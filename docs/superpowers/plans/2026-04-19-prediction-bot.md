# Prediction Market Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone `prediction_bot/` service that scans Polymarket + Kalshi for near-certain outcomes, evaluates edge via LLM, and paper-trades them with SQLite persistence and a FastAPI dashboard on port 4001.

**Architecture:** Separate `prediction_bot/` package in the same repo. Own entry point (`python -m prediction_bot.main`), own `PredictionBotSettings`, own `PredictionEngine` loop. Shares `.env` and `requirements.txt` with the stock bot. SQLite persists paper trades across restarts. Dashboard mirrors the stock bot pattern (FastAPI + Jinja2 + SSE).

**Tech Stack:** Python 3.14, FastAPI, Uvicorn, aiosqlite, httpx, litellm, pydantic-settings, Jinja2, pytest, pytest-asyncio

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `prediction_bot/__init__.py` | Create | Package marker |
| `prediction_bot/main.py` | Create | Entry point — uvicorn on port 4001 |
| `prediction_bot/src/__init__.py` | Create | Package marker |
| `prediction_bot/src/config/__init__.py` | Create | Package marker |
| `prediction_bot/src/config/settings.py` | Create | `PredictionBotSettings` (Pydantic BaseSettings) |
| `prediction_bot/src/api/__init__.py` | Create | Package marker |
| `prediction_bot/src/api/models.py` | Create | Pydantic models: PredictionMarket, MarketCandidate, PaperTrade, BankrollSnapshot, PMBotStatus |
| `prediction_bot/src/api/polymarket_client.py` | Create | Async httpx client for Polymarket Gamma API |
| `prediction_bot/src/api/kalshi_client.py` | Create | Async httpx client for Kalshi API |
| `prediction_bot/src/bot/__init__.py` | Create | Package marker |
| `prediction_bot/src/bot/scanner.py` | Create | `scan_markets()` — filter + rank candidates |
| `prediction_bot/src/bot/evaluator.py` | Create | LLM probability assessment + edge calculation |
| `prediction_bot/src/bot/paper_trader.py` | Create | `PaperTrader` — bankroll mgmt + trade lifecycle |
| `prediction_bot/src/bot/engine.py` | Create | `PredictionEngine` — orchestrates full cycle |
| `prediction_bot/src/data/__init__.py` | Create | Package marker |
| `prediction_bot/src/data/market_data.py` | Create | External data enrichment (CoinGecko, ESPN, news) |
| `prediction_bot/src/data/result_store.py` | Create | `ResultStore` — aiosqlite persistence |
| `prediction_bot/src/dashboard/__init__.py` | Create | Package marker |
| `prediction_bot/src/dashboard/app.py` | Create | FastAPI server + SSE + REST endpoints |
| `prediction_bot/src/dashboard/templates/dashboard.html` | Create | Dashboard UI |
| `prediction_bot/tests/__init__.py` | Create | Package marker |
| `prediction_bot/tests/test_settings.py` | Create | Settings tests |
| `prediction_bot/tests/test_polymarket_client.py` | Create | Polymarket client tests |
| `prediction_bot/tests/test_kalshi_client.py` | Create | Kalshi client tests |
| `prediction_bot/tests/test_scanner.py` | Create | Scanner tests |
| `prediction_bot/tests/test_evaluator.py` | Create | Evaluator + market_data tests |
| `prediction_bot/tests/test_result_store.py` | Create | ResultStore tests |
| `prediction_bot/tests/test_paper_trader.py` | Create | PaperTrader tests |
| `prediction_bot/Dockerfile` | Create | Container definition |
| `requirements.txt` | Modify | Add `aiosqlite` |
| `docker-compose.yml` | Modify | Add `prediction-bot` service |
| `.env.example` | Modify | Add prediction bot env vars |

---

## Task 1: Scaffold — directories, settings, models, minimal FastAPI

**Files:**
- Create: all `__init__.py` files
- Create: `prediction_bot/main.py`
- Create: `prediction_bot/src/config/settings.py`
- Create: `prediction_bot/src/api/models.py`
- Create: `prediction_bot/src/dashboard/app.py` (stub)
- Create: `prediction_bot/tests/test_settings.py`
- Modify: `requirements.txt`, `.env.example`

- [ ] **Step 1: Add aiosqlite to requirements.txt**

```bash
echo "aiosqlite>=0.20.0" >> requirements.txt
.venv/bin/pip install aiosqlite
```

- [ ] **Step 2: Create directory skeleton**

```bash
mkdir -p prediction_bot/src/config
mkdir -p prediction_bot/src/api
mkdir -p prediction_bot/src/bot
mkdir -p prediction_bot/src/data
mkdir -p prediction_bot/src/dashboard/templates
mkdir -p prediction_bot/tests
mkdir -p prediction_bot/data

touch prediction_bot/__init__.py
touch prediction_bot/src/__init__.py
touch prediction_bot/src/config/__init__.py
touch prediction_bot/src/api/__init__.py
touch prediction_bot/src/bot/__init__.py
touch prediction_bot/src/data/__init__.py
touch prediction_bot/src/dashboard/__init__.py
touch prediction_bot/tests/__init__.py
```

- [ ] **Step 3: Write the failing settings test**

Create `prediction_bot/tests/test_settings.py`:

```python
"""Tests for PredictionBotSettings."""
import os
import pytest


class TestPredictionBotSettings:
    def test_defaults_loaded(self):
        """All fields have sane defaults when no env vars set."""
        os.environ.pop("POLYMARKET_ENABLED", None)
        os.environ.pop("VIRTUAL_BANKROLL", None)
        from prediction_bot.src.config.settings import PredictionBotSettings
        s = PredictionBotSettings()
        assert s.POLYMARKET_ENABLED is True
        assert s.KALSHI_ENABLED is True
        assert s.VIRTUAL_BANKROLL == 1000.0
        assert s.MAX_POSITION_PCT == 0.10
        assert s.PM_DASHBOARD_PORT == 4001
        assert s.SCAN_INTERVAL_SECONDS == 120

    def test_env_override(self, monkeypatch):
        """Env vars override defaults."""
        monkeypatch.setenv("VIRTUAL_BANKROLL", "500.0")
        monkeypatch.setenv("PM_DASHBOARD_PORT", "4002")
        from importlib import reload
        import prediction_bot.src.config.settings as m
        reload(m)
        s = m.PredictionBotSettings()
        assert s.VIRTUAL_BANKROLL == 500.0
        assert s.PM_DASHBOARD_PORT == 4002

    def test_categories_default(self):
        """ENABLED_CATEGORIES defaults to all three."""
        from prediction_bot.src.config.settings import PredictionBotSettings
        s = PredictionBotSettings()
        assert set(s.ENABLED_CATEGORIES) == {"crypto", "sports", "politics"}
```

- [ ] **Step 4: Run test — confirm it fails**

```bash
.venv/bin/python -m pytest prediction_bot/tests/test_settings.py -v
```

Expected: `ModuleNotFoundError: No module named 'prediction_bot.src.config.settings'`

- [ ] **Step 5: Create `prediction_bot/src/config/settings.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class PredictionBotSettings(BaseSettings):
    POLYMARKET_ENABLED: bool = True
    KALSHI_ENABLED: bool = True
    KALSHI_API_KEY: str = ""
    KALSHI_API_SECRET: str = ""
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-sonnet-4-6"
    SCAN_INTERVAL_SECONDS: int = 120
    EXPIRY_WINDOW_HOURS: int = 48
    HIGH_PROB_MIN: float = 0.80
    HIGH_PROB_MAX: float = 0.97
    MIN_LIQUIDITY: float = 1000.0
    MIN_EDGE_PCT: float = 0.02
    ENABLED_CATEGORIES: list[str] = ["crypto", "sports", "politics"]
    VIRTUAL_BANKROLL: float = 1000.0
    MAX_POSITION_PCT: float = 0.10
    MAX_OPEN_POSITIONS: int = 20
    PM_DB_PATH: str = "prediction_bot/data/paper_trades.db"
    PM_DASHBOARD_PORT: int = 4001

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


pm_settings = PredictionBotSettings()
```

- [ ] **Step 6: Run settings test — confirm pass**

```bash
.venv/bin/python -m pytest prediction_bot/tests/test_settings.py -v
```

Expected: all 3 tests pass.

- [ ] **Step 7: Create `prediction_bot/src/api/models.py`**

```python
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel


class PredictionMarket(BaseModel):
    id: str
    platform: str                    # "polymarket" | "kalshi"
    question: str
    category: str                    # "crypto" | "sports" | "politics"
    end_date: datetime
    yes_price: float
    no_price: float
    volume_24h: float = 0.0
    liquidity: float = 0.0
    slug: str = ""
    metadata: dict = {}


class MarketCandidate(BaseModel):
    market: PredictionMarket
    best_side: str                   # "YES" | "NO"
    market_price: float
    external_data: dict = {}
    llm_true_prob: float | None = None
    llm_confidence: float | None = None
    llm_reasoning: str | None = None
    edge: float | None = None


class PaperTrade(BaseModel):
    id: int | None = None
    platform: str
    market_id: str
    market_question: str
    category: str
    side: str
    entry_price: float
    quantity: float
    cost: float
    confidence: float
    reasoning: str | None = None
    status: str = "OPEN"             # OPEN | WON | LOST | EXPIRED
    exit_price: float | None = None
    pnl: float | None = None
    created_at: datetime
    resolved_at: datetime | None = None
    resolution_source: str | None = None


class BankrollSnapshot(BaseModel):
    id: int | None = None
    balance: float
    timestamp: datetime
    trade_id: int | None = None


class PMBotStatus(BaseModel):
    enabled: bool = True
    platforms: dict = {"polymarket": True, "kalshi": False}
    categories: list[str] = ["crypto", "sports", "politics"]
    open_trades: int = 0
    bankroll: float = 1000.0
    total_pnl: float = 0.0
    win_rate: float | None = None
    last_scan: datetime | None = None
    next_scan: datetime | None = None
```

- [ ] **Step 8: Create stub `prediction_bot/src/dashboard/app.py`**

```python
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from prediction_bot.src.api.models import PMBotStatus

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="Prediction Market Bot", lifespan=lifespan)


@app.get("/api/status")
async def get_status():
    return JSONResponse(PMBotStatus().model_dump(mode="json"))
```

- [ ] **Step 9: Create `prediction_bot/main.py`**

```python
import logging
import uvicorn
from prediction_bot.src.config.settings import pm_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

if __name__ == "__main__":
    uvicorn.run(
        "prediction_bot.src.dashboard.app:app",
        host="0.0.0.0",
        port=pm_settings.PM_DASHBOARD_PORT,
        reload=True,
    )
```

- [ ] **Step 10: Smoke-test the entry point**

```bash
.venv/bin/python -m prediction_bot.main &
sleep 2
curl -s http://localhost:4001/api/status | python3 -m json.tool
kill %1
```

Expected: JSON with `enabled: true`, `bankroll: 1000.0`.

- [ ] **Step 11: Append prediction bot vars to `.env.example`**

Add after the existing content:

```
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

- [ ] **Step 12: Commit**

```bash
git add prediction_bot/ requirements.txt .env.example
git commit -m "feat(pm): scaffold prediction_bot — settings, models, stub dashboard"
```

---

## Task 2: Polymarket API Client

**Files:**
- Create: `prediction_bot/src/api/polymarket_client.py`
- Create: `prediction_bot/tests/test_polymarket_client.py`

- [ ] **Step 1: Write failing tests**

Create `prediction_bot/tests/test_polymarket_client.py`:

```python
"""Tests for PolymarketClient."""
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

