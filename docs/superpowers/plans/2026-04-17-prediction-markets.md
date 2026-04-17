# Prediction Markets Signal Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inject Polymarket (macro) and Kalshi (ticker-specific) prediction market probabilities as a `=== PREDICTION MARKETS ===` section in the LLM trading prompt.

**Architecture:** A new `src/data/prediction_markets.py` module fetches from both APIs, normalises results into `MarketProb` dataclasses, caches them for 15 min, and returns a dict keyed by `"macro"` and each watchlist ticker. `strategy.py` formats this into a prompt section using the same pattern as existing `_build_macro_section` and `_build_news_section` helpers. `engine.py` calls the fetcher alongside news/earnings/macro and threads it through to `generate_signals()`.

**Tech Stack:** Python 3.14, `requests` (already in requirements.txt), PyYAML (already installed via pydantic-settings transitive dep — verify), `pydantic-settings`, `pytest`, `unittest.mock`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/config/settings.py` | Modify | Add `KALSHI_API_KEY`, `PREDICTION_MARKETS_CACHE_TTL` |
| `.env.example` | Modify | Document new env vars |
| `src/data/prediction_markets_config.yaml` | Create | Curated macro + per-ticker market slugs/series |
| `src/data/prediction_markets.py` | Create | `MarketProb` dataclass, fetchers, cache, public function |
| `src/bot/strategy.py` | Modify | Add `_build_prediction_markets_section()`, update `_build_market_context()` + `generate_signals()` |
| `src/bot/engine.py` | Modify | Call `get_prediction_market_context()` in `_cycle()`, pass to `generate_signals()` |
| `tests/test_prediction_markets.py` | Create | Unit tests for fetchers, cache, section builder |

---

## Task 1: Settings + env vars

**Files:**
- Modify: `src/config/settings.py`
- Modify: `.env.example`

- [ ] **Step 1: Verify PyYAML is available**

```bash
.venv/bin/python -c "import yaml; print(yaml.__version__)"
```

Expected: a version string like `6.0.1`. If `ModuleNotFoundError`, run:
```bash
.venv/bin/pip install pyyaml && echo "pyyaml" >> requirements.txt
```

- [ ] **Step 2: Add settings fields**

In `src/config/settings.py`, after the `NEWS_CACHE_TTL_SECONDS` line add:

```python
    # Prediction markets
    KALSHI_API_KEY: str = ""               # required for Kalshi fetches; skip silently if absent
    PREDICTION_MARKETS_CACHE_TTL: int = 900  # seconds; shared for Polymarket + Kalshi
```

- [ ] **Step 3: Update .env.example**

Append after the `# ── News feed` block:

```
# ── Prediction markets ────────────────────────────────────────────────────────
# Polymarket: no API key needed (public API)
# Kalshi: get a free key at kalshi.com → Settings → API
KALSHI_API_KEY=              # optional; Kalshi skipped silently if absent
PREDICTION_MARKETS_CACHE_TTL=900
```

- [ ] **Step 4: Run settings tests to confirm no regressions**

```bash
.venv/bin/python -m pytest tests/test_settings.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/config/settings.py .env.example
git commit -m "feat: add KALSHI_API_KEY and PREDICTION_MARKETS_CACHE_TTL settings"
```

---

## Task 2: Mapping config YAML

**Files:**
- Create: `src/data/prediction_markets_config.yaml`

- [ ] **Step 1: Create the config file**

