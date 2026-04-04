# Claude Trade Bot

An AI-powered trading bot that uses Claude to generate trading signals and executes them via the Trading212 API. Includes a real-time web dashboard for monitoring.

## Features

- Claude Sonnet-powered signal generation with portfolio context
- Automated risk management (position sizing, stop-loss, take-profit)
- Real-time dashboard with live updates via Server-Sent Events
- Paper trading support via Trading212 demo environment
- Docker-ready deployment

## Running Locally

### Prerequisites

- Python 3.9+
- [Trading212](https://www.trading212.com/) account with API access enabled
- [Anthropic API key](https://console.anthropic.com/)

### Step 1 — Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
```

### Step 2 — Install dependencies

```bash
pip install -r requirements.txt
```

### Step 3 — Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in the required values:

| Key | Where to get it |
|---|---|
| `T212_API_KEY` | Trading212 app → Settings → API Key |
| `T212_API_SECRET` | Trading212 app → Settings → API Key |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/) |

Leave `T212_ENV=demo` to use paper trading (no real money).

### Step 4 — Start the bot

```bash
python main.py
```

### Step 5 — Open the dashboard

Navigate to **http://localhost:8080**

You'll see the live dashboard with account info, positions, signals, and trade log. Use the toggle button to enable/disable trading.

---

## Running with Docker

```bash
cp .env.example .env   # fill in your keys first
docker-compose up --build
```

Dashboard available at `http://localhost:8080`

## Configuration

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

## Architecture

```
FastAPI Dashboard (port 8080)
        │
  TradingEngine (async loop)
        │
   ┌────┼────┐
   ▼    ▼    ▼
Claude  Risk  Trading212
Strategy Mgr  API Client
```

Each cycle: fetch account state → generate signals (Claude) → validate (risk manager) → execute orders → manage exits.

## Dashboard

The web UI provides:
- Bot status and toggle (enable/disable)
- Account balance and open positions
- Recent trading signals with confidence scores
- Trade history and pending orders

## Warning

Set `T212_ENV=live` only when you intend to trade with real money. Use `demo` for testing.