from prediction_bot.src.api.models import PredictionMarket


def _make_raw_market(
    id="abc123",
    question="Will BTC stay above $80k?",
    end_date_offset_hours=24,
    yes_price=0.92,
    volume=150000,
    liquidity=50000,
    closed=False,
    tags=None,
):
    end_dt = datetime.now(timezone.utc) + timedelta(hours=end_date_offset_hours)
    return {
        "conditionId": id,
        "question": question,
        "endDate": end_dt.isoformat(),
        "outcomePrices": f'["{yes_price}", "{round(1-yes_price, 2)}"]',
        "volume24hr": volume,
        "liquidity": liquidity,
        "closed": closed,
        "slug": "will-btc-stay-above-80k",
        "tags": tags or [{"label": "Crypto"}],
    }


class TestPolymarketClient:
    @pytest.mark.asyncio
    async def test_get_active_markets_parses_models(self):
        """Returns list of PredictionMarket from raw API response."""
        from prediction_bot.src.api.polymarket_client import PolymarketClient

        raw = {"markets": [_make_raw_market()], "count": 1}

        async with PolymarketClient() as client:
            with patch.object(client._session, "get") as mock_get:
                mock_resp = AsyncMock()
                mock_resp.status_code = 200
                mock_resp.json = MagicMock(return_value=raw)
                mock_resp.raise_for_status = MagicMock()
                mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
                mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

                markets = await client.get_active_markets(limit=10)

        assert len(markets) == 1
        m = markets[0]
        assert isinstance(m, PredictionMarket)
        assert m.platform == "polymarket"
        assert abs(m.yes_price - 0.92) < 0.001
        assert abs(m.no_price - 0.08) < 0.001

    @pytest.mark.asyncio
    async def test_price_extraction_from_json_string(self):
        """outcomePrices JSON string parsed correctly."""
        from prediction_bot.src.api.polymarket_client import _parse_outcome_prices

        yes, no = _parse_outcome_prices('["0.85", "0.15"]')
        assert abs(yes - 0.85) < 0.001
        assert abs(no - 0.15) < 0.001

    @pytest.mark.asyncio
    async def test_near_expiry_filters_by_time(self):
        """get_near_expiry_markets only returns markets within the window."""
        from prediction_bot.src.api.polymarket_client import PolymarketClient

        inside = _make_raw_market(id="in", end_date_offset_hours=20)
        outside = _make_raw_market(id="out", end_date_offset_hours=100)
        raw = {"markets": [inside, outside], "count": 2}

        async with PolymarketClient() as client:
            with patch.object(client._session, "get") as mock_get:
                mock_resp = AsyncMock()
                mock_resp.status_code = 200
                mock_resp.json = MagicMock(return_value=raw)
                mock_resp.raise_for_status = MagicMock()
                mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
                mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

                markets = await client.get_near_expiry_markets(hours=48, min_liquidity=0)

        ids = [m.id for m in markets]
        assert "in" in ids
        assert "out" not in ids

    @pytest.mark.asyncio
    async def test_resolution_detection(self):
        """Closed market with settled prices detected as resolved."""
        from prediction_bot.src.api.polymarket_client import PolymarketClient

        raw_resolved = {
            "conditionId": "res1",
            "closed": True,
            "outcomePrices": '["1.0", "0.0"]',
            "question": "Test?",
            "endDate": datetime.now(timezone.utc).isoformat(),
            "volume24hr": 0,
            "liquidity": 0,
            "slug": "test",
            "tags": [],
        }

        async with PolymarketClient() as client:
            with patch.object(client._session, "get") as mock_get:
                mock_resp = AsyncMock()
                mock_resp.status_code = 200
                mock_resp.json = MagicMock(return_value=raw_resolved)
                mock_resp.raise_for_status = MagicMock()
                mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
                mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

                status = await client.get_market_status("res1")

        assert status["resolved"] is True
        assert status["winner"] == "YES"
