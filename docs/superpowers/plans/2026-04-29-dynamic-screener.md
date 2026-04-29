# Dynamic Watchlist Screener Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in screener that surfaces up to N high-momentum S&P 500 candidates each trading cycle and injects them as clearly-labelled transient additions to the Claude prompt.

**Architecture:** A new `src/data/screener.py` module scores universe tickers against three criteria (volume spike, relative strength vs SPY, near 52-week high) using a 1-year yfinance batch fetch. Candidates are passed through `generate_signals()` as a separate `screen_candidates` list so they appear in a distinct prompt section while the permanent watchlist is unchanged.

**Tech Stack:** Python 3.14, yfinance, dataclasses, pytest, existing LiteLLM / FastAPI stack.

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `src/data/screener.py` | Screening logic, data fetch, cache, ScreenCandidate dataclass |
| Modify | `src/config/settings.py` | Add ENABLE_SCREENER, MAX_SCREENER_ADDITIONS |
| Modify | `src/bot/strategy.py` | Accept screen_candidates, extend price fetch, new prompt section |
| Modify | `src/bot/engine.py` | Call screener in _cycle(), pass candidates to generate_signals() |
| Create | `tests/test_screener.py` | Unit tests for all screening criteria (no network) |

---

## Shared `price_data` dict format (used in tests and internally by screener)

Every entry in the `price_data` dict passed to `run_screener()` must have this shape:

```python
{
    "TICKER": {
        "current_price": float,
        "high_52w": float,
        "current_volume": int,     # most recent day's volume
        "avg_volume_30d": int,     # 30-day average volume
        "return_5d": float,        # decimal, e.g. 0.05 means +5%
    },
    # SPY must also be present for the rs_vs_spy criterion
    "SPY": {
        "current_price": float,
        "high_52w": float,
        "current_volume": int,
        "avg_volume_30d": int,
        "return_5d": float,
    },
}
```

`_fetch_screener_data()` (Task 7) produces this exact shape. Tests pass hand-crafted dicts of this shape directly.

---

## Task 1: Add settings

**Files:**
- Modify: `src/config/settings.py:32-35`

- [ ] **Step 1: Add the two new settings fields**

In `src/config/settings.py`, after the `WATCHLIST` field (line 35), add:

```python
    # Dynamic screener
    ENABLE_SCREENER: bool = False
    MAX_SCREENER_ADDITIONS: int = 3
```

- [ ] **Step 2: Verify settings load**

```bash
.venv/bin/python -c "from src.config.settings import settings; print(settings.ENABLE_SCREENER, settings.MAX_SCREENER_ADDITIONS)"
```

Expected output: `False 3`

- [ ] **Step 3: Commit**

```bash
git add src/config/settings.py
git commit -m "feat: add ENABLE_SCREENER and MAX_SCREENER_ADDITIONS settings"
```

---

## Task 2: ScreenCandidate dataclass + screener skeleton

**Files:**
- Create: `src/data/screener.py`
- Create: `tests/test_screener.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_screener.py`:

```python
"""Unit tests for src/data/screener.py — no yfinance network calls."""
import pytest
from src.data.screener import ScreenCandidate, run_screener


def test_empty_universe():
    result = run_screener([], price_data={}, max_results=3)
    assert result == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_screener.py::test_empty_universe -v
```

Expected: `ModuleNotFoundError` or `ImportError` — `src/data/screener.py` does not exist yet.

- [ ] **Step 3: Create screener skeleton**

Create `src/data/screener.py`:

```python
"""
Dynamic watchlist screener.

Scores S&P 500 universe tickers against momentum criteria each trading cycle.
Returns up to max_results ScreenCandidate objects for injection into the Claude prompt.
Uses a 1-year yfinance batch fetch (cached 5 min). Pass price_data explicitly for tests.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

_CACHE_TTL = 300  # seconds
_screener_cache: dict = {}  # {"data": dict, "fetched_at": datetime}

SP500_TOP100: list[str] = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "BRK-B", "LLY", "JPM",
    "AVGO", "V", "UNH", "XOM", "MA", "JNJ", "HD", "PG", "COST", "ABBV",
    "MRK", "BAC", "CRM", "CVX", "NFLX", "KO", "WMT", "ORCL", "AMD", "LIN",
    "ACN", "PM", "ADBE", "MCD", "CSCO", "TXN", "TMO", "ABT", "PEP", "DIS",
    "WFC", "AMGN", "INTU", "NEE", "QCOM", "DHR", "ISRG", "AMAT", "PFE", "SPGI",
    "IBM", "VZ", "HON", "SYK", "BX", "GS", "UBER", "UNP", "ELV", "LOW",
    "RTX", "T", "PANW", "BA", "CAT", "BKNG", "AXP", "SBUX", "BLK", "DE",
    "GILD", "MDLZ", "ADI", "MS", "CI", "REGN", "MMC", "ETN", "NOW", "LRCX",
    "TJX", "ZTS", "KLAC", "PLD", "AMT", "CB", "MO", "ICE", "SHW", "DXCM",
    "APH", "BSX", "CME", "EQIX", "HCA", "VRTX", "PLTR", "CRWD", "MSTR", "APP",
]


@dataclass
class ScreenCandidate:
    ticker: str
    trigger: str   # "volume_spike", "rs_vs_spy", "near_52w_high", or "+" combined
    score: float   # higher = stronger; used for ranking
    details: str   # injected verbatim into Claude prompt, e.g. "vol=4.2× avg"


def run_screener(
    universe: list[str],
    price_data: dict | None = None,
    exclude: list[str] | None = None,
    max_results: int = 3,
) -> list[ScreenCandidate]:
    """Score universe tickers and return top candidates.

    Args:
        universe:   List of ticker symbols to screen.
        price_data: Pre-fetched data dict (see module docstring for shape).
                    Pass None to fetch internally via yfinance (with cache).
        exclude:    Tickers to omit from results (pass settings.WATCHLIST).
        max_results: Maximum candidates to return.
    """
    if not universe:
        return []
    return []  # stub — implemented in later tasks
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/test_screener.py::test_empty_universe -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/data/screener.py tests/test_screener.py
git commit -m "feat: add ScreenCandidate dataclass and screener skeleton"
```

---

## Task 3: Volume spike criterion

**Files:**
- Modify: `src/data/screener.py`
- Modify: `tests/test_screener.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_screener.py`:

```python
def _base_spy() -> dict:
    """SPY entry that never triggers rs_vs_spy on its own."""
    return {"current_price": 500.0, "high_52w": 520.0,
            "current_volume": 80_000_000, "avg_volume_30d": 70_000_000,
            "return_5d": 0.01}


def test_volume_spike_detected():
    price_data = {
        "PLTR": {
            "current_price": 100.0, "high_52w": 130.0,
            "current_volume": 5_000_000, "avg_volume_30d": 1_000_000,
            "return_5d": 0.01,  # no RS signal
        },
        "AAPL": {
            "current_price": 200.0, "high_52w": 230.0,
            "current_volume": 800_000, "avg_volume_30d": 1_000_000,
            "return_5d": 0.00,  # below average volume, no signal
        },
        "SPY": _base_spy(),
    }
    results = run_screener(["PLTR", "AAPL"], price_data=price_data, max_results=5)
    tickers = [r.ticker for r in results]
    assert "PLTR" in tickers
    assert "AAPL" not in tickers
    pltr = next(r for r in results if r.ticker == "PLTR")
    assert pltr.trigger == "volume_spike"
    assert pltr.score == 1.0
    assert "vol=" in pltr.details
    assert "× avg" in pltr.details
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_screener.py -v
```

Expected: `test_empty_universe PASSED`, `test_volume_spike_detected FAILED` (returns empty list).

- [ ] **Step 3: Implement volume spike scoring**

In `src/data/screener.py`, add after the `SP500_TOP100` list and before `run_screener()`:

```python
def _score_volume_spike(td: dict) -> float | None:
    """Returns 1.0 if today's volume ≥ 2.5× 30d avg, else None."""
    vol = td.get("current_volume", 0)
    avg = td.get("avg_volume_30d", 0)
    if avg <= 0:
        return None
    if vol / avg >= 2.5:
        return 1.0
    return None
```

Replace the `run_screener()` stub body with:

```python
    if not universe:
        return []

    if price_data is None:
        price_data = _fetch_screener_data(universe)

    if not price_data:
        return []

    spy_data = price_data.get("SPY", {})
    excluded = set(exclude or [])
    candidates: list[ScreenCandidate] = []

    for ticker in universe:
        if ticker in excluded:
            continue
        td = price_data.get(ticker)
        if not td:
            continue

        score = 0.0
        triggers: list[str] = []
        details_parts: list[str] = []

        vol_score = _score_volume_spike(td)
        if vol_score is not None:
            ratio = td["current_volume"] / td["avg_volume_30d"]
            score += vol_score
            triggers.append("volume_spike")
            details_parts.append(f"vol={ratio:.1f}× avg")

        if not triggers:
            continue

        candidates.append(ScreenCandidate(
            ticker=ticker,
            trigger="+".join(triggers),
            score=round(score, 4),
            details=", ".join(details_parts),
        ))

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:max_results]
```

