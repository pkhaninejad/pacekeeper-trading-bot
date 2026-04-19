# Prediction Market Bot — Master Design Spec

**Date:** 2026-04-17
**Status:** Draft

---

## Problem

The existing trading bot only trades equities via Trading212. Prediction markets (Polymarket, Kalshi) offer high-edge short-duration opportunities across sports, politics, and crypto/finance — but neither platform offers paper trading. We need a separate runnable instance that scans prediction markets, identifies near-certain outcomes, evaluates edge via LLM, and paper-trades them with full result tracking.

---

## Top 3 Categories (by edge reliability)

### 1. Crypto & Finance
- **Why highest edge:** Quantifiable data (on-chain metrics, price feeds, protocol schedules), fast resolution, high Polymarket liquidity.
- **Examples:** "Will BTC stay above $X this week?", "Will ETH upgrade ship by date?", Fed rate decisions, CPI outcomes.
- **Data sources:** Binance/CoinGecko price API, Fed schedule, BLS calendar, Cleveland Fed Nowcast.

### 2. Sports (Live & Pre-game)
- **Why high edge:** Real-time score feeds create information speed advantages. Series/tournament markets with lopsided records (e.g., 3-0 leads) are systematically mispriced.
- **Examples:** "Will team X win?" (when up 30 pts in Q4), "Will player score 20+?" (has 19 in Q3), series advancement.
- **Data sources:** ESPN API, Polymarket `/sports` tags, live score feeds.

### 3. Politics & Current Events
- **Why decent edge:** Procedural certainties (bill passage after full votes, confirmed appointments) create "already decided" markets that sit at 90-95¢. Longer-duration mispricings.
- **Examples:** "Will bill X become law?" (after passing both chambers), Senate confirmations with public whip counts, election calls.
- **Data sources:** Congress.gov API, AP News, official government sites, news aggregators.

---

## Architecture Overview

Reuses the existing bot's patterns but with its own entry point, engine, and data layer. Shares nothing at runtime with the stock trading bot.

```
prediction_bot/
  main.py                    # entry point (uvicorn, separate port)
  src/
    api/
      polymarket_client.py   # Polymarket Gamma + CLOB API client
      kalshi_client.py       # Kalshi REST API client
      models.py              # Pydantic models for PM data
    bot/
      engine.py              # PredictionEngine (scan → evaluate → paper-trade)
      scanner.py             # Market scanner (filters near-expiry high-prob)
      evaluator.py           # LLM-based probability assessment
      paper_trader.py        # Paper trading state machine + persistence
    config/
      settings.py            # PredictionBotSettings (Pydantic BaseSettings)
    dashboard/
      app.py                 # FastAPI server + dashboard (separate port)
      templates/
        dashboard.html       # Prediction market dashboard UI
    data/
      market_data.py         # External data enrichment (prices, scores, news)
      result_store.py        # SQLite persistence for paper trades + outcomes
  tests/
    test_scanner.py
    test_evaluator.py
    test_paper_trader.py
    test_result_store.py
    test_polymarket_client.py
    test_kalshi_client.py
```

---

## Implementation Tickets (Dependency Order)

| # | Ticket | Depends On | Description |
|---|--------|------------|-------------|
| 1 | Project scaffold & settings | — | Entry point, settings, directory structure |
| 2 | Polymarket API client | 1 | Gamma API + CLOB client for market data |
| 3 | Kalshi API client | 1 | Kalshi REST client for market data |
| 4 | Market scanner | 2, 3 | Scan near-expiry markets, filter by category, find high-prob candidates |
| 5 | LLM evaluator | 1 | Send market + external data to Claude, get probability assessment |
| 6 | Paper trader + result store | 1 | Paper trading state machine with SQLite persistence |
| 7 | Dashboard + result display | 1–6 | FastAPI dashboard showing scan results, paper trades, P&L |

---

## Paper Trading Strategy

Neither Polymarket nor Kalshi offers paper trading. We implement it locally:

1. **On signal:** Record a virtual trade (market_id, side, price_at_entry, quantity, timestamp) in SQLite
2. **On resolution:** When market resolves (YES/NO), compute P&L:
   - Bought YES at $0.92, resolved YES → profit = $0.08/contract
   - Bought YES at $0.92, resolved NO → loss = $0.92/contract