```

- [ ] **Step 2: Run — confirm fail**

```bash
.venv/bin/python -m pytest prediction_bot/tests/test_polymarket_client.py -v
```

Expected: `ModuleNotFoundError: No module named 'prediction_bot.src.api.polymarket_client'`

- [ ] **Step 3: Create `prediction_bot/src/api/polymarket_client.py`**

```python
"""Async Polymarket Gamma API client (read-only)."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

import httpx

from prediction_bot.src.api.models import PredictionMarket

logger = logging.getLogger(__name__)

BASE_URL = "https://gamma-api.polymarket.com"
_REQUEST_DELAY = 0.5  # seconds between requests

_CRYPTO_TAGS = {"crypto", "bitcoin", "ethereum", "defi", "token"}
_POLITICS_TAGS = {"politics", "elections", "congress", "government", "president"}


def _parse_outcome_prices(raw: str | list) -> tuple[float, float]:
    prices = json.loads(raw) if isinstance(raw, str) else raw
    return float(prices[0]), float(prices[1])


def _classify_tags(tags: list[dict]) -> str | None:
    for t in tags:
        label = t.get("label", "").lower()
        slug = t.get("slug", "").lower()
        for key in (label, slug):
            if any(k in key for k in _CRYPTO_TAGS):
                return "crypto"
            if any(k in key for k in _POLITICS_TAGS):
                return "politics"
    # Sports is the fallback if tags contain sport-related text
    for t in tags:
        label = t.get("label", "").lower()
        if any(k in label for k in ("nfl", "nba", "mlb", "sport", "game", "match", "team")):
            return "sports"
    return None


def _parse_market(raw: dict) -> PredictionMarket | None:
    try:
        yes_price, no_price = _parse_outcome_prices(raw.get("outcomePrices", '["0.5","0.5"]'))
        end_date = datetime.fromisoformat(raw["endDate"].replace("Z", "+00:00"))
        tags = raw.get("tags") or []
        category = _classify_tags(tags) or "politics"
        return PredictionMarket(
            id=raw["conditionId"],
            platform="polymarket",
            question=raw.get("question", ""),
            category=category,
            end_date=end_date,
            yes_price=yes_price,
            no_price=no_price,
            volume_24h=float(raw.get("volume24hr", 0) or 0),
            liquidity=float(raw.get("liquidity", 0) or 0),
            slug=raw.get("slug", ""),
            metadata={"tags": tags, "closed": raw.get("closed", False)},
        )
    except Exception as e:
        logger.debug("Failed to parse market %s: %s", raw.get("conditionId"), e)
        return None


class PolymarketClient:
    def __init__(self):
        self._session: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._session = httpx.AsyncClient(base_url=BASE_URL, timeout=15.0)
        return self

    async def __aexit__(self, *_):
        if self._session:
            await self._session.aclose()

    async def _get(self, path: str, params: dict | None = None) -> dict:
        await asyncio.sleep(_REQUEST_DELAY)
        for attempt in range(3):
            try:
                async with self._session.get(path, params=params) as resp:
                    resp.raise_for_status()
                    return resp.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    await asyncio.sleep(5 * (2 ** attempt))
                else:
                    raise
        return {}

    async def get_active_markets(
        self,
        limit: int = 100,
        offset: int = 0,
        order: str = "volume_24hr",
        tag_id: int | None = None,
    ) -> list[PredictionMarket]:
        params = {"active": "true", "closed": "false", "limit": limit, "offset": offset, "order": order}
        if tag_id:
            params["tag_id"] = tag_id
        data = await self._get("/markets", params)
        markets = data.get("markets", data if isinstance(data, list) else [])
        return [m for raw in markets if (m := _parse_market(raw))]

    async def get_market_status(self, condition_id: str) -> dict:
        data = await self._get(f"/markets/{condition_id}")
        if isinstance(data, list):
            data = data[0] if data else {}
        closed = data.get("closed", False)
        if not closed:
            return {"resolved": False, "winner": None}
        yes_price, no_price = _parse_outcome_prices(data.get("outcomePrices", '["0.5","0.5"]'))
        winner = "YES" if yes_price > 0.9 else ("NO" if no_price > 0.9 else None)
        return {"resolved": closed, "winner": winner}

    async def get_near_expiry_markets(
        self,
        hours: int = 48,
        min_liquidity: float = 1000.0,
        limit: int = 200,
    ) -> list[PredictionMarket]:
        markets = await self.get_active_markets(limit=limit)
        cutoff = datetime.now(UTC) + timedelta(hours=hours)
        return [
            m for m in markets
            if m.end_date <= cutoff
            and m.end_date > datetime.now(UTC)
            and m.liquidity >= min_liquidity
        ]
```

- [ ] **Step 4: Run tests — confirm pass**

```bash
.venv/bin/python -m pytest prediction_bot/tests/test_polymarket_client.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add prediction_bot/src/api/polymarket_client.py prediction_bot/tests/test_polymarket_client.py
git commit -m "feat(pm): add PolymarketClient (Gamma API, near-expiry scanner)"
```

---

## Task 3: Kalshi API Client

**Files:**
- Create: `prediction_bot/src/api/kalshi_client.py`
- Create: `prediction_bot/tests/test_kalshi_client.py`

- [ ] **Step 1: Write failing tests**

Create `prediction_bot/tests/test_kalshi_client.py`:

```python
"""Tests for KalshiClient."""
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from prediction_bot.src.api.models import PredictionMarket


def _make_kalshi_market(
    ticker="BTCUSD-24-T80000",
    title="Will BTC stay above $80k?",
    hours_offset=20,
    yes_bid=88,
    yes_ask=92,
    no_bid=8,
    no_ask=12,
    volume=50000,
    status="open",
    result=None,
):
    close_time = (datetime.now(timezone.utc) + timedelta(hours=hours_offset)).isoformat()
    return {
        "ticker": ticker,
        "title": title,
        "close_time": close_time,
        "yes_bid": yes_bid,
        "yes_ask": yes_ask,
        "no_bid": no_bid,
        "no_ask": no_ask,
        "volume": volume,
        "status": status,
        "result": result,
        "series_ticker": "CRYPTO",
    }


class TestKalshiClient:
    @pytest.mark.asyncio
    async def test_disabled_returns_empty(self):
        """When KALSHI_ENABLED=False, all methods return empty."""
        from prediction_bot.src.api.kalshi_client import KalshiClient
        from prediction_bot.src.config.settings import PredictionBotSettings

        settings = PredictionBotSettings(KALSHI_ENABLED=False)
        async with KalshiClient(settings=settings) as client:
            result = await client.get_near_expiry_markets()
        assert result == []

    @pytest.mark.asyncio
    async def test_price_extraction_from_cents(self):
        """Kalshi prices in cents (0-100) converted to dollars (0-1)."""
        from prediction_bot.src.api.kalshi_client import _parse_kalshi_market

        raw = _make_kalshi_market(yes_bid=88, yes_ask=92, no_bid=8, no_ask=12)
        market = _parse_kalshi_market(raw)
        assert market is not None
        assert abs(market.yes_price - 0.90) < 0.01   # midpoint of (88+92)/2 / 100
        assert abs(market.no_price - 0.10) < 0.01

    @pytest.mark.asyncio
    async def test_category_from_series(self):
        """Series ticker prefix maps to category."""
        from prediction_bot.src.api.kalshi_client import _parse_kalshi_market

        crypto_market = _make_kalshi_market(ticker="BTCUSD-T80000")
        crypto_market["series_ticker"] = "CRYPTO"
        m = _parse_kalshi_market(crypto_market)
        assert m.category == "crypto"

        politics_market = _make_kalshi_market(ticker="PRES-2024")
        politics_market["series_ticker"] = "ELECTIONS"
        m2 = _parse_kalshi_market(politics_market)
        assert m2.category == "politics"

    @pytest.mark.asyncio
    async def test_resolution_detection_settled(self):
        """Settled market with result returns resolved=True."""
        from prediction_bot.src.api.kalshi_client import KalshiClient
        from prediction_bot.src.config.settings import PredictionBotSettings

        settings = PredictionBotSettings(KALSHI_ENABLED=True, KALSHI_API_KEY="test")
        settled = _make_kalshi_market(status="settled", result="yes")

        async with KalshiClient(settings=settings) as client:
            client._token = "fake-token"
            with patch.object(client, "_get", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = settled
                status = await client.get_market_status("BTCUSD-T80000")

        assert status["resolved"] is True
        assert status["winner"] == "YES"

    @pytest.mark.asyncio
    async def test_near_expiry_filters_time(self):
        """Markets outside the expiry window are excluded."""
        from prediction_bot.src.api.kalshi_client import KalshiClient
        from prediction_bot.src.config.settings import PredictionBotSettings

        settings = PredictionBotSettings(KALSHI_ENABLED=True, KALSHI_API_KEY="test")
        inside = _make_kalshi_market(ticker="IN", hours_offset=10)
        outside = _make_kalshi_market(ticker="OUT", hours_offset=100)
        raw = {"markets": [inside, outside], "cursor": None}

        async with KalshiClient(settings=settings) as client:
            client._token = "fake-token"
            with patch.object(client, "_get_markets_raw", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = (
                    [m for m in [inside, outside]],
                    None,
                )
                markets = await client.get_near_expiry_markets(hours=48, min_volume=0)

        ids = [m.id for m in markets]
        assert "IN" in ids
        assert "OUT" not in ids
```

- [ ] **Step 2: Run — confirm fail**

```bash
.venv/bin/python -m pytest prediction_bot/tests/test_kalshi_client.py -v
```

Expected: `ModuleNotFoundError: No module named 'prediction_bot.src.api.kalshi_client'`

- [ ] **Step 3: Create `prediction_bot/src/api/kalshi_client.py`**

```python
"""Async Kalshi Exchange API v2 client."""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import httpx

from prediction_bot.src.api.models import PredictionMarket
from prediction_bot.src.config.settings import PredictionBotSettings, pm_settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
_REQUEST_DELAY = 0.2

_SERIES_CATEGORY: dict[str, str] = {
    "CRYPTO": "crypto", "BITCOIN": "crypto", "ETHEREUM": "crypto",
    "NFL": "sports", "NBA": "sports", "MLB": "sports", "NHL": "sports", "SOCCER": "sports",
    "ELECTIONS": "politics", "CONGRESS": "politics", "PRESIDENT": "politics",
    "SCOTUS": "politics", "GOVERNMENT": "politics",
}


def _parse_kalshi_market(raw: dict) -> PredictionMarket | None:
    try:
        close_time = datetime.fromisoformat(raw["close_time"].replace("Z", "+00:00"))
        yes_price = ((raw.get("yes_bid", 50) + raw.get("yes_ask", 50)) / 2) / 100
        no_price = ((raw.get("no_bid", 50) + raw.get("no_ask", 50)) / 2) / 100
        series = raw.get("series_ticker", "").upper()
        category = "politics"
        for prefix, cat in _SERIES_CATEGORY.items():
            if series.startswith(prefix):
                category = cat
                break
        return PredictionMarket(
            id=raw["ticker"],
            platform="kalshi",
            question=raw.get("title", raw.get("ticker", "")),
            category=category,
            end_date=close_time,
            yes_price=yes_price,
            no_price=no_price,
            volume_24h=float(raw.get("volume", 0) or 0),
            liquidity=float(raw.get("volume", 0) or 0),
            slug=raw.get("ticker", ""),
            metadata={"series_ticker": raw.get("series_ticker"), "status": raw.get("status")},
        )
    except Exception as e:
        logger.debug("Failed to parse Kalshi market %s: %s", raw.get("ticker"), e)
        return None


class KalshiClient:
    def __init__(self, settings: PredictionBotSettings = pm_settings):
        self._settings = settings
        self._session: httpx.AsyncClient | None = None
        self._token: str | None = None

    async def __aenter__(self):
        self._session = httpx.AsyncClient(base_url=BASE_URL, timeout=15.0)
        return self

    async def __aexit__(self, *_):
        if self._session:
            await self._session.aclose()

    async def _login(self):
        if not self._settings.KALSHI_API_KEY:
            return
        try:
            resp = await self._session.post(
                "/log-in",
                json={"email": self._settings.KALSHI_API_KEY, "password": self._settings.KALSHI_API_SECRET},
            )
            resp.raise_for_status()
            self._token = resp.json().get("token")
        except Exception as e:
            logger.warning("Kalshi login failed: %s", e)

    def _headers(self) -> dict:
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    async def _get(self, path: str, params: dict | None = None) -> dict:
        await asyncio.sleep(_REQUEST_DELAY)
        for attempt in range(3):
            try:
                resp = await self._session.get(path, params=params, headers=self._headers())
                if resp.status_code == 401:
                    await self._login()
                    continue
                if resp.status_code == 429:
                    await asyncio.sleep(5 * (2 ** attempt))
                    continue
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                logger.warning("Kalshi HTTP error %s for %s: %s", e.response.status_code, path, e)
                return {}
        return {}

    async def _get_markets_raw(
        self, cursor: str | None = None, limit: int = 200
    ) -> tuple[list[dict], str | None]:
        params: dict = {"status": "open", "limit": limit}
        if cursor:
            params["cursor"] = cursor
        data = await self._get("/markets", params)
        return data.get("markets", []), data.get("cursor")

    async def get_market_status(self, ticker: str) -> dict:
        data = await self._get(f"/markets/{ticker}")
        status = data.get("status", "open")
        result = data.get("result")
        if status in ("settled", "finalized") and result:
            return {"resolved": True, "winner": result.upper()}
        return {"resolved": False, "winner": None}

    async def get_near_expiry_markets(
        self,
        hours: int = 48,
        min_volume: float = 1000.0,
        limit: int = 200,
    ) -> list[PredictionMarket]:
        if not self._settings.KALSHI_ENABLED:
            return []
        if not self._token:
            await self._login()
        raw_markets, _ = await self._get_markets_raw(limit=limit)
        cutoff = datetime.now(UTC) + timedelta(hours=hours)
        now = datetime.now(UTC)
        results = []
        for raw in raw_markets:
            m = _parse_kalshi_market(raw)
            if m and m.end_date <= cutoff and m.end_date > now and m.liquidity >= min_volume:
                results.append(m)
        return results
```

- [ ] **Step 4: Run tests — confirm pass**

```bash
.venv/bin/python -m pytest prediction_bot/tests/test_kalshi_client.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add prediction_bot/src/api/kalshi_client.py prediction_bot/tests/test_kalshi_client.py
git commit -m "feat(pm): add KalshiClient (auth, near-expiry scanner, graceful disable)"
```

---

## Task 4: Market Scanner

**Files:**
- Create: `prediction_bot/src/bot/scanner.py`
- Create: `prediction_bot/tests/test_scanner.py`

- [ ] **Step 1: Write failing tests**

Create `prediction_bot/tests/test_scanner.py`:

```python
"""Tests for scan_markets()."""
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch
import pytest

from prediction_bot.src.api.models import PredictionMarket, MarketCandidate
from prediction_bot.src.config.settings import PredictionBotSettings


def _market(
    id="m1",
    platform="polymarket",
    question="Will BTC hit $90k?",
    category="crypto",
    hours_offset=20,
    yes_price=0.92,
    liquidity=5000.0,
):
    return PredictionMarket(
        id=id,
        platform=platform,
        question=question,
        category=category,
        end_date=datetime.now(timezone.utc) + timedelta(hours=hours_offset),
        yes_price=yes_price,
        no_price=round(1 - yes_price, 2),
        liquidity=liquidity,
    )


@pytest.fixture
def settings():
    return PredictionBotSettings(
        HIGH_PROB_MIN=0.80,
        HIGH_PROB_MAX=0.97,
        MIN_LIQUIDITY=1000.0,
        EXPIRY_WINDOW_HOURS=48,
        ENABLED_CATEGORIES=["crypto", "sports", "politics"],
    )


class TestScanMarkets:
    @pytest.mark.asyncio
    async def test_filters_low_liquidity(self, settings):
        """Markets below MIN_LIQUIDITY are excluded."""
        from prediction_bot.src.bot.scanner import scan_markets

        low_liq = _market(id="low", liquidity=500.0)
        ok = _market(id="ok", liquidity=2000.0)

        poly_mock = AsyncMock()
        poly_mock.get_near_expiry_markets = AsyncMock(return_value=[low_liq, ok])
        kalshi_mock = AsyncMock()
        kalshi_mock.get_near_expiry_markets = AsyncMock(return_value=[])

        result = await scan_markets(poly_mock, kalshi_mock, settings)
        ids = [c.market.id for c in result]
        assert "ok" in ids
        assert "low" not in ids

    @pytest.mark.asyncio
    async def test_filters_price_below_range(self, settings):
        """Markets with best_price below HIGH_PROB_MIN excluded."""
        from prediction_bot.src.bot.scanner import scan_markets

        cheap = _market(id="cheap", yes_price=0.60)
        good = _market(id="good", yes_price=0.90)

        poly_mock = AsyncMock()
        poly_mock.get_near_expiry_markets = AsyncMock(return_value=[cheap, good])
        kalshi_mock = AsyncMock()
        kalshi_mock.get_near_expiry_markets = AsyncMock(return_value=[])

        result = await scan_markets(poly_mock, kalshi_mock, settings)
        ids = [c.market.id for c in result]
        assert "good" in ids
        assert "cheap" not in ids

    @pytest.mark.asyncio
    async def test_filters_price_above_range(self, settings):
        """Markets with best_price above HIGH_PROB_MAX excluded (too certain = no edge)."""
        from prediction_bot.src.bot.scanner import scan_markets

        too_high = _market(id="high", yes_price=0.99)
        good = _market(id="good", yes_price=0.91)

        poly_mock = AsyncMock()
        poly_mock.get_near_expiry_markets = AsyncMock(return_value=[too_high, good])
        kalshi_mock = AsyncMock()
        kalshi_mock.get_near_expiry_markets = AsyncMock(return_value=[])

        result = await scan_markets(poly_mock, kalshi_mock, settings)
        ids = [c.market.id for c in result]
        assert "good" in ids
        assert "high" not in ids

    @pytest.mark.asyncio
    async def test_best_side_yes(self, settings):
        """best_side=YES when yes_price > no_price."""
        from prediction_bot.src.bot.scanner import scan_markets

        poly_mock = AsyncMock()
        poly_mock.get_near_expiry_markets = AsyncMock(return_value=[_market(yes_price=0.92)])
        kalshi_mock = AsyncMock()
        kalshi_mock.get_near_expiry_markets = AsyncMock(return_value=[])

        result = await scan_markets(poly_mock, kalshi_mock, settings)
        assert result[0].best_side == "YES"
        assert abs(result[0].market_price - 0.92) < 0.001

    @pytest.mark.asyncio
    async def test_best_side_no(self, settings):
        """best_side=NO when no_price > yes_price (long-shot YES, near-certain NO)."""
        from prediction_bot.src.bot.scanner import scan_markets

        m = _market(yes_price=0.08)  # no_price = 0.92
        poly_mock = AsyncMock()
        poly_mock.get_near_expiry_markets = AsyncMock(return_value=[m])
        kalshi_mock = AsyncMock()
        kalshi_mock.get_near_expiry_markets = AsyncMock(return_value=[])

        result = await scan_markets(poly_mock, kalshi_mock, settings)
        assert len(result) == 1
        assert result[0].best_side == "NO"
        assert abs(result[0].market_price - 0.92) < 0.001

    @pytest.mark.asyncio
    async def test_filters_disabled_category(self, settings):
        """Markets in disabled categories excluded."""
        from prediction_bot.src.bot.scanner import scan_markets

        s = PredictionBotSettings(
            HIGH_PROB_MIN=0.80, HIGH_PROB_MAX=0.97, MIN_LIQUIDITY=0,
            EXPIRY_WINDOW_HOURS=48, ENABLED_CATEGORIES=["crypto"],
        )
        sports_market = _market(id="sports", category="sports")
        crypto_market = _market(id="crypto", category="crypto")

        poly_mock = AsyncMock()
        poly_mock.get_near_expiry_markets = AsyncMock(return_value=[sports_market, crypto_market])
        kalshi_mock = AsyncMock()
        kalshi_mock.get_near_expiry_markets = AsyncMock(return_value=[])

        result = await scan_markets(poly_mock, kalshi_mock, s)
        ids = [c.market.id for c in result]
        assert "crypto" in ids
        assert "sports" not in ids

    @pytest.mark.asyncio
    async def test_ranked_by_edge_potential(self, settings):
        """Higher edge_potential candidates ranked first."""
        from prediction_bot.src.bot.scanner import scan_markets

        # lower price = more potential upside = higher edge_potential
        high_edge = _market(id="hedge", yes_price=0.82, liquidity=10000)
        low_edge = _market(id="ledge", yes_price=0.95, liquidity=1000)

        poly_mock = AsyncMock()
        poly_mock.get_near_expiry_markets = AsyncMock(return_value=[low_edge, high_edge])
        kalshi_mock = AsyncMock()
        kalshi_mock.get_near_expiry_markets = AsyncMock(return_value=[])

        result = await scan_markets(poly_mock, kalshi_mock, settings)
        assert result[0].market.id == "hedge"

    @pytest.mark.asyncio
    async def test_single_platform_kalshi_none(self, settings):
        """Works when Kalshi client is None (disabled)."""
        from prediction_bot.src.bot.scanner import scan_markets

        poly_mock = AsyncMock()
        poly_mock.get_near_expiry_markets = AsyncMock(return_value=[_market()])

        result = await scan_markets(poly_mock, None, settings)
        assert len(result) == 1
```

- [ ] **Step 2: Run — confirm fail**

```bash
.venv/bin/python -m pytest prediction_bot/tests/test_scanner.py -v
```

Expected: `ModuleNotFoundError: No module named 'prediction_bot.src.bot.scanner'`

- [ ] **Step 3: Create `prediction_bot/src/bot/scanner.py`**

```python
"""Market scanner — filters and ranks MarketCandidate list from both platforms."""
from __future__ import annotations

import logging
import math

from prediction_bot.src.api.models import MarketCandidate, PredictionMarket
from prediction_bot.src.config.settings import PredictionBotSettings

logger = logging.getLogger(__name__)


async def scan_markets(
    polymarket,
    kalshi,
    settings: PredictionBotSettings,
) -> list[MarketCandidate]:
    """Scan both platforms and return ranked MarketCandidate list (best first, max 50)."""
    raw: list[PredictionMarket] = []

    if polymarket:
        try:
            poly_markets = await polymarket.get_near_expiry_markets(
                hours=settings.EXPIRY_WINDOW_HOURS,
                min_liquidity=settings.MIN_LIQUIDITY,
            )
            raw.extend(poly_markets)
            logger.info("Polymarket: %d near-expiry markets fetched", len(poly_markets))
        except Exception as e:
            logger.warning("Polymarket scan error: %s", e)

    if kalshi:
        try:
            kalshi_markets = await kalshi.get_near_expiry_markets(
                hours=settings.EXPIRY_WINDOW_HOURS,
                min_volume=settings.MIN_LIQUIDITY,
            )
            raw.extend(kalshi_markets)
            logger.info("Kalshi: %d near-expiry markets fetched", len(kalshi_markets))
        except Exception as e:
            logger.warning("Kalshi scan error: %s", e)

    candidates: list[MarketCandidate] = []
    for market in raw:
        if market.category not in settings.ENABLED_CATEGORIES:
            continue
        if market.liquidity < settings.MIN_LIQUIDITY:
            continue

        best_side = "YES" if market.yes_price >= market.no_price else "NO"
        best_price = market.yes_price if best_side == "YES" else market.no_price

        if not (settings.HIGH_PROB_MIN <= best_price <= settings.HIGH_PROB_MAX):
            continue

        candidates.append(MarketCandidate(
            market=market,
            best_side=best_side,
            market_price=best_price,
        ))

    # Rank: more upside * more liquidity = more interesting
    def _score(c: MarketCandidate) -> float:
        return (1.0 - c.market_price) * math.log(c.market.liquidity + 1)

    candidates.sort(key=_score, reverse=True)
    return candidates[:50]
```

- [ ] **Step 4: Run tests — confirm pass**

```bash
.venv/bin/python -m pytest prediction_bot/tests/test_scanner.py -v
```

Expected: all 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add prediction_bot/src/bot/scanner.py prediction_bot/tests/test_scanner.py
git commit -m "feat(pm): add market scanner (filter, rank, dual-platform)"
```

---

## Task 5: Market Data Enrichment

**Files:**
- Create: `prediction_bot/src/data/market_data.py`

- [ ] **Step 1: Create `prediction_bot/src/data/market_data.py`**

No separate test file — enrichment functions are tested implicitly in Task 6's evaluator tests via mocking.

```python
"""External data enrichment for market candidates."""
from __future__ import annotations

import logging
import re

import httpx

logger = logging.getLogger(__name__)

_COINGECKO_BASE = "https://api.coingecko.com/api/v3"

_CRYPTO_SYMBOLS = {
    "btc": "bitcoin", "bitcoin": "bitcoin",
    "eth": "ethereum", "ethereum": "ethereum",
    "sol": "solana", "solana": "solana",
    "bnb": "binancecoin",
}


async def get_crypto_price(symbol: str) -> dict | None:
    """Fetch current price from CoinGecko free API. Returns None on error."""
    coin_id = _CRYPTO_SYMBOLS.get(symbol.lower(), symbol.lower())
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{_COINGECKO_BASE}/simple/price",
                params={"ids": coin_id, "vs_currencies": "usd"},
            )
            resp.raise_for_status()
            data = resp.json()
            price = data.get(coin_id, {}).get("usd")
            if price:
                return {"symbol": symbol.upper(), "price_usd": price, "coin_id": coin_id}
    except Exception as e:
        logger.debug("CoinGecko fetch failed for %s: %s", symbol, e)
    return None


async def get_crypto_context(question: str) -> str:
    """Extract crypto context for a market question."""
    question_lower = question.lower()
    for sym, coin_id in _CRYPTO_SYMBOLS.items():
        if sym in question_lower:
            price_data = await get_crypto_price(sym)
            if price_data:
                return f"Current {price_data['symbol']} price: ${price_data['price_usd']:,.2f} USD"
    return ""


async def get_sports_scores(query: str) -> str:
    """Fetch live/recent scores via ESPN public API. Returns formatted string."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
            )
            resp.raise_for_status()
            data = resp.json()
            games = data.get("events", [])[:3]
            if not games:
                return ""
            lines = []
            for g in games:
                name = g.get("name", "")
                status = g.get("status", {}).get("type", {}).get("description", "")
                lines.append(f"{name} ({status})")
            return "Recent NBA games: " + "; ".join(lines)
    except Exception as e:
        logger.debug("ESPN fetch failed: %s", e)
    return ""