Also add a stub for the internal fetch (needed for the `price_data is None` branch):

```python
def _fetch_screener_data(universe: list[str]) -> dict:
    """Fetch 1-year OHLCV for universe + SPY. Implemented in Task 7."""
    return {}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_screener.py -v
```

Expected: both tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add src/data/screener.py tests/test_screener.py
git commit -m "feat(screener): implement volume spike criterion"
```

---

## Task 4: RS vs SPY criterion

**Files:**
- Modify: `src/data/screener.py`
- Modify: `tests/test_screener.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_screener.py`:

```python
def test_rs_vs_spy_detected():
    price_data = {
        "META": {
            "current_price": 600.0, "high_52w": 700.0,
            "current_volume": 500_000, "avg_volume_30d": 1_000_000,  # no vol spike
            "return_5d": 0.08,   # +8% 5-day
        },
        "GILD": {
            "current_price": 90.0, "high_52w": 110.0,
            "current_volume": 400_000, "avg_volume_30d": 1_000_000,
            "return_5d": 0.02,   # +2%, only 1pp above SPY — below threshold
        },
        "SPY": {"current_price": 500.0, "high_52w": 520.0,
                "current_volume": 80_000_000, "avg_volume_30d": 70_000_000,
                "return_5d": 0.05},   # SPY +5%
    }
    results = run_screener(["META", "GILD"], price_data=price_data, max_results=5)
    tickers = [r.ticker for r in results]
    assert "META" in tickers    # +8% vs SPY +5% = +3pp, exactly at threshold
    assert "GILD" not in tickers
    meta = next(r for r in results if r.ticker == "META")
    assert meta.trigger == "rs_vs_spy"
    assert "RS=+" in meta.details
    assert "pp vs SPY" in meta.details
    # score = 0.5 + (3.0 / 10) = 0.8
    assert abs(meta.score - 0.8) < 0.01
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_screener.py::test_rs_vs_spy_detected -v
```

Expected: `FAILED` — META not returned.

- [ ] **Step 3: Implement RS vs SPY scoring**

In `src/data/screener.py`, add after `_score_volume_spike()`:

```python
def _score_rs_vs_spy(td: dict, spy_data: dict) -> tuple[float, float] | None:
    """Returns (score, rs_delta_pp) if 5-day RS ≥ SPY + 3pp, else None."""
    ticker_5d = td.get("return_5d")
    spy_5d = spy_data.get("return_5d")
    if ticker_5d is None or spy_5d is None:
        return None
    rs_delta_pp = (ticker_5d - spy_5d) * 100
    if rs_delta_pp >= 3.0:
        score = min(1.0, 0.5 + rs_delta_pp / 10)
        return score, rs_delta_pp
    return None
```

In `run_screener()`, add RS scoring inside the per-ticker loop, after the volume spike block and before `if not triggers`:

```python
        rs_result = _score_rs_vs_spy(td, spy_data)
        if rs_result is not None:
            rs_score, rs_delta = rs_result
            score += rs_score
            triggers.append("rs_vs_spy")
            details_parts.append(f"RS=+{rs_delta:.1f}pp vs SPY")
```

- [ ] **Step 4: Run all tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_screener.py -v
```

Expected: all `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add src/data/screener.py tests/test_screener.py
git commit -m "feat(screener): implement RS vs SPY criterion"
```

---

## Task 5: Near 52-week high criterion

**Files:**
- Modify: `src/data/screener.py`
- Modify: `tests/test_screener.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_screener.py`:

