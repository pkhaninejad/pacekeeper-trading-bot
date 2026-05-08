# Claude Trade Bot

AI-powered prediction + execution bot for Trading212, with a FastAPI dashboard.

## Which bot is which

- `stock_bot.py` = stock trading bot (Trading212 + dashboard)
- `prediction_bot/main.py` = prediction market bot

## Quick Start (Local)

### 1. Create the virtual environment

```bash
python3 -m venv .venv
```

### 2. Install dependencies (important)

Always use the project venv binaries:

```bash
.venv/bin/pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Set these required values in `.env`:

- `T212_API_KEY`
- `T212_API_SECRET`
- `ANTHROPIC_API_KEY`

Recommended while testing:

- `T212_ENV=demo` (paper trading)
- `BOT_ENABLED=false` (start in safe/manual mode)

### 4. Start the stock trading bot app

```bash
.venv/bin/python stock_bot.py
```

### 5. Open the dashboard

- [http://localhost:4000](http://localhost:4000)

## Verify the bot is running

Check status directly:

```bash
curl http://localhost:4000/api/status
```

If running correctly, you should get JSON with bot status fields.

You can manually trigger one prediction/trading cycle from the dashboard or:

```bash
curl -X POST http://localhost:4000/api/cycle
```

## Safety-first test flow

1. Keep `T212_ENV=demo`
2. Keep `BOT_ENABLED=false`
3. Start app and confirm dashboard loads
4. Trigger one manual cycle (`POST /api/cycle`)
5. Review signals/trades in dashboard
6. Only then set `BOT_ENABLED=true` if behavior looks correct

## Run With Docker

```bash
cp .env.example .env
# edit .env first
docker-compose up --build
```

Dashboard: [http://localhost:4000](http://localhost:4000)

## Run The Prediction Bot

From the repo root:

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m prediction_bot.main
.venv/bin/python prediction_bot/main.py
```

Prefer `-m prediction_bot.main` as the default form; it is the most reliable import path setup.

Prediction bot dashboard: [http://localhost:4001](http://localhost:4001)

## Common Issues

- `ModuleNotFoundError` or missing packages:
  - You likely used system Python. Re-run with `.venv/bin/python` and `.venv/bin/pip`.
- Dashboard not reachable:
  - Confirm server is running and check `DASHBOARD_PORT` in `.env` (default `4000`).
- No trades/signals appear:
  - Ensure API keys are valid and market/account constraints allow orders.
  - Try manual cycle endpoint and inspect logs.

## Key Environment Variables

- `T212_API_KEY`, `T212_API_SECRET`
- `T212_ENV` (`demo` or `live`)
- `ANTHROPIC_API_KEY`
- `BOT_ENABLED`
- `TRADE_INTERVAL_SECONDS`
- `MAX_OPEN_POSITIONS`
- `MAX_POSITION_SIZE_PCT`
- `STOP_LOSS_PCT`, `TAKE_PROFIT_PCT`
- `WATCHLIST`
- `DASHBOARD_PORT`

## Warning

Use `T212_ENV=live` only when you intentionally want real-money trading.