async def get_news_headlines(query: str, max_results: int = 3) -> str:
    """Return placeholder — implement with a real news API if needed."""
    return ""
```

- [ ] **Step 2: Commit**

```bash
git add prediction_bot/src/data/market_data.py
git commit -m "feat(pm): add market data enrichment (CoinGecko, ESPN)"
```

---

## Task 6: LLM Evaluator

**Files:**
- Create: `prediction_bot/src/bot/evaluator.py`
- Create: `prediction_bot/tests/test_evaluator.py`

- [ ] **Step 1: Write failing tests**

Create `prediction_bot/tests/test_evaluator.py`:

```python
"""Tests for evaluate_candidates()."""
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
import pytest

from prediction_bot.src.api.models import PredictionMarket, MarketCandidate
from prediction_bot.src.config.settings import PredictionBotSettings


def _candidate(
    id="m1",
    question="Will BTC stay above $80k?",
    category="crypto",
    yes_price=0.92,
    no_price=0.08,
    platform="polymarket",
    best_side="YES",
):
    return MarketCandidate(
        market=PredictionMarket(
            id=id,
            platform=platform,
            question=question,
            category=category,
            end_date=datetime.now(timezone.utc) + timedelta(hours=20),
            yes_price=yes_price,
            no_price=no_price,
            liquidity=50000,
        ),
        best_side=best_side,
        market_price=yes_price if best_side == "YES" else no_price,
    )


@pytest.fixture
def settings():
    return PredictionBotSettings(MIN_EDGE_PCT=0.02, ANTHROPIC_API_KEY="test-key")


class TestParseEvaluatorResponse:
    def test_parses_valid_json_array(self):
        from prediction_bot.src.bot.evaluator import _parse_llm_response

        raw = '[{"market_id":"m1","true_probability":0.97,"confidence":0.85,"reasoning":"Strong signal","recommended_side":"YES"}]'
        result = _parse_llm_response(raw)
        assert len(result) == 1
        assert result[0]["market_id"] == "m1"
        assert result[0]["true_probability"] == 0.97

    def test_handles_json_in_markdown_block(self):
        from prediction_bot.src.bot.evaluator import _parse_llm_response

        raw = '```json\n[{"market_id":"m1","true_probability":0.95,"confidence":0.8,"reasoning":"ok","recommended_side":"YES"}]\n```'
        result = _parse_llm_response(raw)
        assert len(result) == 1

    def test_returns_empty_on_invalid_json(self):
        from prediction_bot.src.bot.evaluator import _parse_llm_response

        result = _parse_llm_response("not json at all")
        assert result == []