```python
def test_near_52w_high_detected():
    price_data = {
        "CRWD": {
            "current_price": 395.0, "high_52w": 400.0,   # 1.25% from 52w high
            "current_volume": 500_000, "avg_volume_30d": 1_000_000,
            "return_5d": 0.01,   # no RS signal
        },
        "IBM": {
            "current_price": 150.0, "high_52w": 200.0,   # 25% from 52w high — too far
            "current_volume": 300_000, "avg_volume_30d": 1_000_000,
            "return_5d": 0.00,
        },
        "SPY": {"current_price": 500.0, "high_52w": 520.0,
                "current_volume": 80_000_000, "avg_volume_30d": 70_000_000,
                "return_5d": 0.01},
    }
    results = run_screener(["CRWD", "IBM"], price_data=price_data, max_results=5)
    tickers = [r.ticker for r in results]
    assert "CRWD" in tickers
    assert "IBM" not in tickers
    crwd = next(r for r in results if r.ticker == "CRWD")
    assert crwd.trigger == "near_52w_high"
    assert "% from 52w high" in crwd.details
    # gap_pct = (400 - 395) / 400 = 0.0125
    # score = 0.5 + (1 - 0.0125/0.02) * 0.5 = 0.5 + 0.375 * 0.5 ≈ 0.6875
    assert abs(crwd.score - 0.6875) < 0.001
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_screener.py::test_near_52w_high_detected -v
```

Expected: `FAILED`.

- [ ] **Step 3: Implement near 52w high scoring**

In `src/data/screener.py`, add after `_score_rs_vs_spy()`:

```python
def _score_near_52w_high(td: dict) -> tuple[float, float] | None:
    """Returns (score, gap_pct) if price within 2% of 52w high, else None.

    gap_pct = (high_52w - current) / high_52w
    Score = 1.0 at 52w high, 0.5 at exactly 2% below.
    """
    current = td.get("current_price")
    high_52w = td.get("high_52w")
    if not current or not high_52w or high_52w <= 0:
        return None
    gap_pct = (high_52w - current) / high_52w
    if gap_pct <= 0.02:
        score = 0.5 + (1 - gap_pct / 0.02) * 0.5
        return score, gap_pct
    return None
```

In `run_screener()`, add near-52w-high scoring inside the per-ticker loop, after the RS block and before `if not triggers`:

```python
        near_result = _score_near_52w_high(td)
        if near_result is not None:
            near_score, gap_pct = near_result
            score += near_score
            triggers.append("near_52w_high")
            details_parts.append(f"{gap_pct * 100:.1f}% from 52w high")
```

- [ ] **Step 4: Run all tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_screener.py -v
```

Expected: all `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add src/data/screener.py tests/test_screener.py
git commit -m "feat(screener): implement near-52w-high criterion"
```

---

## Task 6: Multi-criterion scoring, exclude filter, max_results

**Files:**
- Modify: `tests/test_screener.py`

(The loop logic in `run_screener()` already handles all of this — these tests verify correctness.)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_screener.py`:

```python
def test_multi_criterion_score():
    """Ticker matching volume_spike + rs_vs_spy should outscore single-criterion ticker."""
    price_data = {
        "PLTR": {  # volume spike only
            "current_price": 100.0, "high_52w": 130.0,
            "current_volume": 5_000_000, "avg_volume_30d": 1_000_000,
            "return_5d": 0.01,
        },
        "META": {  # volume spike + rs_vs_spy
            "current_price": 600.0, "high_52w": 700.0,
            "current_volume": 5_000_000, "avg_volume_30d": 1_000_000,
            "return_5d": 0.09,   # +9%, SPY +5% → RS = +4pp
        },
        "SPY": {"current_price": 500.0, "high_52w": 520.0,
                "current_volume": 80_000_000, "avg_volume_30d": 70_000_000,
                "return_5d": 0.05},
    }
    results = run_screener(["PLTR", "META"], price_data=price_data, max_results=5)
    assert len(results) == 2
    # META should rank first (higher score)
    assert results[0].ticker == "META"
    assert results[1].ticker == "PLTR"
    assert results[0].score > results[1].score
    assert "volume_spike" in results[0].trigger
    assert "rs_vs_spy" in results[0].trigger


def test_max_results_limit():
    """Only top N candidates returned even if more qualify."""
    price_data = {
        "SPY": {"current_price": 500.0, "high_52w": 520.0,
                "current_volume": 80_000_000, "avg_volume_30d": 70_000_000,
                "return_5d": 0.01},
    }
    # Add 5 tickers all with volume spikes
    for sym in ["A", "B", "C", "D", "E"]:
        price_data[sym] = {
            "current_price": 100.0, "high_52w": 130.0,
            "current_volume": 5_000_000, "avg_volume_30d": 1_000_000,
            "return_5d": 0.01,
        }
    results = run_screener(["A", "B", "C", "D", "E"], price_data=price_data, max_results=2)
    assert len(results) == 2


def test_watchlist_tickers_excluded():
    """Tickers in exclude list do not appear in results."""
    price_data = {
        "NVDA": {
            "current_price": 900.0, "high_52w": 950.0,
            "current_volume": 5_000_000, "avg_volume_30d": 1_000_000,
            "return_5d": 0.10,
        },
        "AMZN": {
            "current_price": 200.0, "high_52w": 220.0,
            "current_volume": 5_000_000, "avg_volume_30d": 1_000_000,
            "return_5d": 0.10,
        },
        "SPY": {"current_price": 500.0, "high_52w": 520.0,
                "current_volume": 80_000_000, "avg_volume_30d": 70_000_000,
                "return_5d": 0.05},
    }
    results = run_screener(
        ["NVDA", "AMZN"],
        price_data=price_data,
        exclude=["NVDA"],
        max_results=5,
    )
    tickers = [r.ticker for r in results]
    assert "NVDA" not in tickers
    assert "AMZN" in tickers


def test_no_qualifying_tickers():
    """Returns empty list when nothing meets any threshold."""
    price_data = {
        "XYZ": {
            "current_price": 50.0, "high_52w": 100.0,
            "current_volume": 100_000, "avg_volume_30d": 1_000_000,  # low vol
            "return_5d": -0.05,   # negative return
        },
        "SPY": {"current_price": 500.0, "high_52w": 520.0,
                "current_volume": 80_000_000, "avg_volume_30d": 70_000_000,
                "return_5d": 0.01},
    }
    results = run_screener(["XYZ"], price_data=price_data, max_results=3)
    assert results == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_screener.py -v
```