```bash
cat > src/data/prediction_markets_config.yaml << 'EOF'
# Prediction markets mapping config.
# macro: Polymarket slugs and/or Kalshi series for macro events.
# tickers: per-ticker Kalshi series + discovery keywords for auto-finding markets.
# Kalshi series names follow the pattern used on kalshi.com/markets.
# discovery_keywords are used when kalshi_series is null or not yet created.

macro:
  - label: "Fed cuts rates May 2025"
    polymarket_slug: "will-the-fed-cut-rates-at-the-may-2025-fomc-meeting"
    kalshi_series: "FED-25BPS-MAY25"
  - label: "Fed cuts rates Jun 2025"
    polymarket_slug: "will-the-fed-cut-rates-at-the-june-2025-fomc-meeting"
    kalshi_series: "FED-25BPS-JUN25"
  - label: "US CPI above 3% Apr 2025"
    polymarket_slug: "us-cpi-above-3-april-2025"
    kalshi_series: null
  - label: "US recession in 2025"
    polymarket_slug: "us-recession-in-2025"
    kalshi_series: "USREC-25"

tickers:
  AAPL:
    - label: "AAPL earnings beat Q2 2025"
      kalshi_series: null
      discovery_keywords: ["apple", "aapl", "earnings"]
  TSLA:
    - label: "TSLA earnings beat Q1 2025"
      kalshi_series: null
      discovery_keywords: ["tesla", "tsla", "earnings"]
  NVDA:
    - label: "NVDA earnings beat Q1 2025"
      kalshi_series: null
      discovery_keywords: ["nvidia", "nvda", "earnings"]
  MSFT:
    - label: "MSFT earnings beat Q3 2025"
      kalshi_series: null
      discovery_keywords: ["microsoft", "msft", "earnings"]
  AMZN:
    - label: "AMZN earnings beat Q1 2025"
      kalshi_series: null
      discovery_keywords: ["amazon", "amzn", "earnings"]
  GOOGL:
    - label: "GOOGL earnings beat Q1 2025"
      kalshi_series: null
      discovery_keywords: ["google", "googl", "earnings"]
  META:
    - label: "META earnings beat Q1 2025"
      kalshi_series: null
      discovery_keywords: ["meta", "facebook", "earnings"]
  NFLX:
    - label: "NFLX earnings beat Q1 2025"
      kalshi_series: null
      discovery_keywords: ["netflix", "nflx", "earnings"]
  AMD:
    - label: "AMD earnings beat Q1 2025"
      kalshi_series: null
      discovery_keywords: ["amd", "advanced micro", "earnings"]
  JPM:
    - label: "JPM earnings beat Q1 2025"
      kalshi_series: null
      discovery_keywords: ["jpmorgan", "jpm", "earnings"]
  V:
    - label: "V earnings beat Q2 2025"
      kalshi_series: null
      discovery_keywords: ["visa", "earnings"]
  UBER:
    - label: "UBER earnings beat Q1 2025"
      kalshi_series: null
      discovery_keywords: ["uber", "earnings"]
  PLTR:
    - label: "PLTR earnings beat Q1 2025"
      kalshi_series: null
      discovery_keywords: ["palantir", "pltr", "earnings"]
EOF
```

- [ ] **Step 2: Verify YAML parses cleanly**

```bash
.venv/bin/python -c "
import yaml, pathlib
cfg = yaml.safe_load(pathlib.Path('src/data/prediction_markets_config.yaml').read_text())
print('macro entries:', len(cfg['macro']))
print('ticker entries:', len(cfg['tickers']))
"
```

Expected:
```
macro entries: 4
ticker entries: 13
```

- [ ] **Step 3: Commit**

```bash
git add src/data/prediction_markets_config.yaml
git commit -m "feat: add prediction markets mapping config (macro + 13 tickers)"
```

---

## Task 3: `prediction_markets.py` — dataclass + Polymarket fetcher

**Files:**
- Create: `src/data/prediction_markets.py`
- Create: `tests/test_prediction_markets.py`

- [ ] **Step 1: Write the failing test for MarketProb and Polymarket fetcher**

Create `tests/test_prediction_markets.py`:

```python
"""Tests for src/data/prediction_markets.py."""
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import pytest


# ---------------------------------------------------------------------------
# MarketProb
# ---------------------------------------------------------------------------

class TestMarketProb:
    def test_fields(self):
        from src.data.prediction_markets import MarketProb
        mp = MarketProb(
            source="polymarket",
            event="Fed cuts May 2025",
            ticker=None,
            yes_prob=0.72,
            volume_usd=2_100_000,
            url="https://polymarket.com/event/fed-cuts",
            fetched_at=datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc),
        )
        assert mp.source == "polymarket"
        assert mp.yes_prob == 0.72
        assert mp.ticker is None
        assert mp.volume_usd == 2_100_000


# ---------------------------------------------------------------------------
# Polymarket fetcher
# ---------------------------------------------------------------------------

class TestFetchPolymarketMacro:
    def test_returns_market_prob_on_success(self):
        """Returns list of MarketProb for each macro entry with a polymarket_slug."""
        from src.data.prediction_markets import _fetch_polymarket_macro

        poly_response = {
            "markets": [
                {
                    "outcomePrices": '["0.72", "0.28"]',
                    "volume": "2100000.00",
                    "conditionId": "abc123",
                }
            ]
        }

        with patch("src.data.prediction_markets.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = poly_response

            results = _fetch_polymarket_macro([
                {"label": "Fed cuts May 2025", "polymarket_slug": "fed-cuts-may-2025", "kalshi_series": None}
            ])

        assert len(results) == 1
        mp = results[0]
        assert mp.source == "polymarket"
        assert mp.event == "Fed cuts May 2025"
        assert mp.ticker is None
        assert abs(mp.yes_prob - 0.72) < 0.001
        assert mp.volume_usd == 2_100_000

    def test_skips_entry_without_slug(self):
        """Entries with null polymarket_slug are skipped."""
        from src.data.prediction_markets import _fetch_polymarket_macro

        results = _fetch_polymarket_macro([
            {"label": "CPI above 3%", "polymarket_slug": None, "kalshi_series": None}
        ])
        assert results == []

    def test_returns_empty_on_http_error(self):
        """HTTP errors return empty list without raising."""
        from src.data.prediction_markets import _fetch_polymarket_macro

        with patch("src.data.prediction_markets.requests.get") as mock_get:
            mock_get.return_value.status_code = 500
            mock_get.return_value.raise_for_status.side_effect = Exception("500")

            results = _fetch_polymarket_macro([
                {"label": "Fed cuts May 2025", "polymarket_slug": "fed-cuts-may-2025", "kalshi_series": None}
            ])

        assert results == []
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
.venv/bin/python -m pytest tests/test_prediction_markets.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.data.prediction_markets'`

- [ ] **Step 3: Create `src/data/prediction_markets.py` with MarketProb + Polymarket fetcher**

```python
"""
Prediction market probabilities from Polymarket (macro) and Kalshi (ticker-specific).

Fetchers fail silently — log warnings and return [] so a missing API key or
network error never breaks the trading cycle.
"""

from __future__ import annotations

import logging
import pathlib
from dataclasses import dataclass
from datetime import UTC, datetime

import requests
import yaml

logger = logging.getLogger(__name__)

_CONFIG_PATH = pathlib.Path(__file__).parent / "prediction_markets_config.yaml"

_cache: dict[str, dict] = {}  # {"macro" | ticker: {"data": list[MarketProb], "fetched_at": datetime}}


@dataclass
class MarketProb:
    source: str         # "polymarket" | "kalshi"
    event: str          # human-readable label
    ticker: str | None  # None for macro events
    yes_prob: float     # 0.0–1.0
    volume_usd: int     # liquidity indicator
    url: str            # traceability; not injected into prompt
    fetched_at: datetime


def _load_config() -> dict:
    return yaml.safe_load(_CONFIG_PATH.read_text())


def _is_fresh(entry: dict, ttl: int) -> bool:
    age = (datetime.now(UTC) - entry["fetched_at"]).total_seconds()
    return age < ttl


# ---------------------------------------------------------------------------
# Polymarket
# ---------------------------------------------------------------------------

_POLYMARKET_BASE = "https://gamma-api.polymarket.com"


def _fetch_polymarket_macro(macro_entries: list[dict]) -> list[MarketProb]:
    """Fetch YES probabilities for macro events from Polymarket public API."""
    results: list[MarketProb] = []
    for entry in macro_entries:
        slug = entry.get("polymarket_slug")
        if not slug:
            continue
        try:
            url = f"{_POLYMARKET_BASE}/events?slug={slug}"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            markets = data.get("markets", [])
            if not markets:
                logger.warning("Polymarket: no markets found for slug '%s'", slug)
                continue
            m = markets[0]
            prices_raw = m.get("outcomePrices", '["0.5", "0.5"]')
            # outcomePrices is a JSON-encoded string like '["0.72", "0.28"]'
            import json as _json
            prices = _json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
            yes_prob = float(prices[0])
            volume_usd = int(float(m.get("volume", 0)))
            market_url = f"https://polymarket.com/event/{slug}"
            results.append(MarketProb(
                source="polymarket",
                event=entry["label"],
                ticker=None,
                yes_prob=yes_prob,
                volume_usd=volume_usd,
                url=market_url,
                fetched_at=datetime.now(UTC),
            ))
        except Exception as e:
            logger.warning("Polymarket fetch failed for slug '%s': %s", slug, e)
    return results
```

- [ ] **Step 4: Run Polymarket tests**

```bash
.venv/bin/python -m pytest tests/test_prediction_markets.py::TestMarketProb tests/test_prediction_markets.py::TestFetchPolymarketMacro -v
```