class TestEdgeCalculation:
    def test_edge_yes_side(self):
        from prediction_bot.src.bot.evaluator import _calculate_edge

        # true_prob=0.97, market_price=0.92, fee=0.02 → edge=0.03
        edge = _calculate_edge(
            true_prob=0.97,
            recommended_side="YES",
            yes_price=0.92,
            no_price=0.08,
            platform="polymarket",
        )
        assert abs(edge - 0.03) < 0.001  # 0.97 - 0.92 - 0.02

    def test_edge_no_side(self):
        from prediction_bot.src.bot.evaluator import _calculate_edge

        # true_prob=0.03 → no_prob=0.97, market_no_price=0.08, fee=0.02 → edge=0.87
        edge = _calculate_edge(
            true_prob=0.03,
            recommended_side="NO",
            yes_price=0.92,
            no_price=0.08,
            platform="polymarket",
        )
        assert abs(edge - (0.97 - 0.08 - 0.02)) < 0.001

    def test_kalshi_higher_fee(self):
        from prediction_bot.src.bot.evaluator import _calculate_edge

        poly_edge = _calculate_edge(0.97, "YES", 0.92, 0.08, "polymarket")
        kalshi_edge = _calculate_edge(0.97, "YES", 0.92, 0.08, "kalshi")
        assert kalshi_edge < poly_edge  # kalshi fee = 0.03 vs polymarket 0.02

    def test_skip_returns_zero(self):
        from prediction_bot.src.bot.evaluator import _calculate_edge

        edge = _calculate_edge(0.92, "SKIP", 0.92, 0.08, "polymarket")
        assert edge == 0.0


class TestEvaluateCandidates:
    @pytest.mark.asyncio
    async def test_returns_only_candidates_with_edge(self, settings):
        from prediction_bot.src.bot.evaluator import evaluate_candidates

        c1 = _candidate(id="m1", yes_price=0.92)  # enough room for edge
        c2 = _candidate(id="m2", yes_price=0.96)  # barely any room

        llm_response = '[{"market_id":"m1","true_probability":0.97,"confidence":0.85,"reasoning":"Strong","recommended_side":"YES"},{"market_id":"m2","true_probability":0.96,"confidence":0.5,"reasoning":"Meh","recommended_side":"SKIP"}]'

        with patch("prediction_bot.src.bot.evaluator.litellm.completion") as mock_llm:
            mock_llm.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content=llm_response))]
            )
            result = await evaluate_candidates([c1, c2], settings)

        assert len(result) == 1
        assert result[0].market.id == "m1"
        assert result[0].edge is not None
        assert result[0].edge > 0

    @pytest.mark.asyncio
    async def test_handles_malformed_llm_response(self, settings):
        from prediction_bot.src.bot.evaluator import evaluate_candidates

        c1 = _candidate(id="m1")

        with patch("prediction_bot.src.bot.evaluator.litellm.completion") as mock_llm:
            mock_llm.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="I cannot evaluate this."))]
            )
            result = await evaluate_candidates([c1], settings)

        assert result == []
```

- [ ] **Step 2: Run — confirm fail**

```bash
.venv/bin/python -m pytest prediction_bot/tests/test_evaluator.py -v
```

Expected: `ModuleNotFoundError: No module named 'prediction_bot.src.bot.evaluator'`

- [ ] **Step 3: Create `prediction_bot/src/bot/evaluator.py`**

```python
"""LLM-based market probability evaluator."""
from __future__ import annotations

import json
import logging
import re

import litellm

from prediction_bot.src.api.models import MarketCandidate
from prediction_bot.src.bot.evaluator_prompt import SYSTEM_PROMPT, build_user_prompt
from prediction_bot.src.config.settings import PredictionBotSettings
from prediction_bot.src.data.market_data import get_crypto_context, get_sports_scores

logger = logging.getLogger(__name__)

_FEES = {"polymarket": 0.02, "kalshi": 0.03}


def _parse_llm_response(raw: str) -> list[dict]:
    # Strip markdown code fences
    raw = re.sub(r"```(?:json)?\s*", "", raw).strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _calculate_edge(
    true_prob: float,
    recommended_side: str,
    yes_price: float,
    no_price: float,
    platform: str,
) -> float:
    if recommended_side == "SKIP":
        return 0.0
    fee = _FEES.get(platform, 0.02)
    if recommended_side == "YES":
        return true_prob - yes_price - fee
    else:  # NO
        return (1.0 - true_prob) - no_price - fee


async def _enrich(candidate: MarketCandidate) -> MarketCandidate:
    cat = candidate.market.category
    if cat == "crypto":
        ctx = await get_crypto_context(candidate.market.question)
        if ctx:
            candidate = candidate.model_copy(update={"external_data": {"crypto": ctx}})
    elif cat == "sports":
        ctx = await get_sports_scores(candidate.market.question)
        if ctx:
            candidate = candidate.model_copy(update={"external_data": {"sports": ctx}})
    return candidate