Expected: the 4 new tests fail (empty list returned or wrong order).

- [ ] **Step 3: Verify tests pass (logic already implemented)**

The multi-criterion, max_results, exclude, and no-qualifying logic is already in `run_screener()` from Task 3. Re-run:

```bash
.venv/bin/python -m pytest tests/test_screener.py -v
```

Expected: all 8 tests `PASSED`. If any fail, debug the scoring loop in `run_screener()` — check that `score` accumulates across all three criteria before appending to `candidates`.

- [ ] **Step 4: Commit**

```bash
git add tests/test_screener.py
git commit -m "test(screener): add multi-criterion, exclude, max_results, empty-result tests"
```

---

## Task 7: Internal yfinance batch fetch

**Files:**
- Modify: `src/data/screener.py` (replace `_fetch_screener_data` stub)

- [ ] **Step 1: Replace the stub with the real implementation**

In `src/data/screener.py`, replace the existing `_fetch_screener_data` stub with:

```python
def _fetch_screener_data(universe: list[str]) -> dict:
    """Batch-fetch 1-year OHLCV for universe tickers + SPY via yfinance.

    Returns a dict keyed by ticker with the shape documented in run_screener().
    Caches results for _CACHE_TTL seconds (shared across all universe calls).
    """
    global _screener_cache

    cached = _screener_cache.get("data")
    fetched_at = _screener_cache.get("fetched_at")
    if cached is not None and fetched_at is not None:
        age = (datetime.utcnow() - fetched_at).total_seconds()
        if age < _CACHE_TTL:
            return cached

    try:
        import yfinance as yf
    except ImportError:
        logger.warning("Screener: yfinance not installed — returning empty data")
        return {}

    all_tickers = sorted(set(universe) | {"SPY"})
    try:
        raw = yf.download(
            all_tickers,
            period="1y",
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
    except Exception as e:
        logger.warning("Screener: yf.download failed: %s", e)
        return {}

    result: dict = {}
    for ticker in all_tickers:
        try:
            df = raw[ticker] if len(all_tickers) > 1 else raw
            if df is None or df.empty or len(df) < 6:
                continue
            close = df["Close"].dropna()
            volume = df["Volume"].dropna()
            if close.empty or volume.empty:
                continue
            result[ticker] = {
                "current_price": round(float(close.iloc[-1]), 4),
                "high_52w": round(float(close.max()), 4),
                "current_volume": int(volume.iloc[-1]),
                "avg_volume_30d": int(volume.tail(30).mean()),
                "return_5d": round(
                    (float(close.iloc[-1]) - float(close.iloc[-6])) / float(close.iloc[-6]), 6
                ),
            }
        except Exception as e:
            logger.warning("Screener: failed to process %s: %s", ticker, e)

    _screener_cache["data"] = result
    _screener_cache["fetched_at"] = datetime.utcnow()
    return result
```

