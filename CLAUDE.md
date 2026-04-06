# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies into the project venv
.venv/bin/pip install -r requirements.txt

# Run locally with auto-reload (nodemon equivalent)
.venv/bin/python main.py

# Run with Docker
docker-compose up --build

# Run all tests
.venv/bin/python -m pytest tests/ -v

# Run a single test file
.venv/bin/python -m pytest tests/test_risk_manager.py -v

# Access dashboard
open http://localhost:4000
```

The project uses `.venv/` (Python 3.14). Always use `.venv/bin/python` / `.venv/bin/pip` — the system `python3` does not have the project dependencies.

## Environment Setup

Copy `.env.example` to `.env` and fill in:
- `T212_API_KEY` / `T212_API_SECRET` — Trading212 credentials (both required for Basic auth)
- `ANTHROPIC_API_KEY` — Anthropic API key
- `T212_ENV` — `demo` (paper trading) or `live` (real money)

`WATCHLIST`, port, and risk parameters can also be overridden in `.env` — see `src/config/settings.py` for all keys and defaults.

## Architecture

The bot runs as a FastAPI server with a background async trading loop started via the FastAPI `lifespan` context manager.

**Entry point:** `main.py` → `src/dashboard/app.py` (FastAPI lifespan creates `TradingEngine` and calls `engine.start()` as an asyncio task)

**Trading cycle** (every `TRADE_INTERVAL_SECONDS`, default 300s):
1. `TradingEngine._cycle()` (`src/bot/engine.py`) — fetches cash and positions from Trading212; lazily loads and caches instrument metadata on first run
2. `TradingEngine._manage_exits()` — auto-closes positions hitting stop-loss (2%) or take-profit (4%) before generating new signals
3. `ClaudeStrategy.generate_signals()` (`src/bot/strategy.py`) — calls `price_feed.get_price_summary()` for 30-day OHLCV context, then sends the full portfolio + price context to Claude Sonnet; receives a JSON array of `TradeSignal` objects
4. `RiskManager.validate()` (`src/bot/risk_manager.py`) — enforces: confidence ≥ 0.6, max open positions, cash availability, max position size (auto-scales down if needed), no duplicate direction
5. `TradingEngine._execute_signal()` — resolves short ticker (e.g. `NVDA`) to T212 format (`NVDA_US_EQ`) via `_ticker_map`, then places market/limit/stop order

**Key modules:**
- `src/api/client.py` — async Trading212 HTTP client; uses HTTP Basic auth (`Base64(key:secret)`); global asyncio lock + 1s delay between all requests; exponential backoff on 429s (5s/10s/20s)
- `src/api/models.py` — Pydantic v2 models for all API types plus `TradeSignal` and `BotStatus`
- `src/bot/price_feed.py` — yfinance wrapper; fetches 30-day OHLCV, computes SMA10/SMA30/RSI14; 5-minute in-process cache
- `src/config/settings.py` — Pydantic `BaseSettings` loaded from `.env`; `settings.t212_base_url` switches between demo/live endpoints

**Dashboard API endpoints** (all under `/api/`):
- `GET /status`, `POST /bot/toggle` — bot state
- `GET /account`, `/positions`, `/orders` — live Trading212 data (account/positions responses cached 30s)
- `POST /positions/{ticker}/close`, `POST /positions/close-all` — close specific or all positions
- `GET /signals`, `/trades` — in-memory history (last 100 signals / 200 trades, cleared on restart)
- `POST /cycle` — manually trigger a trading cycle
- `GET /stream` — SSE feed consumed by the dashboard UI for real-time updates

**In-memory state only:** Signal history, trade log, instrument cache, and ticker map all live in the `TradingEngine` instance and are lost on restart. No database.

## Branching and PRs

Do not use git worktrees. For all feature work: create a branch, implement, then open a PR. Branch naming: `feat/<topic>` or `fix/<topic>`.

## File Size Guidelines

Keep files focused and small. When a file grows large, extract cohesive functionality into its own module rather than adding more to the existing file. Prefer many small, single-purpose files over a few large ones.

- If a file exceeds ~200 lines, consider whether it is doing too much and split it.
- Extract helper functions, data models, or sub-strategies into separate modules.
- Never add to a file that is already large — refactor first, then add.

This keeps token consumption low and each file easy to reason about in context.

## Trading212 API Notes

- `T212_ENV=demo` maps to `demo.trading212.com`; `live` maps to `live.trading212.com` — the same key pair works for both
- The Invest/ISA account type is required for demo; CFD accounts use a different API
- Tickers must use T212 format: `NVDA_US_EQ` not `NVDA`. The engine pre-seeds a `_ticker_map` and extends it from the instruments endpoint at startup
- The global lock in `client.py` is shared across all `Trading212Client` instances in the process — required to avoid 429s when the dashboard and engine make concurrent requests