Expected: all 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/data/prediction_markets.py tests/test_prediction_markets.py
git commit -m "feat: add MarketProb dataclass and Polymarket macro fetcher"
```

---

## Task 4: Kalshi fetcher

**Files:**
- Modify: `src/data/prediction_markets.py`
- Modify: `tests/test_prediction_markets.py`

- [ ] **Step 1: Add Kalshi tests to test file**

Append to `tests/test_prediction_markets.py`:

```python
# ---------------------------------------------------------------------------
# Kalshi fetcher
# ---------------------------------------------------------------------------

class TestFetchKalshiTicker:
    def test_returns_market_prob_on_success(self):
        """Returns MarketProb list when Kalshi API responds with matching markets."""
        from src.data.prediction_markets import _fetch_kalshi_ticker

        kalshi_response = {
            "markets": [
                {
                    "title": "NVDA earnings beat Q1 2025",
                    "yes_ask": 0.61,
                    "volume": 45000,
                    "ticker": "NVDA-EARN-Q1-2025",
                }
            ]
        }

        with patch("src.data.prediction_markets.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = kalshi_response

            results = _fetch_kalshi_ticker(
                ticker="NVDA",
                entries=[{"label": "NVDA earnings beat Q1 2025", "kalshi_series": None, "discovery_keywords": ["nvidia", "earnings"]}],
                api_key="test-key",
            )

        assert len(results) == 1
        mp = results[0]
        assert mp.source == "kalshi"
        assert mp.ticker == "NVDA"
        assert abs(mp.yes_prob - 0.61) < 0.001
        assert mp.volume_usd == 45000

    def test_returns_empty_without_api_key(self):
        """Skips Kalshi silently when api_key is empty."""
        from src.data.prediction_markets import _fetch_kalshi_ticker

        results = _fetch_kalshi_ticker(
            ticker="NVDA",
            entries=[{"label": "NVDA earnings beat Q1 2025", "kalshi_series": None, "discovery_keywords": ["nvidia"]}],
            api_key="",
        )
        assert results == []

    def test_returns_empty_on_http_error(self):
        """HTTP errors return empty list without raising."""
        from src.data.prediction_markets import _fetch_kalshi_ticker

        with patch("src.data.prediction_markets.requests.get") as mock_get:
            mock_get.return_value.status_code = 401
            mock_get.return_value.raise_for_status.side_effect = Exception("401 Unauthorized")

            results = _fetch_kalshi_ticker(
                ticker="NVDA",
                entries=[{"label": "NVDA earnings beat", "kalshi_series": None, "discovery_keywords": ["nvidia"]}],
                api_key="bad-key",
            )
        assert results == []
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/python -m pytest tests/test_prediction_markets.py::TestFetchKalshiTicker -v
```

Expected: `ImportError` or `AttributeError` — `_fetch_kalshi_ticker` not defined yet.

- [ ] **Step 3: Add Kalshi fetcher to `prediction_markets.py`**

Append to `src/data/prediction_markets.py` (after `_fetch_polymarket_macro`):

```python
# ---------------------------------------------------------------------------
# Kalshi
# ---------------------------------------------------------------------------

_KALSHI_BASE = "https://trading-api.kalshi.com/trade-api/v2"


def _fetch_kalshi_ticker(ticker: str, entries: list[dict], api_key: str) -> list[MarketProb]:
    """Fetch YES probabilities for a ticker's events from Kalshi."""
    if not api_key:
        logger.info("KALSHI_API_KEY not set — skipping Kalshi for %s", ticker)
        return []

    headers = {"Authorization": f"Bearer {api_key}"}
    results: list[MarketProb] = []

    for entry in entries:
        series = entry.get("kalshi_series")
        keywords = entry.get("discovery_keywords", [])
        label = entry["label"]

        markets: list[dict] = []

        # Try curated series first
        if series:
            try:
                resp = requests.get(
                    f"{_KALSHI_BASE}/markets",
                    params={"series_ticker": series},
                    headers=headers,
                    timeout=10,
                )
                resp.raise_for_status()
                markets = resp.json().get("markets", [])
            except Exception as e:
                logger.warning("Kalshi series fetch failed for '%s': %s", series, e)

        # Fall back to keyword discovery
        if not markets and keywords:
            query = " ".join(keywords[:2])
            try:
                resp = requests.get(
                    f"{_KALSHI_BASE}/markets",
                    params={"search": query, "status": "open", "limit": 5},
                    headers=headers,
                    timeout=10,
                )
                resp.raise_for_status()
                markets = resp.json().get("markets", [])
            except Exception as e:
                logger.warning("Kalshi discovery failed for ticker '%s' query '%s': %s", ticker, query, e)

        if not markets:
            continue

        m = markets[0]
        yes_prob = float(m.get("yes_ask", m.get("yes_bid", 0.5)))
        volume_usd = int(m.get("volume", 0))
        market_ticker = m.get("ticker", "")
        market_url = f"https://kalshi.com/markets/{market_ticker}"

        results.append(MarketProb(
            source="kalshi",
            event=label,
            ticker=ticker,
            yes_prob=yes_prob,
            volume_usd=volume_usd,
            url=market_url,
            fetched_at=datetime.now(UTC),
        ))

    return results
```

- [ ] **Step 4: Run Kalshi tests**

```bash
.venv/bin/python -m pytest tests/test_prediction_markets.py::TestFetchKalshiTicker -v
```

Expected: all 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/data/prediction_markets.py tests/test_prediction_markets.py
git commit -m "feat: add Kalshi ticker fetcher with curated series + keyword discovery"
```

---

## Task 5: Cache + public `get_prediction_market_context()`

**Files:**
- Modify: `src/data/prediction_markets.py`
- Modify: `tests/test_prediction_markets.py`

- [ ] **Step 1: Add cache + public function tests**

Append to `tests/test_prediction_markets.py`:

```python
# ---------------------------------------------------------------------------
# Cache + public function
# ---------------------------------------------------------------------------

class TestGetPredictionMarketContext:
    def setup_method(self):
        from src.data import prediction_markets
        prediction_markets._cache.clear()

    def test_returns_macro_and_ticker_keys(self):
        """Result contains 'macro' key and one key per watchlist ticker."""
        from src.data.prediction_markets import get_prediction_market_context

        macro_prob = MarketProb(
            source="polymarket", event="Fed cuts", ticker=None,
            yes_prob=0.7, volume_usd=1_000_000,
            url="https://polymarket.com/x", fetched_at=datetime.now(timezone.utc),
        )
        nvda_prob = MarketProb(
            source="kalshi", event="NVDA beat", ticker="NVDA",
            yes_prob=0.6, volume_usd=50_000,
            url="https://kalshi.com/x", fetched_at=datetime.now(timezone.utc),
        )

        with patch("src.data.prediction_markets._fetch_polymarket_macro", return_value=[macro_prob]), \
             patch("src.data.prediction_markets._fetch_kalshi_ticker", return_value=[nvda_prob]), \
             patch("src.data.prediction_markets.settings") as mock_settings:
            mock_settings.KALSHI_API_KEY = "test-key"
            mock_settings.PREDICTION_MARKETS_CACHE_TTL = 900
            result = get_prediction_market_context(["NVDA"])

        assert "macro" in result
        assert "NVDA" in result
        assert result["macro"][0].event == "Fed cuts"
        assert result["NVDA"][0].event == "NVDA beat"

    def test_returns_cached_result_within_ttl(self):
        """Second call within TTL does not re-fetch."""
        from src.data.prediction_markets import get_prediction_market_context

        with patch("src.data.prediction_markets._fetch_polymarket_macro", return_value=[]) as poly_mock, \
             patch("src.data.prediction_markets._fetch_kalshi_ticker", return_value=[]) as kalshi_mock, \
             patch("src.data.prediction_markets.settings") as mock_settings:
            mock_settings.KALSHI_API_KEY = "test-key"
            mock_settings.PREDICTION_MARKETS_CACHE_TTL = 900
            get_prediction_market_context(["NVDA"])
            get_prediction_market_context(["NVDA"])

        # Should only fetch once (second call hits cache)
        assert poly_mock.call_count == 1

    def test_empty_result_when_all_fetchers_fail(self):
        """Returns dict with empty lists when both fetchers raise."""
        from src.data.prediction_markets import get_prediction_market_context

        with patch("src.data.prediction_markets._fetch_polymarket_macro", return_value=[]), \
             patch("src.data.prediction_markets._fetch_kalshi_ticker", return_value=[]), \
             patch("src.data.prediction_markets.settings") as mock_settings:
            mock_settings.KALSHI_API_KEY = ""
            mock_settings.PREDICTION_MARKETS_CACHE_TTL = 900
            result = get_prediction_market_context(["NVDA"])

        assert result["macro"] == []
        assert result.get("NVDA", []) == []
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/python -m pytest tests/test_prediction_markets.py::TestGetPredictionMarketContext -v
```

Expected: `ImportError` — `get_prediction_market_context` not defined yet.

- [ ] **Step 3: Add cache + public function to `prediction_markets.py`**

Append to `src/data/prediction_markets.py`:

```python
# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

from src.config.settings import settings as _settings


def get_prediction_market_context(watchlist: list[str]) -> dict[str, list[MarketProb]]:
    """
    Fetch and cache prediction market probabilities for macro events and each
    watchlist ticker. Returns {"macro": [...], "NVDA": [...], ...}.
    Both fetchers fail silently — missing keys or network errors return [].
    """
    ttl = _settings.PREDICTION_MARKETS_CACHE_TTL
    config = _load_config()

    result: dict[str, list[MarketProb]] = {}

    # --- macro ---
    cache_key = "__macro__"
    if cache_key in _cache and _is_fresh(_cache[cache_key], ttl):
        result["macro"] = _cache[cache_key]["data"]
    else:
        macro_probs = _fetch_polymarket_macro(config.get("macro", []))
        _cache[cache_key] = {"data": macro_probs, "fetched_at": datetime.now(UTC)}
        result["macro"] = macro_probs

    # --- per ticker ---
    ticker_configs: dict[str, list[dict]] = config.get("tickers", {})
    for ticker in watchlist:
        if ticker in _cache and _is_fresh(_cache[ticker], ttl):
            result[ticker] = _cache[ticker]["data"]
            continue
        entries = ticker_configs.get(ticker, [])
        if not entries:
            result[ticker] = []
            continue
        probs = _fetch_kalshi_ticker(ticker, entries, _settings.KALSHI_API_KEY)
        _cache[ticker] = {"data": probs, "fetched_at": datetime.now(UTC)}
        result[ticker] = probs

    return result
```

- [ ] **Step 4: Run all prediction markets tests**

```bash
.venv/bin/python -m pytest tests/test_prediction_markets.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/data/prediction_markets.py tests/test_prediction_markets.py
git commit -m "feat: add prediction market cache and get_prediction_market_context()"
```

---

## Task 6: Strategy — section builder + prompt integration

**Files:**
- Modify: `src/bot/strategy.py`
- Modify: `tests/test_strategy.py`

- [ ] **Step 1: Add section builder tests to `tests/test_strategy.py`**

Append to `tests/test_strategy.py`:

```python
# ---------------------------------------------------------------------------
# _build_prediction_markets_section
# ---------------------------------------------------------------------------

from datetime import timezone as _tz
from src.bot.strategy import _build_prediction_markets_section
from src.data.prediction_markets import MarketProb as _MarketProb


def _make_prob(source, event, ticker, yes_prob, volume_usd) -> _MarketProb:
    return _MarketProb(
        source=source, event=event, ticker=ticker,
        yes_prob=yes_prob, volume_usd=volume_usd,
        url="https://example.com", fetched_at=datetime(2026, 4, 17, tzinfo=_tz.utc),
    )


class TestBuildPredictionMarketsSection:
    def test_returns_empty_string_for_empty_data(self):
        assert _build_prediction_markets_section({}) == ""
        assert _build_prediction_markets_section({"macro": [], "NVDA": []}) == ""

    def test_macro_only(self):
        data = {
            "macro": [_make_prob("polymarket", "Fed cuts May 2025", None, 0.72, 2_100_000)],
            "NVDA": [],
        }
        section = _build_prediction_markets_section(data)
        assert "=== PREDICTION MARKETS ===" in section
        assert "Fed cuts May 2025" in section
        assert "72%" in section
        assert "Polymarket" in section
        assert "$2.1M" in section

    def test_ticker_market_included(self):
        data = {
            "macro": [],
            "NVDA": [_make_prob("kalshi", "NVDA earnings beat Q1", "NVDA", 0.61, 45_000)],
        }
        section = _build_prediction_markets_section(data)
        assert "NVDA" in section
        assert "61%" in section
        assert "Kalshi" in section

    def test_low_liquidity_flagged(self):
        data = {
            "macro": [],
            "TSLA": [_make_prob("kalshi", "TSLA earnings beat Q1", "TSLA", 0.44, 5_000)],
        }
        section = _build_prediction_markets_section(data)
        assert "low liquidity" in section

    def test_high_liquidity_not_flagged(self):
        data = {
            "macro": [],
            "NVDA": [_make_prob("kalshi", "NVDA earnings beat Q1", "NVDA", 0.61, 50_000)],
        }
        section = _build_prediction_markets_section(data)
        assert "low liquidity" not in section

    def test_build_market_context_includes_section(self):
        from src.bot.strategy import _build_market_context
        from src.api.models import CashInfo
        data = {
            "macro": [_make_prob("polymarket", "Fed cuts", None, 0.7, 1_000_000)],
        }
        cash = CashInfo(free=5000, total=10000, ppl=0, result=0, invested=5000, pieCash=0)
        ctx = _build_market_context([], cash, ["NVDA"], [], prediction_markets=data)
        assert "=== PREDICTION MARKETS ===" in ctx

    def test_build_market_context_omits_section_when_empty(self):
        from src.bot.strategy import _build_market_context
        from src.api.models import CashInfo
        cash = CashInfo(free=5000, total=10000, ppl=0, result=0, invested=5000, pieCash=0)
        ctx = _build_market_context([], cash, ["NVDA"], [], prediction_markets=None)
        assert "=== PREDICTION MARKETS ===" not in ctx
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/python -m pytest tests/test_strategy.py::TestBuildPredictionMarketsSection -v
```

Expected: `ImportError` — `_build_prediction_markets_section` not defined yet.

- [ ] **Step 3: Add `_build_prediction_markets_section` to `strategy.py`**

In `src/bot/strategy.py`, add this import at the top with the other data imports:

```python
from src.data.prediction_markets import MarketProb
```

Then add this function after `_build_macro_section`:

```python
def _build_prediction_markets_section(data: dict[str, list["MarketProb"]]) -> str:
    """Format the === PREDICTION MARKETS === prompt section."""
    LOW_LIQUIDITY_THRESHOLD = 10_000

    def _fmt_vol(v: int) -> str:
        if v >= 1_000_000:
            return f"${v / 1_000_000:.1f}M"
        if v >= 1_000:
            return f"${v // 1_000}K"
        return f"${v}"

    lines: list[str] = []

    macro_probs = [p for p in data.get("macro", []) if p]
    if macro_probs:
        lines.append("MACRO:")
        for p in macro_probs:
            liq = " — low liquidity" if p.volume_usd < LOW_LIQUIDITY_THRESHOLD else ""
            source_label = "Polymarket" if p.source == "polymarket" else "Kalshi"
            lines.append(
                f"  {p.event}: {p.yes_prob * 100:.0f}% yes"
                f"  ({source_label}, {_fmt_vol(p.volume_usd)} vol{liq})"
            )
        lines.append("")

    for ticker, probs in data.items():
        if ticker == "macro" or not probs:
            continue
        lines.append(f"{ticker}:")
        for p in probs:
            liq = " — low liquidity" if p.volume_usd < LOW_LIQUIDITY_THRESHOLD else ""
            source_label = "Polymarket" if p.source == "polymarket" else "Kalshi"
            lines.append(
                f"  {p.event}: {p.yes_prob * 100:.0f}% yes"
                f"  ({source_label}, {_fmt_vol(p.volume_usd)} vol{liq})"
            )
        lines.append("")

    if not lines:
        return ""

    body = "\n".join(lines).rstrip()
    return f"\n=== PREDICTION MARKETS ===\n{body}\n"
```

- [ ] **Step 4: Update `_build_market_context` signature and body**

Change the function signature from:
```python
def _build_market_context(
    positions: list[Position],
    cash: CashInfo,
    watchlist: list[str],
    instruments: list[Instrument],
    price_data: dict | None = None,
    earnings_info: dict[str, "EarningsInfo"] | None = None,
    news_data: dict[str, list["NewsItem"]] | None = None,
    macro_events: list["MacroEvent"] | None = None,
    outcome_log: list | None = None,
    regime: "RegimeResult | None" = None,
) -> str:
```

To:
```python
def _build_market_context(
    positions: list[Position],
    cash: CashInfo,
    watchlist: list[str],
    instruments: list[Instrument],
    price_data: dict | None = None,
    earnings_info: dict[str, "EarningsInfo"] | None = None,
    news_data: dict[str, list["NewsItem"]] | None = None,
    macro_events: list["MacroEvent"] | None = None,
    outcome_log: list | None = None,
    regime: "RegimeResult | None" = None,
    prediction_markets: dict | None = None,
) -> str:
```

Then in the body, add after `macro_section = _build_macro_section(macro_events, settings.MACRO_BLOCK_HOURS)`:

```python
    prediction_markets_section = ""
    if prediction_markets:
        prediction_markets_section = _build_prediction_markets_section(prediction_markets)
```

And update the `context` f-string — replace:
```python
{earnings_section}{macro_section}{news_section}{perf_section}{regime_section}
```
With:
```python
{earnings_section}{macro_section}{prediction_markets_section}{news_section}{perf_section}{regime_section}
```

- [ ] **Step 5: Update `AIStrategy.generate_signals` signature**

Add `prediction_markets: dict | None = None` to the method signature and pass it through:

```python
    def generate_signals(
        self,
        positions: list[Position],
        cash: CashInfo,
        watchlist: list[str],
        instruments: list[Instrument],
        provider_config: "ProviderConfig | None" = None,
        earnings_info: dict[str, "EarningsInfo"] | None = None,
        news_data: dict[str, list["NewsItem"]] | None = None,
        macro_events: list["MacroEvent"] | None = None,
        outcome_log: list | None = None,
        regime: "RegimeResult | None" = None,
        prediction_markets: dict | None = None,
    ) -> list[TradeSignal]:
```

And in the body, update the `_build_market_context` call to pass it through:

```python
        user_prompt = _build_market_context(
            positions, cash, watchlist, instruments, price_data,
            earnings_info, news_data, macro_events, outcome_log,
            regime=regime,
            prediction_markets=prediction_markets,
        )
```

- [ ] **Step 6: Run all strategy tests**

```bash
.venv/bin/python -m pytest tests/test_strategy.py -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/bot/strategy.py tests/test_strategy.py
git commit -m "feat: add prediction markets prompt section to strategy"
```

---

## Task 7: Engine — fetch and thread through

**Files:**
- Modify: `src/bot/engine.py`

- [ ] **Step 1: Add import to `engine.py`**

In `src/bot/engine.py`, add alongside the other data imports:

```python
from src.data.prediction_markets import get_prediction_market_context
```

- [ ] **Step 2: Add fetch call in `_cycle()`**

In `_cycle()`, after the line `macro_events = self.macro.get_high_impact_events(hours_ahead=24)`, add:

```python
            # Fetch prediction market probabilities (cached 15 min; fails silently)
            prediction_markets = get_prediction_market_context(settings.WATCHLIST)
```

- [ ] **Step 3: Pass to `generate_signals()`**

Update the `generate_signals` call to include:

```python
            signals = self.strategy.generate_signals(
                positions, cash, settings.WATCHLIST, instruments,
                provider_config=self._provider_config,
                earnings_info=earnings_info,
                news_data=news_data,
                macro_events=macro_events,
                outcome_log=self.outcome_log,
                regime=self._last_regime,
                prediction_markets=prediction_markets,
            )
```

- [ ] **Step 4: Run full test suite**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/bot/engine.py
git commit -m "feat: fetch prediction market context in engine cycle and pass to strategy"
```

---

## Task 8: Open PR

- [ ] **Step 1: Push branch**

```bash
git push -u origin HEAD
```

- [ ] **Step 2: Create PR**

```bash
gh pr create \
  --title "feat: inject prediction market probabilities into LLM prompt" \
  --body "$(cat <<'EOF'
## Summary

- Adds `src/data/prediction_markets.py` — Polymarket (macro) + Kalshi (ticker) fetchers with 15-min cache and silent failure
- Adds `src/data/prediction_markets_config.yaml` — curated macro slugs + per-ticker keywords for all 13 watchlist tickers
- Adds `=== PREDICTION MARKETS ===` section to the LLM trading prompt
- New settings: `KALSHI_API_KEY`, `PREDICTION_MARKETS_CACHE_TTL`

## Test plan

- [ ] Run `pytest tests/test_prediction_markets.py -v` — all pass
- [ ] Run `pytest tests/test_strategy.py -v` — all pass
- [ ] Run `pytest tests/ -v` — full suite passes
- [ ] Set `KALSHI_API_KEY=` (empty) in `.env` — confirm bot starts and cycles without error
- [ ] Set a valid `KALSHI_API_KEY` — confirm `=== PREDICTION MARKETS ===` appears in logs

Closes #60
EOF
)"
```