- [ ] **Step 2: Verify existing tests still pass (no yfinance called because price_data is always provided in tests)**

```bash
.venv/bin/python -m pytest tests/test_screener.py -v
```

Expected: all 8 tests `PASSED`.

- [ ] **Step 3: Commit**

```bash
git add src/data/screener.py
git commit -m "feat(screener): implement yfinance batch fetch with 5-min cache"
```

---

## Task 8: Update strategy.py

**Files:**
- Modify: `src/bot/strategy.py`
- Modify: `tests/test_strategy.py`

- [ ] **Step 1: Write failing test**

Open `tests/test_strategy.py`. After the existing imports, add:

```python
from src.data.screener import ScreenCandidate
```

Then append a new test at the end of the file:

```python
def test_build_market_context_with_screen_candidates():
    """Screened candidates appear in a labelled section in the prompt."""
    positions = []
    cash = make_cash()
    watchlist = ["AAPL", "TSLA"]
    instruments = [make_instrument("AAPL_US_EQ", "Apple Inc.")]
    candidates = [
        ScreenCandidate(
            ticker="PLTR",
            trigger="volume_spike+rs_vs_spy",
            score=1.8,
            details="vol=4.2× avg, RS=+6.1pp vs SPY",
        )
    ]
    result = _build_market_context(
        positions, cash, watchlist, instruments,
        screen_candidates=candidates,
    )
    assert "=== SCREENED CANDIDATES (this cycle only) ===" in result
    assert "PLTR" in result
    assert "vol=4.2× avg, RS=+6.1pp vs SPY" in result
    assert "volume_spike+rs_vs_spy" in result
    assert "not permanent watchlist members" in result


def test_build_market_context_without_screen_candidates():
    """No screened section rendered when screen_candidates is None."""
    positions = []
    cash = make_cash()
    watchlist = ["AAPL"]
    instruments = []
    result = _build_market_context(positions, cash, watchlist, instruments)
    assert "SCREENED CANDIDATES" not in result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_strategy.py::test_build_market_context_with_screen_candidates tests/test_strategy.py::test_build_market_context_without_screen_candidates -v
```

Expected: `TypeError` — `_build_market_context` does not accept `screen_candidates`.

- [ ] **Step 3: Update SYSTEM_PROMPT**

In `src/bot/strategy.py`, find the SYSTEM_PROMPT string (lines 23–53). Change this line:

```python
- Only generate signals for tickers on the watchlist.
```

to:

```python
- Only generate signals for tickers on the watchlist or listed under SCREENED CANDIDATES.
```

- [ ] **Step 4: Update `_build_market_context()` signature and add screened section**

In `src/bot/strategy.py`, update the `_build_market_context()` signature (line ~196) to add the new parameter:

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
    screen_candidates: list | None = None,
) -> str:
```

Inside `_build_market_context()`, add this block just before the `context = f"""..."""` template (after the `regime_section` block):

```python
    screened_section = ""
    if screen_candidates:
        sc_lines = []
        for c in screen_candidates:
            sc_lines.append(f"  {c.ticker}: {c.details} — {c.trigger}")
        screened_section = (
            "\n=== SCREENED CANDIDATES (this cycle only) ===\n"
            + "\n".join(sc_lines)
            + "\n  (apply same signal discipline; these are not permanent watchlist members)\n"
        )
```

In the `context = f"""..."""` template at the end of `_build_market_context()`, change the `=== WATCHLIST ===` block from:

```python
=== WATCHLIST ===
{json.dumps({t: instrument_info.get(t, t) for t in watchlist}, indent=2)}
```

to:

```python
=== WATCHLIST ===
{json.dumps({t: instrument_info.get(t, t) for t in watchlist}, indent=2)}
{screened_section}
```

- [ ] **Step 5: Update `generate_signals()` signature and price fetch**

In `src/bot/strategy.py`, update `generate_signals()` (line ~344) to add the parameter:

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
        screen_candidates: list | None = None,
    ) -> list[TradeSignal]:
```

Inside `generate_signals()`, replace the single line:

```python
        price_data = get_price_summary(watchlist)
```

with:

```python
        all_tickers = watchlist + [c.ticker for c in (screen_candidates or [])]
        price_data = get_price_summary(all_tickers)
```