3. **On startup:** Load previous results from SQLite, display cumulative P&L and win rate
4. **Virtual bankroll:** Start with configurable amount (default $1000), track balance over time

### Result Persistence Schema (SQLite)

```sql
CREATE TABLE paper_trades (
    id INTEGER PRIMARY KEY,
    platform TEXT NOT NULL,          -- 'polymarket' | 'kalshi'
    market_id TEXT NOT NULL,
    market_question TEXT NOT NULL,
    category TEXT NOT NULL,          -- 'crypto' | 'sports' | 'politics'
    side TEXT NOT NULL,              -- 'YES' | 'NO'
    entry_price REAL NOT NULL,       -- price when paper-bought
    quantity REAL NOT NULL,          -- number of contracts
    cost REAL NOT NULL,              -- entry_price * quantity
    confidence REAL NOT NULL,        -- LLM confidence
    reasoning TEXT,                  -- LLM reasoning
    status TEXT NOT NULL DEFAULT 'OPEN',  -- 'OPEN' | 'WON' | 'LOST' | 'EXPIRED'
    exit_price REAL,                 -- 1.0 if won, 0.0 if lost
    pnl REAL,                        -- profit/loss after resolution
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    resolution_source TEXT           -- how we determined the outcome
);

CREATE TABLE bankroll_snapshots (
    id INTEGER PRIMARY KEY,
    balance REAL NOT NULL,
    timestamp TEXT NOT NULL,
    trade_id INTEGER REFERENCES paper_trades(id)
);
```

---

## Cycle Flow

Every `SCAN_INTERVAL_SECONDS` (default 120):

```
PredictionEngine._cycle()
  1. Load previous results from SQLite (on first run)
     → Display cumulative stats: total trades, win rate, total P&L, ROI
  2. Check open paper trades
     → For each: query market status; if resolved, settle + update bankroll
  3. Scan markets (both platforms)
     → Filter: active, expiring within EXPIRY_WINDOW_HOURS (default 48h)
     → Filter: price in HIGH_PROB_RANGE (default 0.80–0.97 for YES or NO side)
     → Filter: category in ENABLED_CATEGORIES
     → Filter: minimum liquidity threshold
  4. Enrich candidates with external data
     → Crypto: current prices from CoinGecko/Binance
     → Sports: live scores from ESPN
     → Politics: recent headlines from news APIs
  5. LLM evaluation (batch)
     → Send top N candidates to Claude with context
     → Receive: estimated_true_probability, confidence, reasoning
  6. Edge calculation
     → edge = true_prob - market_price - estimated_fees
     → Filter: edge > MIN_EDGE_PCT (default 0.02)
  7. Paper-trade
     → Allocate from virtual bankroll (max position size % of balance)
     → Record in SQLite
  8. Broadcast to dashboard via SSE
```

---

## Configuration

```python
# Prediction Market Settings
POLYMARKET_ENABLED: bool = True
KALSHI_ENABLED: bool = True
KALSHI_API_KEY: str = ""
KALSHI_API_SECRET: str = ""

# Scanning
SCAN_INTERVAL_SECONDS: int = 120
EXPIRY_WINDOW_HOURS: int = 48
HIGH_PROB_MIN: float = 0.80
HIGH_PROB_MAX: float = 0.97
MIN_LIQUIDITY: float = 1000.0
MIN_EDGE_PCT: float = 0.02
ENABLED_CATEGORIES: list[str] = ["crypto", "sports", "politics"]

# Paper Trading
VIRTUAL_BANKROLL: float = 1000.0
MAX_POSITION_PCT: float = 0.10   # 10% of bankroll per trade
MAX_OPEN_POSITIONS: int = 20
PM_DB_PATH: str = "prediction_bot/data/paper_trades.db"

# Dashboard
PM_DASHBOARD_PORT: int = 4001
```

---

## Files in Parent Repo

This entire bot lives under `prediction_bot/` in the same repository but runs independently. Shared:
- `.env` (add new env vars)
- `requirements.txt` (add new deps: `py-clob-client`, `aiosqlite`)
- `docker-compose.yml` (add second service)
