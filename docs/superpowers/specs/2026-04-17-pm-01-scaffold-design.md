# Ticket 1: Project Scaffold & Settings — Design Spec

**Date:** 2026-04-17
**Status:** Draft
**Master Spec:** [prediction-market-bot-design.md](2026-04-17-prediction-market-bot-design.md)
**Depends on:** Nothing

---

## Goal

Create the `prediction_bot/` directory structure, entry point, settings module, and base models so all subsequent tickets have a working skeleton to build on.

---

## New Files

### `prediction_bot/main.py`

```python
import logging, uvicorn
from prediction_bot.src.config.settings import pm_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

if __name__ == "__main__":
    uvicorn.run("prediction_bot.src.dashboard.app:app", host="0.0.0.0", port=pm_settings.PM_DASHBOARD_PORT, reload=True)
```

### `prediction_bot/src/config/settings.py`

Pydantic BaseSettings, loaded from `.env`:

```python
class PredictionBotSettings(BaseSettings):
    # Platform toggles
    POLYMARKET_ENABLED: bool = True
    KALSHI_ENABLED: bool = True

    # Kalshi auth
    KALSHI_API_KEY: str = ""
    KALSHI_API_SECRET: str = ""

    # LLM
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-sonnet-4-6"

    # Scanning
    SCAN_INTERVAL_SECONDS: int = 120
    EXPIRY_WINDOW_HOURS: int = 48
    HIGH_PROB_MIN: float = 0.80
    HIGH_PROB_MAX: float = 0.97
    MIN_LIQUIDITY: float = 1000.0
    MIN_EDGE_PCT: float = 0.02
    ENABLED_CATEGORIES: list[str] = ["crypto", "sports", "politics"]

    # Paper trading
    VIRTUAL_BANKROLL: float = 1000.0
    MAX_POSITION_PCT: float = 0.10
    MAX_OPEN_POSITIONS: int = 20
    PM_DB_PATH: str = "prediction_bot/data/paper_trades.db"

    # Dashboard
    PM_DASHBOARD_PORT: int = 4001

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

pm_settings = PredictionBotSettings()
```

### `prediction_bot/src/api/models.py`

Pydantic v2 models:

```python
class PredictionMarket:
    id: str
    platform: str                # "polymarket" | "kalshi"
    question: str
    category: str                # "crypto" | "sports" | "politics"
    end_date: datetime
    yes_price: float
    no_price: float
    volume_24h: float
    liquidity: float
    slug: str
    metadata: dict = {}          # platform-specific extras

class MarketCandidate:
    market: PredictionMarket
    best_side: str               # "YES" | "NO"
    market_price: float          # price of best_side
    external_data: dict = {}     # enrichment data
    llm_true_prob: float | None  # filled by evaluator
    llm_confidence: float | None
    llm_reasoning: str | None
    edge: float | None           # true_prob - market_price - fees

class PaperTrade:
    id: int | None
    platform: str
    market_id: str
    market_question: str
    category: str
    side: str
    entry_price: float
    quantity: float
    cost: float
    confidence: float
    reasoning: str | None
    status: str = "OPEN"         # OPEN | WON | LOST | EXPIRED
    exit_price: float | None
    pnl: float | None
    created_at: datetime
    resolved_at: datetime | None

class BankrollSnapshot:
    id: int | None
    balance: float
    timestamp: datetime
    trade_id: int | None

class PMBotStatus:
    enabled: bool
    platforms: dict               # {"polymarket": True, "kalshi": False}
    categories: list[str]
    open_trades: int
    bankroll: float
    total_pnl: float
    win_rate: float | None
    last_scan: datetime | None
    next_scan: datetime | None
```

### Directory `__init__.py` files

Create empty `__init__.py` in:
- `prediction_bot/`
- `prediction_bot/src/`
- `prediction_bot/src/api/`
- `prediction_bot/src/bot/`
- `prediction_bot/src/config/`
- `prediction_bot/src/dashboard/`
- `prediction_bot/src/data/`

### `.env.example` additions

```env
# === Prediction Market Bot ===
POLYMARKET_ENABLED=true
KALSHI_ENABLED=false
KALSHI_API_KEY=
KALSHI_API_SECRET=
SCAN_INTERVAL_SECONDS=120
EXPIRY_WINDOW_HOURS=48
HIGH_PROB_MIN=0.80
HIGH_PROB_MAX=0.97
MIN_LIQUIDITY=1000
MIN_EDGE_PCT=0.02
ENABLED_CATEGORIES=crypto,sports,politics
VIRTUAL_BANKROLL=1000
MAX_POSITION_PCT=0.10
MAX_OPEN_POSITIONS=20
PM_DASHBOARD_PORT=4001
```

---

## Modified Files

| File | Change |
|---|---|
| `requirements.txt` | Add: `aiosqlite`, `py-clob-client` (Polymarket SDK) |
| `docker-compose.yml` | Add `prediction-bot` service on port 4001 |
| `.env.example` | Add prediction market env vars |

---

## Testing

`prediction_bot/tests/test_settings.py`:
- `test_defaults_loaded` — verify defaults with no env vars
- `test_env_override` — verify `.env` overrides work
- `test_categories_parsing` — comma-separated list parsed correctly

---

## Acceptance Criteria

- [ ] `prediction_bot/main.py` starts uvicorn on port 4001
- [ ] Settings load from `.env` with sane defaults
- [ ] All Pydantic models validate correctly
- [ ] `docker-compose up prediction-bot` works