async def evaluate_candidates(
    candidates: list[MarketCandidate],
    settings: PredictionBotSettings,
) -> list[MarketCandidate]:
    """Enrich candidates, call LLM in batches of 10, return those with edge > MIN_EDGE_PCT."""
    enriched = []
    for c in candidates:
        enriched.append(await _enrich(c))

    results: list[MarketCandidate] = []
    batch_size = 10
    for i in range(0, len(enriched), batch_size):
        batch = enriched[i : i + batch_size]
        user_prompt = build_user_prompt(batch)
        try:
            resp = litellm.completion(
                model=settings.CLAUDE_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=2048,
                temperature=0.3,
            )
            raw = resp.choices[0].message.content
        except Exception as e:
            logger.warning("LLM evaluation failed for batch %d: %s", i // batch_size, e)
            continue

        assessments = _parse_llm_response(raw)
        assessment_map = {a["market_id"]: a for a in assessments}

        for candidate in batch:
            assessment = assessment_map.get(candidate.market.id)
            if not assessment:
                continue
            side = assessment.get("recommended_side", "SKIP")
            true_prob = float(assessment.get("true_probability", 0.5))
            edge = _calculate_edge(
                true_prob, side,
                candidate.market.yes_price,
                candidate.market.no_price,
                candidate.market.platform,
            )
            if edge > settings.MIN_EDGE_PCT:
                updated = candidate.model_copy(update={
                    "llm_true_prob": true_prob,
                    "llm_confidence": float(assessment.get("confidence", 0.5)),
                    "llm_reasoning": assessment.get("reasoning", ""),
                    "edge": edge,
                })
                results.append(updated)

    return results
```

- [ ] **Step 4: Create `prediction_bot/src/bot/evaluator_prompt.py`**

```python
"""Prompt templates for the LLM evaluator."""
from __future__ import annotations
from datetime import UTC, datetime

from prediction_bot.src.api.models import MarketCandidate

SYSTEM_PROMPT = """You are a prediction market analyst. For each market, estimate the TRUE probability of YES based on:
1. The market question and what it takes to resolve YES
2. The current market price (crowd wisdom)
3. Any external data provided
4. Your knowledge up to your training cutoff

Be calibrated. Only flag edge when you have genuine reasons. Respond with a JSON array only.
For each market: {"market_id": "...", "true_probability": 0.0-1.0, "confidence": 0.0-1.0, "reasoning": "...", "recommended_side": "YES"|"NO"|"SKIP"}"""


def build_user_prompt(candidates: list[MarketCandidate]) -> str:
    lines = ["=== MARKETS TO EVALUATE ===\n"]
    now = datetime.now(UTC)
    for i, c in enumerate(candidates, 1):
        hours_left = max(0, (c.market.end_date - now).total_seconds() / 3600)
        lines.append(f"Market {i} (id: {c.market.id})")
        lines.append(f'  Question: "{c.market.question}"')
        lines.append(f"  Platform: {c.market.platform} | Category: {c.market.category}")
        lines.append(f"  Expires in: {hours_left:.1f}h")
        lines.append(f"  YES price: ${c.market.yes_price:.2f} | NO price: ${c.market.no_price:.2f}")
        lines.append(f"  Our best side: {c.best_side} @ ${c.market_price:.2f}")
        lines.append(f"  Liquidity: ${c.market.liquidity:,.0f}")
        if c.external_data:
            for k, v in c.external_data.items():
                lines.append(f"  {k.title()} data: {v}")
        lines.append("")
    lines.append("Respond with JSON array only. SKIP when edge < 2%.")
    return "\n".join(lines)
```

- [ ] **Step 5: Run tests — confirm pass**

```bash
.venv/bin/python -m pytest prediction_bot/tests/test_evaluator.py -v
```

Expected: all 7 tests pass.

- [ ] **Step 6: Commit**

```bash
git add prediction_bot/src/bot/evaluator.py prediction_bot/src/bot/evaluator_prompt.py prediction_bot/tests/test_evaluator.py
git commit -m "feat(pm): add LLM evaluator (edge calc, batch evaluation, enrichment)"
```

---

## Task 7: Result Store

**Files:**
- Create: `prediction_bot/src/data/result_store.py`
- Create: `prediction_bot/tests/test_result_store.py`

- [ ] **Step 1: Write failing tests**

Create `prediction_bot/tests/test_result_store.py`:

```python
"""Tests for ResultStore (aiosqlite)."""
import pytest
from datetime import datetime, timezone

from prediction_bot.src.api.models import PaperTrade


def _trade(**kwargs) -> PaperTrade:
    defaults = dict(
        platform="polymarket",
        market_id="m1",
        market_question="Will BTC stay above $80k?",
        category="crypto",
        side="YES",
        entry_price=0.92,
        quantity=10.0,
        cost=9.2,
        confidence=0.85,
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    return PaperTrade(**defaults)


@pytest.fixture
async def store(tmp_path):
    from prediction_bot.src.data.result_store import ResultStore
    s = ResultStore(str(tmp_path / "test.db"))
    await s.initialize()
    return s


class TestResultStore:
    @pytest.mark.asyncio
    async def test_creates_tables(self, tmp_path):
        """initialize() creates paper_trades and bankroll_snapshots tables."""
        import aiosqlite
        from prediction_bot.src.data.result_store import ResultStore

        db_path = str(tmp_path / "test.db")
        s = ResultStore(db_path)
        await s.initialize()

        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT name FROM sqlite_master WHERE type='table'") as cur:
                tables = {row[0] async for row in cur}
        assert "paper_trades" in tables
        assert "bankroll_snapshots" in tables

    @pytest.mark.asyncio
    async def test_add_and_fetch_trade(self, store):
        """add_trade returns ID; get_open_trades returns the trade."""
        trade_id = await store.add_trade(_trade(), initial_bankroll=1000.0)
        assert isinstance(trade_id, int)

        open_trades = await store.get_open_trades()
        assert len(open_trades) == 1
        assert open_trades[0].market_id == "m1"

    @pytest.mark.asyncio
    async def test_settle_trade_won(self, store):
        """settle_trade(won=True): pnl = (1-entry)*qty, status=WON."""
        trade_id = await store.add_trade(_trade(entry_price=0.92, quantity=10.0), initial_bankroll=1000.0)
        await store.settle_trade(trade_id, won=True)

        trades = await store.get_recent_trades()
        t = trades[0]
        assert t.status == "WON"
        assert abs(t.pnl - (1.0 - 0.92) * 10.0) < 0.001  # 0.08 * 10 = 0.80

    @pytest.mark.asyncio
    async def test_settle_trade_lost(self, store):
        """settle_trade(won=False): pnl = -entry*qty, status=LOST."""
        trade_id = await store.add_trade(_trade(entry_price=0.92, quantity=10.0), initial_bankroll=1000.0)
        await store.settle_trade(trade_id, won=False)

        trades = await store.get_recent_trades()
        t = trades[0]
        assert t.status == "LOST"
        assert abs(t.pnl - (-0.92 * 10.0)) < 0.001  # -9.20

    @pytest.mark.asyncio
    async def test_get_stats_win_rate(self, store):
        """get_stats computes win_rate correctly."""
        t1 = await store.add_trade(_trade(market_id="m1", cost=9.2), initial_bankroll=1000.0)
        t2 = await store.add_trade(_trade(market_id="m2", cost=9.2), initial_bankroll=1000.0)
        await store.settle_trade(t1, won=True)
        await store.settle_trade(t2, won=False)

        stats = await store.get_stats()
        assert stats["total_trades"] == 2
        assert stats["won"] == 1
        assert stats["lost"] == 1
        assert abs(stats["win_rate"] - 0.5) < 0.001

    @pytest.mark.asyncio
    async def test_get_bankroll_decreases_after_trade(self, store):
        """Bankroll decremented by trade cost after add_trade."""
        await store.add_trade(_trade(cost=9.2), initial_bankroll=1000.0)
        bankroll = await store.get_bankroll()
        assert abs(bankroll - (1000.0 - 9.2)) < 0.001
```

- [ ] **Step 2: Run — confirm fail**

```bash
.venv/bin/python -m pytest prediction_bot/tests/test_result_store.py -v
```

Expected: `ModuleNotFoundError: No module named 'prediction_bot.src.data.result_store'`

- [ ] **Step 3: Create `prediction_bot/src/data/result_store.py`**

```python
"""aiosqlite persistence for paper trades and bankroll."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

import aiosqlite

from prediction_bot.src.api.models import BankrollSnapshot, PaperTrade

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    market_id TEXT NOT NULL,
    market_question TEXT NOT NULL,
    category TEXT NOT NULL,
    side TEXT NOT NULL,
    entry_price REAL NOT NULL,
    quantity REAL NOT NULL,
    cost REAL NOT NULL,
    confidence REAL NOT NULL,
    reasoning TEXT,
    status TEXT NOT NULL DEFAULT 'OPEN',
    exit_price REAL,
    pnl REAL,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    resolution_source TEXT
);

CREATE TABLE IF NOT EXISTS bankroll_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    balance REAL NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    trade_id INTEGER REFERENCES paper_trades(id)
);

CREATE INDEX IF NOT EXISTS idx_trades_status ON paper_trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_created ON paper_trades(created_at);
"""


class ResultStore:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()

    async def add_trade(self, trade: PaperTrade, initial_bankroll: float | None = None) -> int:
        """Insert trade, deduct cost from bankroll, return trade ID."""
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """INSERT INTO paper_trades
                   (platform, market_id, market_question, category, side, entry_price,
                    quantity, cost, confidence, reasoning, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    trade.platform, trade.market_id, trade.market_question,
                    trade.category, trade.side, trade.entry_price,
                    trade.quantity, trade.cost, trade.confidence,
                    trade.reasoning, trade.created_at.isoformat(),
                ),
            )
            trade_id = cur.lastrowid

            # Update bankroll: deduct cost
            current = await self._get_bankroll_tx(db, initial_bankroll)
            new_balance = current - trade.cost
            await db.execute(
                "INSERT INTO bankroll_snapshots (balance, trade_id) VALUES (?, ?)",
                (new_balance, trade_id),
            )
            await db.commit()
        return trade_id

    async def _get_bankroll_tx(self, db: aiosqlite.Connection, initial: float | None) -> float:
        async with db.execute("SELECT balance FROM bankroll_snapshots ORDER BY id DESC LIMIT 1") as cur:
            row = await cur.fetchone()
        if row:
            return row[0]
        return initial or 1000.0

    async def get_open_trades(self) -> list[PaperTrade]:
        return await self._fetch_trades("WHERE status = 'OPEN'")

    async def settle_trade(self, trade_id: int, won: bool):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT entry_price, quantity, cost FROM paper_trades WHERE id=?", (trade_id,)
            ) as cur:
                row = await cur.fetchone()
            if not row:
                return
            entry_price, quantity, cost = row
            pnl = (1.0 - entry_price) * quantity if won else (-entry_price * quantity)
            status = "WON" if won else "LOST"
            exit_price = 1.0 if won else 0.0
            await db.execute(
                """UPDATE paper_trades SET status=?, exit_price=?, pnl=?, resolved_at=?
                   WHERE id=?""",
                (status, exit_price, pnl, datetime.now(UTC).isoformat(), trade_id),
            )
            current = await self._get_bankroll_tx(db, None)
            credit = cost + pnl  # refund cost + pnl
            await db.execute(
                "INSERT INTO bankroll_snapshots (balance, trade_id) VALUES (?, ?)",
                (current + credit, trade_id),
            )
            await db.commit()

    async def expire_trade(self, trade_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT cost FROM paper_trades WHERE id=?", (trade_id,)
            ) as cur:
                row = await cur.fetchone()
            if not row:
                return
            cost = row[0]
            await db.execute(
                "UPDATE paper_trades SET status='EXPIRED', pnl=0, resolved_at=? WHERE id=?",
                (datetime.now(UTC).isoformat(), trade_id),
            )
            current = await self._get_bankroll_tx(db, None)
            await db.execute(
                "INSERT INTO bankroll_snapshots (balance, trade_id) VALUES (?, ?)",
                (current + cost, trade_id),
            )
            await db.commit()

    async def get_bankroll(self) -> float:
        async with aiosqlite.connect(self.db_path) as db:
            return await self._get_bankroll_tx(db, None)

    async def get_stats(self) -> dict:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT status, SUM(pnl), COUNT(*) FROM paper_trades GROUP BY status"
            ) as cur:
                rows = await cur.fetchall()

        counts = {"WON": 0, "LOST": 0, "EXPIRED": 0, "OPEN": 0}
        pnl_total = 0.0
        for status, pnl_sum, cnt in rows:
            counts[status] = cnt
            if pnl_sum:
                pnl_total += pnl_sum

        total = sum(counts.values())
        settled = counts["WON"] + counts["LOST"]
        win_rate = counts["WON"] / settled if settled > 0 else None
        bankroll = await self.get_bankroll()

        return {
            "total_trades": total,
            "open_trades": counts["OPEN"],
            "won": counts["WON"],
            "lost": counts["LOST"],
            "expired": counts["EXPIRED"],
            "win_rate": win_rate,
            "total_pnl": pnl_total,
            "roi": pnl_total / 1000.0 if total > 0 else 0.0,
            "bankroll": bankroll,
        }

    async def get_recent_trades(self, limit: int = 50) -> list[PaperTrade]:
        return await self._fetch_trades(f"ORDER BY created_at DESC LIMIT {limit}")

    async def get_bankroll_history(self, limit: int = 100) -> list[BankrollSnapshot]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                f"SELECT id, balance, timestamp, trade_id FROM bankroll_snapshots ORDER BY id DESC LIMIT {limit}"
            ) as cur:
                rows = await cur.fetchall()
        return [
            BankrollSnapshot(id=r[0], balance=r[1], timestamp=datetime.fromisoformat(r[2]), trade_id=r[3])
            for r in rows
        ]

    async def _fetch_trades(self, where_clause: str) -> list[PaperTrade]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                f"""SELECT id, platform, market_id, market_question, category, side,
                           entry_price, quantity, cost, confidence, reasoning,
                           status, exit_price, pnl, created_at, resolved_at, resolution_source
                    FROM paper_trades {where_clause}"""
            ) as cur:
                rows = await cur.fetchall()
        return [
            PaperTrade(
                id=r[0], platform=r[1], market_id=r[2], market_question=r[3],
                category=r[4], side=r[5], entry_price=r[6], quantity=r[7],
                cost=r[8], confidence=r[9], reasoning=r[10], status=r[11],
                exit_price=r[12], pnl=r[13],
                created_at=datetime.fromisoformat(r[14]),
                resolved_at=datetime.fromisoformat(r[15]) if r[15] else None,
                resolution_source=r[16],
            )
            for r in rows
        ]
```

- [ ] **Step 4: Add `asyncio_mode` to pytest for async tests**

Check if pytest-asyncio is configured:

```bash
grep -r "asyncio_mode" /Users/pkhaninejad/Desktop/apps/Claude-trade-bot/ 2>/dev/null || echo "not found"
```

If not found, create `prediction_bot/tests/conftest.py`:

```python
import pytest

pytest_plugins = ['pytest_asyncio']
```

And add a `pyproject.toml` at the repo root (or add to existing):

```bash
cat >> pyproject.toml << 'EOF' 2>/dev/null || cat > pyproject.toml << 'EOF'
[tool.pytest.ini_options]
asyncio_mode = "auto"
EOF
```

- [ ] **Step 5: Run tests — confirm pass**

```bash
.venv/bin/python -m pytest prediction_bot/tests/test_result_store.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 6: Commit**

```bash
git add prediction_bot/src/data/result_store.py prediction_bot/tests/test_result_store.py pyproject.toml
git commit -m "feat(pm): add ResultStore (aiosqlite persistence, bankroll tracking)"
```

---

## Task 8: Paper Trader

**Files:**
- Create: `prediction_bot/src/bot/paper_trader.py`
- Create: `prediction_bot/tests/test_paper_trader.py`

- [ ] **Step 1: Write failing tests**

Create `prediction_bot/tests/test_paper_trader.py`:

```python
"""Tests for PaperTrader."""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

from prediction_bot.src.api.models import PredictionMarket, MarketCandidate, PaperTrade
from prediction_bot.src.config.settings import PredictionBotSettings


def _candidate(market_id="m1", yes_price=0.92, category="crypto", platform="polymarket"):
    return MarketCandidate(
        market=PredictionMarket(
            id=market_id,
            platform=platform,
            question=f"Test question {market_id}?",
            category=category,
            end_date=datetime.now(timezone.utc) + timedelta(hours=20),
            yes_price=yes_price,
            no_price=round(1 - yes_price, 2),
            liquidity=50000,
        ),
        best_side="YES",
        market_price=yes_price,
        llm_true_prob=0.97,
        llm_confidence=0.85,
        llm_reasoning="Strong signal",
        edge=0.03,
    )


@pytest.fixture
async def trader(tmp_path):
    from prediction_bot.src.data.result_store import ResultStore
    from prediction_bot.src.bot.paper_trader import PaperTrader

    settings = PredictionBotSettings(
        VIRTUAL_BANKROLL=1000.0,
        MAX_POSITION_PCT=0.10,
        MAX_OPEN_POSITIONS=5,
    )
    store = ResultStore(str(tmp_path / "test.db"))
    pt = PaperTrader(store=store, settings=settings)
    await pt.initialize()
    return pt


class TestPaperTrader:
    @pytest.mark.asyncio
    async def test_place_trade_success(self, trader):
        """Trade placed, bankroll deducted."""
        c = _candidate()
        trade = await trader.place_paper_trade(c)
        assert trade is not None
        assert trade.side == "YES"
        assert trade.entry_price == 0.92
        bankroll = await trader.store.get_bankroll()
        assert bankroll < 1000.0

    @pytest.mark.asyncio
    async def test_quantity_calculation(self, trader):
        """Quantity = (bankroll * MAX_POSITION_PCT) / entry_price."""
        c = _candidate(yes_price=0.92)
        trade = await trader.place_paper_trade(c)
        # max_allocation = 1000 * 0.10 = 100; qty = floor(100/0.92) = 108
        assert trade.quantity == int(100.0 / 0.92)

    @pytest.mark.asyncio
    async def test_place_trade_duplicate_market_rejected(self, trader):
        """Second trade for same market_id is rejected."""
        c = _candidate(market_id="dup")
        trade1 = await trader.place_paper_trade(c)
        trade2 = await trader.place_paper_trade(c)
        assert trade1 is not None
        assert trade2 is None

    @pytest.mark.asyncio
    async def test_place_trade_max_positions_rejected(self, trader):
        """Trade rejected when open positions at MAX_OPEN_POSITIONS."""
        for i in range(5):
            await trader.place_paper_trade(_candidate(market_id=f"m{i}"))
        extra = await trader.place_paper_trade(_candidate(market_id="extra"))
        assert extra is None

    @pytest.mark.asyncio
    async def test_settle_open_trades_won(self, trader):
        """Winning settlement updates bankroll and status."""
        c = _candidate()
        trade = await trader.place_paper_trade(c)
        bankroll_before = await trader.store.get_bankroll()

        poly_mock = AsyncMock()
        poly_mock.get_market_status = AsyncMock(return_value={"resolved": True, "winner": "YES"})

        await trader.settle_open_trades(polymarket=poly_mock, kalshi=None)

        bankroll_after = await trader.store.get_bankroll()
        assert bankroll_after > bankroll_before
        open_trades = await trader.store.get_open_trades()
        assert len(open_trades) == 0
```

- [ ] **Step 2: Run — confirm fail**

```bash
.venv/bin/python -m pytest prediction_bot/tests/test_paper_trader.py -v
```

Expected: `ModuleNotFoundError: No module named 'prediction_bot.src.bot.paper_trader'`

- [ ] **Step 3: Create `prediction_bot/src/bot/paper_trader.py`**

```python
"""Paper trading state machine on top of ResultStore."""
from __future__ import annotations

import logging
import math
from datetime import UTC, datetime, timedelta

from prediction_bot.src.api.models import MarketCandidate, PaperTrade
from prediction_bot.src.config.settings import PredictionBotSettings
from prediction_bot.src.data.result_store import ResultStore

logger = logging.getLogger(__name__)


class PaperTrader:
    def __init__(self, store: ResultStore, settings: PredictionBotSettings):
        self.store = store
        self.settings = settings

    async def initialize(self):
        await self.store.initialize()
        stats = await self.store.get_stats()
        if stats["total_trades"] > 0:
            self._log_summary(stats)

    def _log_summary(self, stats: dict):
        logger.info("=" * 60)
        logger.info("PREVIOUS RESULTS SUMMARY")
        logger.info("  Total trades: %d", stats["total_trades"])
        wr = f"{stats['win_rate']:.1%}" if stats["win_rate"] is not None else "N/A"
        logger.info("  Win rate: %s (%dW / %dL / %dE)", wr, stats["won"], stats["lost"], stats["expired"])
        logger.info("  Total P&L: $%.2f", stats["total_pnl"])
        logger.info("  ROI: %.1f%%", stats["roi"] * 100)
        logger.info("  Current bankroll: $%.2f", stats["bankroll"])
        logger.info("=" * 60)

    async def place_paper_trade(self, candidate: MarketCandidate) -> PaperTrade | None:
        """Place a paper trade if constraints are met. Returns PaperTrade or None."""
        bankroll = await self.store.get_bankroll()
        open_trades = await self.store.get_open_trades()

        if len(open_trades) >= self.settings.MAX_OPEN_POSITIONS:
            logger.debug("Max positions reached, skipping %s", candidate.market.id)
            return None

        existing_ids = {t.market_id for t in open_trades}
        if candidate.market.id in existing_ids:
            logger.debug("Already holding %s, skipping", candidate.market.id)
            return None

        max_allocation = bankroll * self.settings.MAX_POSITION_PCT
        entry_price = candidate.market_price
        if entry_price <= 0:
            return None

        quantity = int(max_allocation / entry_price)
        if quantity < 1:
            logger.debug("Insufficient bankroll for %s", candidate.market.id)
            return None

        cost = entry_price * quantity

        trade = PaperTrade(
            platform=candidate.market.platform,
            market_id=candidate.market.id,
            market_question=candidate.market.question,
            category=candidate.market.category,
            side=candidate.best_side,
            entry_price=entry_price,
            quantity=float(quantity),
            cost=cost,
            confidence=candidate.llm_confidence or 0.5,
            reasoning=candidate.llm_reasoning,
            created_at=datetime.now(UTC),
        )
        trade_id = await self.store.add_trade(trade, initial_bankroll=bankroll)
        trade = trade.model_copy(update={"id": trade_id})
        logger.info(
            "Paper trade: %s '%s' @ $%.2f (qty=%d, cost=$%.2f)",
            trade.side, trade.market_question[:60], trade.entry_price, quantity, cost,
        )
        return trade

    async def settle_open_trades(self, polymarket, kalshi):
        """Check open trades for resolution and settle them."""
        open_trades = await self.store.get_open_trades()
        now = datetime.now(UTC)

        for trade in open_trades:
            try:
                client = polymarket if trade.platform == "polymarket" else kalshi
                if not client:
                    continue

                status = await client.get_market_status(trade.market_id)
                if status["resolved"] and status["winner"]:
                    won = status["winner"] == trade.side
                    await self.store.settle_trade(trade.id, won=won)
                    result = "WON" if won else "LOST"
                    logger.info("SETTLED %s: '%s' → %s", trade.market_id, trade.market_question[:50], result)

                elif trade.resolved_at is None and now > trade.created_at + timedelta(hours=72):
                    await self.store.expire_trade(trade.id)
                    logger.info("EXPIRED %s: '%s'", trade.market_id, trade.market_question[:50])

            except Exception as e:
                logger.warning("Settlement check failed for %s: %s", trade.market_id, e)
```

- [ ] **Step 4: Run tests — confirm pass**

```bash
.venv/bin/python -m pytest prediction_bot/tests/test_paper_trader.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 5: Run full prediction_bot test suite**

```bash
.venv/bin/python -m pytest prediction_bot/tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add prediction_bot/src/bot/paper_trader.py prediction_bot/tests/test_paper_trader.py
git commit -m "feat(pm): add PaperTrader (bankroll mgmt, position limits, settlement)"
```

---

## Task 9: Engine, Dashboard, Docker

**Files:**
- Create: `prediction_bot/src/bot/engine.py`
- Modify: `prediction_bot/src/dashboard/app.py` (replace stub)
- Create: `prediction_bot/src/dashboard/templates/dashboard.html`
- Create: `prediction_bot/Dockerfile`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Create `prediction_bot/src/bot/engine.py`**

```python
"""PredictionEngine — orchestrates scan → evaluate → trade cycle."""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from prediction_bot.src.api.kalshi_client import KalshiClient
from prediction_bot.src.api.models import PMBotStatus
from prediction_bot.src.api.polymarket_client import PolymarketClient
from prediction_bot.src.bot.evaluator import evaluate_candidates
from prediction_bot.src.bot.paper_trader import PaperTrader
from prediction_bot.src.bot.scanner import scan_markets
from prediction_bot.src.config.settings import pm_settings
from prediction_bot.src.data.result_store import ResultStore

logger = logging.getLogger(__name__)


class PredictionEngine:
    def __init__(self):
        self.settings = pm_settings
        self.polymarket = PolymarketClient() if self.settings.POLYMARKET_ENABLED else None
        self.kalshi = KalshiClient() if self.settings.KALSHI_ENABLED else None
        store = ResultStore(self.settings.PM_DB_PATH)
        self.paper_trader = PaperTrader(store=store, settings=self.settings)
        self.status = PMBotStatus(
            platforms={
                "polymarket": self.settings.POLYMARKET_ENABLED,
                "kalshi": self.settings.KALSHI_ENABLED,
            },
            categories=self.settings.ENABLED_CATEGORIES,
            bankroll=self.settings.VIRTUAL_BANKROLL,
        )
        self._running = False
        self.scan_history: list[dict] = []
        self._sse_queues: list[asyncio.Queue] = []

    async def start(self):
        await self.paper_trader.initialize()
        async with (
            (self.polymarket or _noop_ctx()) as poly,
            (self.kalshi or _noop_ctx()) as kalshi,
        ):
            self._poly_client = poly if self.settings.POLYMARKET_ENABLED else None
            self._kalshi_client = kalshi if self.settings.KALSHI_ENABLED else None
            self._running = True
            logger.info(
                "Prediction Market Bot started — Polymarket=%s Kalshi=%s",
                self.settings.POLYMARKET_ENABLED, self.settings.KALSHI_ENABLED,
            )
            while self._running:
                if self.status.enabled:
                    try:
                        await self._cycle()
                    except Exception as e:
                        logger.error("Cycle error: %s", e, exc_info=True)
                await asyncio.sleep(self.settings.SCAN_INTERVAL_SECONDS)

    async def _cycle(self):
        logger.info("Starting scan cycle...")

        await self.paper_trader.settle_open_trades(self._poly_client, self._kalshi_client)

        candidates = await scan_markets(self._poly_client, self._kalshi_client, self.settings)
        logger.info("Scanner found %d candidates", len(candidates))

        evaluated = []
        if candidates:
            evaluated = await evaluate_candidates(candidates, self.settings)
            logger.info("Evaluator found %d with edge", len(evaluated))

        trades_placed = 0
        for candidate in evaluated:
            trade = await self.paper_trader.place_paper_trade(candidate)
            if trade:
                trades_placed += 1
                await self._broadcast({"type": "trade_placed", "trade": trade.model_dump(mode="json")})

        stats = await self.paper_trader.store.get_stats()
        self.status.open_trades = stats["open_trades"]
        self.status.bankroll = stats["bankroll"]
        self.status.total_pnl = stats["total_pnl"]
        self.status.win_rate = stats["win_rate"]
        self.status.last_scan = datetime.now(UTC)
        self.status.next_scan = datetime.now(UTC) + timedelta(seconds=self.settings.SCAN_INTERVAL_SECONDS)

        scan_record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "candidates_found": len(candidates),
            "edges_found": len(evaluated),
            "trades_placed": trades_placed,
        }
        self.scan_history.append(scan_record)
        if len(self.scan_history) > 50:
            self.scan_history = self.scan_history[-50:]

        await self._broadcast({"type": "cycle_complete", "status": self.status.model_dump(mode="json")})

    async def _broadcast(self, event: dict):
        for q in list(self._sse_queues):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def stop(self):
        self._running = False

    def toggle(self) -> bool:
        self.status.enabled = not self.status.enabled
        return self.status.enabled


class _noop_ctx:
    async def __aenter__(self):
        return None
    async def __aexit__(self, *_):
        pass
```

- [ ] **Step 2: Replace stub `prediction_bot/src/dashboard/app.py`**

```python
"""FastAPI dashboard for the Prediction Market Bot."""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from prediction_bot.src.bot.engine import PredictionEngine

logger = logging.getLogger(__name__)

engine = PredictionEngine()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(engine.start())
    yield
    engine.stop()
    task.cancel()


app = FastAPI(title="Prediction Market Bot", lifespan=lifespan)


@app.get("/api/status")
async def get_status():
    return engine.status.model_dump(mode="json")


@app.post("/api/bot/toggle")
async def toggle_bot():
    enabled = engine.toggle()
    return {"enabled": enabled}


@app.get("/api/stats")
async def get_stats():
    return await engine.paper_trader.store.get_stats()


@app.get("/api/trades")
async def get_trades(limit: int = 50):
    trades = await engine.paper_trader.store.get_recent_trades(limit=limit)
    return [t.model_dump(mode="json") for t in trades]


@app.get("/api/trades/open")
async def get_open_trades():
    trades = await engine.paper_trader.store.get_open_trades()
    return [t.model_dump(mode="json") for t in trades]


@app.get("/api/bankroll-history")
async def get_bankroll_history():
    history = await engine.paper_trader.store.get_bankroll_history()
    return [s.model_dump(mode="json") for s in history]


@app.get("/api/scans")
async def get_scans():
    return list(reversed(engine.scan_history))


@app.post("/api/cycle")
async def trigger_cycle():
    asyncio.create_task(engine._cycle())
    return {"status": "cycle triggered"}


@app.get("/api/stream")
async def stream(request: Request):
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    engine._sse_queues.append(q)

    async def generator() -> AsyncGenerator[str, None]:
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield "data: {\"type\":\"ping\"}\n\n"
        finally:
            engine._sse_queues.remove(q)

    return StreamingResponse(generator(), media_type="text/event-stream")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    stats = await engine.paper_trader.store.get_stats()
    trades = await engine.paper_trader.store.get_recent_trades(limit=50)
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "status": engine.status,
            "stats": stats,
            "trades": trades,
            "scan_history": list(reversed(engine.scan_history[:10])),
        },
    )
```

- [ ] **Step 3: Create `prediction_bot/src/dashboard/templates/dashboard.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Prediction Market Bot</title>
<style>
  body { font-family: monospace; background: #0d1117; color: #c9d1d9; margin: 0; padding: 20px; }
  h1 { color: #58a6ff; font-size: 1.2em; }
  .cards { display: flex; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }
  .card { background: #161b22; border: 1px solid #30363d; padding: 16px; border-radius: 6px; min-width: 150px; }
  .card .label { font-size: 0.75em; color: #8b949e; }
  .card .value { font-size: 1.5em; font-weight: bold; margin-top: 4px; }
  .positive { color: #3fb950; }
  .negative { color: #f85149; }
  .neutral { color: #58a6ff; }
  table { width: 100%; border-collapse: collapse; margin-top: 10px; }
  th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid #21262d; font-size: 0.85em; }
  th { color: #8b949e; background: #161b22; }
  .badge { padding: 2px 6px; border-radius: 3px; font-size: 0.75em; }
  .badge-won { background: #1a4731; color: #3fb950; }
  .badge-lost { background: #3d1f1f; color: #f85149; }
  .badge-open { background: #1c2d3f; color: #58a6ff; }
  .badge-expired { background: #2d2a1f; color: #d29922; }
  .section { background: #161b22; border: 1px solid #30363d; padding: 16px; border-radius: 6px; margin-bottom: 16px; }
  .section h2 { font-size: 0.9em; color: #8b949e; margin: 0 0 12px 0; text-transform: uppercase; }
  .toggle-btn { background: #21262d; border: 1px solid #30363d; color: #c9d1d9; padding: 6px 14px; border-radius: 6px; cursor: pointer; font-family: monospace; }
  .toggle-btn:hover { background: #30363d; }
</style>
</head>
<body>
<h1>📊 Prediction Market Bot</h1>

<div class="cards">
  <div class="card">
    <div class="label">BANKROLL</div>
    <div class="value neutral" id="bankroll">${{ "%.2f"|format(stats.bankroll) }}</div>
  </div>
  <div class="card">
    <div class="label">TOTAL P&amp;L</div>
    <div class="value {% if stats.total_pnl >= 0 %}positive{% else %}negative{% endif %}" id="pnl">
      {% if stats.total_pnl >= 0 %}+{% endif %}${{ "%.2f"|format(stats.total_pnl) }}
    </div>
  </div>
  <div class="card">
    <div class="label">WIN RATE</div>
    <div class="value" id="winrate">
      {% if stats.win_rate is not none %}{{ "%.1f"|format(stats.win_rate * 100) }}%{% else %}—{% endif %}
      <small style="font-size:0.5em;color:#8b949e">({{ stats.won }}W/{{ stats.lost }}L/{{ stats.expired }}E)</small>
    </div>
  </div>
  <div class="card">
    <div class="label">OPEN TRADES</div>
    <div class="value neutral" id="open-trades">{{ stats.open_trades }}</div>
  </div>
  <div class="card">
    <div class="label">STATUS</div>
    <div class="value" id="bot-status">{{ "ON" if status.enabled else "OFF" }}</div>
    <button class="toggle-btn" onclick="toggleBot()">Toggle</button>
  </div>
</div>

<div class="section">
  <h2>Recent Trades</h2>
  <table id="trades-table">
    <thead>
      <tr>
        <th>Time</th><th>Market</th><th>Platform</th><th>Side</th>
        <th>Entry</th><th>Qty</th><th>Status</th><th>P&amp;L</th><th>Category</th>
      </tr>
    </thead>
    <tbody>
      {% for t in trades %}
      <tr>
        <td>{{ t.created_at.strftime('%m/%d %H:%M') }}</td>
        <td title="{{ t.market_question }}">{{ t.market_question[:55] }}{% if t.market_question|length > 55 %}…{% endif %}</td>
        <td>{{ t.platform }}</td>
        <td>{{ t.side }}</td>
        <td>${{ "%.2f"|format(t.entry_price) }}</td>
        <td>{{ t.quantity|int }}</td>
        <td><span class="badge badge-{{ t.status|lower }}">{{ t.status }}</span></td>
        <td class="{% if t.pnl and t.pnl > 0 %}positive{% elif t.pnl and t.pnl < 0 %}negative{% endif %}">
          {% if t.pnl is not none %}{% if t.pnl > 0 %}+{% endif %}${{ "%.2f"|format(t.pnl) }}{% else %}—{% endif %}
        </td>
        <td>{{ t.category }}</td>
      </tr>
      {% else %}
      <tr><td colspan="9" style="color:#8b949e;text-align:center">No trades yet</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>

<div class="section">
  <h2>Recent Scans</h2>
  <table>
    <thead><tr><th>Time</th><th>Candidates</th><th>Edges</th><th>Trades</th></tr></thead>
    <tbody>
      {% for s in scan_history %}
      <tr>
        <td>{{ s.timestamp[:19].replace('T',' ') }}</td>
        <td>{{ s.candidates_found }}</td>
        <td>{{ s.edges_found }}</td>
        <td>{{ s.trades_placed }}</td>
      </tr>
      {% else %}
      <tr><td colspan="4" style="color:#8b949e;text-align:center">No scans yet</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>

<script>
const es = new EventSource('/api/stream');
es.onmessage = (e) => {
  const data = JSON.parse(e.data);
  if (data.type === 'cycle_complete') {
    const s = data.status;
    document.getElementById('bankroll').textContent = '$' + s.bankroll.toFixed(2);
    document.getElementById('pnl').textContent = (s.total_pnl >= 0 ? '+' : '') + '$' + s.total_pnl.toFixed(2);
    document.getElementById('open-trades').textContent = s.open_trades;
    if (s.win_rate !== null) document.getElementById('winrate').childNodes[0].textContent = (s.win_rate * 100).toFixed(1) + '%';
  }
};

async function toggleBot() {
  const resp = await fetch('/api/bot/toggle', {method: 'POST'});
  const data = await resp.json();
  document.getElementById('bot-status').textContent = data.enabled ? 'ON' : 'OFF';
}
</script>
</body>
</html>
```

- [ ] **Step 4: Create `prediction_bot/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p prediction_bot/data
EXPOSE 4001
CMD ["python", "-m", "prediction_bot.main"]
```

- [ ] **Step 5: Update `docker-compose.yml`**

Add the `prediction-bot` service after the existing `trade-bot` service:

```yaml
  prediction-bot:
    build:
      context: .
      dockerfile: prediction_bot/Dockerfile
    restart: unless-stopped
    ports:
      - "4001:4001"
    env_file:
      - .env
    volumes:
      - ./prediction_bot/data:/app/prediction_bot/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:4001/api/status"]
      interval: 30s
      timeout: 10s
      retries: 3
```

- [ ] **Step 6: Run full test suite**

```bash
.venv/bin/python -m pytest prediction_bot/tests/ -v
```

Expected: all tests pass.

- [ ] **Step 7: Smoke-test the full bot**

```bash
.venv/bin/python -m prediction_bot.main &
sleep 3
curl -s http://localhost:4001/api/status | python3 -m json.tool
curl -s http://localhost:4001/api/stats | python3 -m json.tool
curl -s http://localhost:4001/ | head -5
kill %1
```

Expected: status + stats JSON returned, HTML page starts with `<!DOCTYPE html>`.

- [ ] **Step 8: Commit**

```bash
git add prediction_bot/src/bot/engine.py prediction_bot/src/dashboard/app.py prediction_bot/src/dashboard/templates/dashboard.html prediction_bot/Dockerfile docker-compose.yml
git commit -m "feat(pm): add PredictionEngine, dashboard, Dockerfile — full prediction bot wired up"
```

---

## Task 10: Open PR

- [ ] **Step 1: Push branch**

```bash
git push -u origin HEAD
```

- [ ] **Step 2: Create PR**

```bash
gh pr create \
  --title "feat: prediction market paper trading bot (Polymarket + Kalshi)" \
  --body "$(cat <<'EOF'
## Summary

- New standalone `prediction_bot/` service (port 4001) — scans Polymarket + Kalshi for near-certain outcomes, evaluates edge via Claude LLM, paper-trades with SQLite persistence
- `PredictionEngine`: scan → evaluate → paper-trade → settle cycle every 120s
- `PolymarketClient`: async Gamma API client (public, no auth)
- `KalshiClient`: async Exchange API v2 client (bearer token auth, graceful disable)
- `ResultStore`: aiosqlite persistence — paper_trades + bankroll_snapshots tables
- `PaperTrader`: position limits, bankroll allocation, settlement on resolution
- FastAPI dashboard at `/` with SSE real-time updates
- Docker Compose service `prediction-bot`

## Test plan

- [ ] `pytest prediction_bot/tests/ -v` — all tests pass
- [ ] `python -m prediction_bot.main` — starts on port 4001
- [ ] `GET /api/status` returns bankroll, enabled, win_rate
- [ ] `GET /` loads dashboard HTML
- [ ] `POST /api/cycle` triggers a scan cycle in logs
- [ ] `POST /api/bot/toggle` toggles enabled state
- [ ] Restart bot — previous results summary printed to log
- [ ] `docker-compose up prediction-bot` — service starts correctly

Closes #61
EOF
)"
```

---

## Self-Review Checklist

**Spec coverage:**
- ✅ Task 1: scaffold, settings, models — matches PM-1
- ✅ Task 2: Polymarket client — matches PM-2
- ✅ Task 3: Kalshi client — matches PM-3
- ✅ Task 4: scanner — matches PM-4
- ✅ Task 5: market_data enrichment — matches PM-5 data layer
- ✅ Task 6: evaluator + evaluator_prompt — matches PM-5 LLM layer
- ✅ Task 7: result_store — matches PM-6 persistence
- ✅ Task 8: paper_trader — matches PM-6 trading logic
- ✅ Task 9: engine + dashboard + docker — matches PM-7
- ✅ `aiosqlite` added to requirements.txt

**Type consistency:**
- `PaperTrade.id` is `int | None` — used correctly in `paper_trader.py` with `model_copy(update={"id": trade_id})`
- `MarketCandidate` uses `model_copy` (Pydantic v2) — consistent throughout
- `ResultStore.add_trade` takes `initial_bankroll: float | None` — matches `PaperTrader.initialize()` call flow
- `_noop_ctx` in engine handles `None` clients cleanly

**Placeholder scan:** No TBD/TODO/placeholder items found.