And update the `_build_market_context()` call to pass `screen_candidates`:

```python
        user_prompt = _build_market_context(
            positions, cash, watchlist, instruments, price_data,
            earnings_info, news_data, macro_events, outcome_log,
            regime=regime,
            prediction_markets=prediction_markets,
            screen_candidates=screen_candidates,
        )
```

- [ ] **Step 6: Run all tests**

```bash
.venv/bin/python -m pytest tests/test_strategy.py tests/test_screener.py -v
```

Expected: all tests `PASSED`.

- [ ] **Step 7: Commit**

```bash
git add src/bot/strategy.py tests/test_strategy.py
git commit -m "feat(strategy): add screen_candidates prompt section and extend price fetch"
```

---

## Task 9: Update engine.py

**Files:**
- Modify: `src/bot/engine.py`

- [ ] **Step 1: Add screener call in `_cycle()`**

In `src/bot/engine.py`, add the import at the top of the file (with the other `src.data` imports, around line 24):

```python
from src.data.screener import ScreenCandidate
```

In `_cycle()`, find the `prediction_markets` fetch line (line ~316):

```python
            prediction_markets = get_prediction_market_context(settings.WATCHLIST)
```

Immediately after it, add:

```python
            # Run dynamic screener (opt-in; no-op when ENABLE_SCREENER=False)
            screen_candidates: list[ScreenCandidate] = []
            if settings.ENABLE_SCREENER:
                from src.data.screener import run_screener, SP500_TOP100
                try:
                    screen_candidates = run_screener(
                        SP500_TOP100,
                        exclude=settings.WATCHLIST,
                        max_results=settings.MAX_SCREENER_ADDITIONS,
                    )
                    logger.info(
                        "Screener found %d candidates: %s",
                        len(screen_candidates),
                        [c.ticker for c in screen_candidates],
                    )
                except Exception as e:
                    logger.warning("Screener failed — proceeding without candidates: %s", e)
```

- [ ] **Step 2: Pass `screen_candidates` to `generate_signals()`**

In `_cycle()`, find the `generate_signals()` call (line ~319). Add the new parameter:

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
                screen_candidates=screen_candidates,
            )
```

- [ ] **Step 3: Run the full test suite**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all tests `PASSED`. If any test fails, check that `screen_candidates=[]` default doesn't break existing strategy call paths.

- [ ] **Step 4: Verify import works cleanly**

```bash
.venv/bin/python -c "from src.bot.engine import TradingEngine; print('import OK')"
```

Expected: `import OK`

- [ ] **Step 5: Commit**

```bash
git add src/bot/engine.py
git commit -m "feat(engine): call screener in _cycle() and pass candidates to generate_signals"
```

---

## Task 10: Final verification and PR

- [ ] **Step 1: Run full test suite**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 2: Verify ENABLE_SCREENER=False leaves cycle unchanged**

```bash
.venv/bin/python -c "
from src.config.settings import settings
assert settings.ENABLE_SCREENER == False
assert settings.MAX_SCREENER_ADDITIONS == 3
print('Settings OK — screener disabled by default')
"
```

- [ ] **Step 3: Check screener module imports cleanly**

```bash
.venv/bin/python -c "
from src.data.screener import run_screener, SP500_TOP100, ScreenCandidate
assert len(SP500_TOP100) == 100
print(f'SP500_TOP100 has {len(SP500_TOP100)} tickers — OK')
"
```

- [ ] **Step 4: Open PR**

```bash
git push -u origin feat/dynamic-screener
gh pr create \
  --title "feat: dynamic watchlist screener (issue #47)" \
  --body "$(cat <<'EOF'
## Summary
- Adds `src/data/screener.py` with volume spike, RS vs SPY, and near-52w-high criteria
- New `ENABLE_SCREENER` / `MAX_SCREENER_ADDITIONS` settings (both off/3 by default)
- Screened candidates injected into Claude prompt as a distinct labelled section
- Risk manager and earnings calendar unchanged — screened tickers treated identically to watchlist

Closes #47

## Test plan
- [ ] Run `pytest tests/test_screener.py -v` — all 8 unit tests pass (no network)
- [ ] Run full suite `pytest tests/ -v` — no regressions
- [ ] Set `ENABLE_SCREENER=true` in `.env`, run the bot, confirm screener log line appears
- [ ] Verify `=== SCREENED CANDIDATES ===` appears in strategy prompt when candidates found

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
