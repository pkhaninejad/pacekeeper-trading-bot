# Claude Trade Bot

Two independent bots in one repo:

| Bot | Description | Port |
|---|---|---|
| **Stock Bot** | AI-powered stock trading via Trading212 | 8888 |
| **Prediction Market Bot** | Paper-trades Polymarket & Kalshi outcomes | 4001 |

---

## Stock Bot

An AI-powered trading bot that uses Claude to generate trading signals and executes them via the Trading212 API.

### Features

- Claude Sonnet-powered signal generation with portfolio context
- Automated risk management (position sizing, stop-loss, take-profit)
- Real-time dashboard with live updates via Server-Sent Events
- Paper trading support via Trading212 demo environment
- Docker-ready deployment

### Running Locally

**Prerequisites:** Python 3.9+, Trading212 account with API access, Anthropic API key.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in T212_API_KEY, T212_API_SECRET, ANTHROPIC_API_KEY
python main.py
```

Dashboard: **http://localhost:8888**

### Running with Docker

```bash
cp .env.example .env
docker-compose up --build trade-bot
```

### Configuration

| Variable | Default | Description |
|---|---|---|
| `T212_API_KEY` | — | Trading212 API key |
| `T212_API_SECRET` | — | Trading212 API secret |
| `T212_ENV` | `demo` | `demo` (paper) or `live` (real money) |
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `CLAUDE_MODEL` | `claude-sonnet-4-6` | Claude model to use |
| `BOT_ENABLED` | `true` | Enable/disable trading |
| `TRADE_INTERVAL_SECONDS` | `300` | Cycle frequency (5 min) |
| `MAX_POSITION_SIZE_PCT` | `0.05` | Max 5% of portfolio per trade |
| `MAX_OPEN_POSITIONS` | `10` | Maximum concurrent positions |
| `STOP_LOSS_PCT` | `0.02` | Auto-close at 2% loss |
| `TAKE_PROFIT_PCT` | `0.04` | Auto-close at 4% gain |

Default watchlist: `AAPL, TSLA, NVDA, MSFT, AMZN, GOOGL, META, NFLX`

### Architecture

```
FastAPI Dashboard (port 8888)
        │
  TradingEngine (async loop)
        │
   ┌────┼────┐
   ▼    ▼    ▼
Claude  Risk  Trading212
Strategy Mgr  API Client
```

Each cycle: fetch account state → generate signals (Claude) → validate (risk manager) → execute orders → manage exits.

### Warning

Set `T212_ENV=live` only when you intend to trade with real money. Use `demo` for testing.

---

## Prediction Market Bot

A standalone paper-trading bot that scans Polymarket and Kalshi for near-certain outcomes, evaluates edge via Claude, and tracks virtual trades with SQLite persistence.

### Features

- Scans Polymarket (no API key needed) and Kalshi for high-probability markets
- Claude evaluates each candidate and estimates true probability
- Paper-trades with a virtual $1,000 bankroll (no real money)
- SQLite persistence — trades and bankroll survive restarts
- Real-time dashboard with live P&L, win rate, and countdown to next scan
- Configurable scan interval and on-demand scan from the dashboard

### Running Locally

**Prerequisites:** Python 3.9+, Anthropic API key. Polymarket needs no API key; Kalshi is optional.

```bash
# same venv as above
cp .env.example .env   # set ANTHROPIC_API_KEY at minimum
.venv/bin/python -m prediction_bot.main
```

Dashboard: **http://localhost:4001**

### Running with Docker

```bash
docker-compose up --build prediction-bot
```

### Configuration

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required for LLM evaluation |
| `POLYMARKET_ENABLED` | `true` | Enable Polymarket scanning |
| `KALSHI_ENABLED` | `false` | Enable Kalshi (requires API key) |
| `KALSHI_API_KEY` | — | Kalshi API key (kalshi.com → Settings) |
| `SCAN_INTERVAL_SECONDS` | `120` | How often to scan (also settable from dashboard) |
| `EXPIRY_WINDOW_HOURS` | `168` | Only trade markets expiring within this window |
| `HIGH_PROB_MIN` | `0.80` | Minimum market price to consider |
| `HIGH_PROB_MAX` | `0.97` | Maximum market price (avoid near-certain markets) |
| `MIN_LIQUIDITY` | `1000` | Minimum market liquidity in USD |
| `MIN_EDGE_PCT` | `0.02` | Minimum fee-adjusted edge to place a trade |
| `VIRTUAL_BANKROLL` | `1000` | Starting paper bankroll in USD |
| `MAX_POSITION_PCT` | `0.10` | Max 10% of bankroll per position |
| `MAX_OPEN_POSITIONS` | `20` | Maximum concurrent open trades |
| `PM_DASHBOARD_PORT` | `4001` | Dashboard port |

### Architecture

```
FastAPI Dashboard (port 4001)
        │
  PredictionEngine (async loop)
        │
   ┌────┼────────┐
   ▼    ▼        ▼
Scanner Evaluator PaperTrader
   │    (Claude)      │
   ▼                  ▼
Polymarket        ResultStore
Kalshi            (SQLite)
```

Each cycle: settle open trades → scan markets → evaluate with Claude → place paper trades → update dashboard.

### Dashboard Controls

| Control | Description |
|---|---|
| **Toggle** | Pause/resume scanning without stopping the process |
| **Scan Now** | Trigger an immediate scan cycle |
| **Scan Interval** | Change how often the bot scans (seconds), takes effect immediately |
| **If All Win** | Total profit if every open trade resolves correctly |

### Trade Lifecycle

1. Scanner finds markets expiring within `EXPIRY_WINDOW_HOURS` with price in `[HIGH_PROB_MIN, HIGH_PROB_MAX]`
2. Claude estimates true probability and fee-adjusted edge
3. If edge > `MIN_EDGE_PCT`, a paper trade is placed (cost deducted from bankroll)
4. Each cycle checks open trades for resolution — settled as WON/LOST, or expired after 72h
5. All trades and bankroll snapshots persist in `prediction_bot/data/paper_trades.db`
