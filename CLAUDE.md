# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
python main.py

# Run with Docker (recommended)
docker-compose up --build

# Access dashboard at http://localhost:8080
```

Run tests with: `.venv/bin/python -m pytest tests/ -v`

## Environment Setup

Copy `.env.example` to `.env` and fill in:
- `T212_API_KEY` / `T212_API_SECRET` — Trading212 credentials
- `ANTHROPIC_API_KEY` — Anthropic API key
- `T212_ENV` — `demo` (paper trading) or `live` (real money)

## Architecture

The bot runs as a FastAPI server with a background async trading loop.

**Entry point:** `main.py` → `src/dashboard/app.py` (FastAPI lifespan starts TradingEngine)

**Trading cycle** (every `TRADE_INTERVAL_SECONDS`, default 300s):
1. `TradingEngine._cycle()` (`src/bot/engine.py`) — fetches account state from Trading212
2. `ClaudeStrategy.generate_signals()` (`src/bot/strategy.py`) — sends portfolio context to Claude Sonnet, receives JSON `TradeSignal` objects
3. `RiskManager.validate()` (`src/bot/risk_manager.py`) — enforces position limits, confidence threshold (≥0.6), cash availability, auto-scales size
4. `TradingEngine._execute_signal()` — places orders via `Trading212Client`
5. `TradingEngine._manage_exits()` — auto-closes positions hitting stop-loss (2%) or take-profit (4%)

**Key modules:**
- `src/api/client.py` — async Trading212 HTTP client (Basic auth, 0.5s rate limiting)
- `src/api/models.py` — Pydantic models for all API requests/responses and internal types (`TradeSignal`, `BotStatus`, etc.)
- `src/config/settings.py` — all configuration via Pydantic settings loaded from `.env`
- `src/dashboard/app.py` — REST API endpoints + Server-Sent Events stream for real-time dashboard updates

**Dashboard API endpoints** (all under `/api/`):
- `GET /api/status`, `POST /api/bot/toggle` — bot state
- `GET /api/account`, `/api/positions`, `/api/orders` — Trading212 data
- `GET /api/signals`, `/api/trades` — in-memory history (100/200 entries, cleared on restart)
- `POST /api/cycle` — manually trigger a trading cycle
- `GET /api/stream` — SSE stream for the dashboard UI

**In-memory state:** Signal history and trade logs live only in `TradingEngine` instance — they are lost on restart. There is no database.

## Trading212 API Notes

- `T212_ENV=demo` uses the paper trading endpoint; `live` uses real money — be careful
- The client uses HTTP Basic auth with base64-encoded `key:secret`
- Rate limit: 0.5s delay enforced between requests in `client.py`
