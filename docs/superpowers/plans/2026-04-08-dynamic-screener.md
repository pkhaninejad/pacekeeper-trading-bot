# Dynamic Watchlist Screener Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a momentum screener that surfaces up to N S&P 500 tickers per cycle and injects them into signal generation as transient candidates.

**Architecture:** A new `src/data/screener.py` fetches 1-year yfinance data for a hardcoded S&P 500 universe (separate cache from the watchlist price feed), scores each ticker against three criteria (volume spike, relative strength vs SPY, near 52-week high), and returns the top-N `ScreenCandidate` objects. The engine expands the cycle's ticker list with these candidates; the strategy renders a distinct prompt section for them. Risk management is unchanged.

**Tech Stack:** yfinance (already installed), Python dataclasses, ThreadPoolExecutor (already used in `price_feed.py`), pytest with `unittest.mock.patch`.

---

## File Map

| File | Change |
|---|---|
| `src/data/screener.py` | **Create** — ScreenCandidate, SP500_TOP100, fetch/cache, scoring, run_screener |
| `src/config/settings.py` | **Modify** — add ENABLE_SCREENER, MAX_SCREENER_ADDITIONS |
| `.env.example` | **Modify** — document new env vars |
| `src/bot/engine.py` | **Modify** — call screener, build cycle_tickers, pass screened to strategy |
| `src/bot/strategy.py` | **Modify** — accept screened_candidates, add prompt section, update system prompt rule |
| `tests/test_screener.py` | **Create** — unit tests with mocked _get_screener_data |

---

## Task 1: Settings + .env.example

**Files:**
- Modify: `src/config/settings.py`
- Modify: `.env.example`
- Modify: `tests/test_settings.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_settings.py`:

```python
def test_screener_disabled_by_default(self):
    s = Settings()
    assert s.ENABLE_SCREENER is False

def test_screener_max_additions_default(self):
    s = Settings()
    assert s.MAX_SCREENER_ADDITIONS == 3

def test_screener_can_be_enabled(self):
    s = Settings(ENABLE_SCREENER=True, MAX_SCREENER_ADDITIONS=5)
    assert s.ENABLE_SCREENER is True
    assert s.MAX_SCREENER_ADDITIONS == 5
```

- [ ] **Step 2: Run to confirm failure**

```bash
.venv/bin/python -m pytest tests/test_settings.py -v -k "screener"
```

Expected: `AttributeError: 'Settings' object has no attribute 'ENABLE_SCREENER'`

- [ ] **Step 3: Add settings to `src/config/settings.py`**

After the `NEWS_CACHE_TTL_SECONDS` line (line 51), add:

```python
    # Screener
    ENABLE_SCREENER: bool = False         # Set True to enable dynamic candidate screening
    MAX_SCREENER_ADDITIONS: int = 3       # Max screened tickers injected per cycle
```

- [ ] **Step 4: Add to `.env.example`**

After the `NEWS_CACHE_TTL_SECONDS=900` line, add:

```
# ── Dynamic screener ──────────────────────────────────────────────────────────
# Screens S&P 500 for high-momentum tickers and injects them as transient candidates
ENABLE_SCREENER=false
MAX_SCREENER_ADDITIONS=3
```

- [ ] **Step 5: Run tests to confirm pass**

```bash
.venv/bin/python -m pytest tests/test_settings.py -v -k "screener"
```

Expected: 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/config/settings.py .env.example tests/test_settings.py
git commit -m "feat: add ENABLE_SCREENER and MAX_SCREENER_ADDITIONS settings"
```

---

## Task 2: Screener module — data types, universe, fetch

**Files:**
- Create: `src/data/screener.py`
- Create: `tests/test_screener.py`

- [ ] **Step 1: Write failing tests for ScreenCandidate and SP500_TOP100**

Create `tests/test_screener.py`:

```python
"""Unit tests for src/data/screener.py"""
import pytest
from unittest.mock import patch
from src.data.screener import ScreenCandidate, SP500_TOP100, run_screener, _score_candidate


def _make_data(
    current: float = 100.0,
    high_52w: float = 102.0,
    avg_vol_30d: float = 1_000_000,
    today_vol: float = 1_000_000,
    ret_5d: float = 0.0,
) -> dict:
    return {
        "current": current,
        "high_52w": high_52w,
        "avg_vol_30d": avg_vol_30d,
        "today_vol": today_vol,
        "ret_5d": ret_5d,
    }


class TestScreenCandidate:
    def test_fields(self):
        c = ScreenCandidate(ticker="AAPL", trigger="vol=3.0× avg", score=0.5)
        assert c.ticker == "AAPL"
        assert c.trigger == "vol=3.0× avg"
        assert c.score == 0.5


class TestSP500Universe:
    def test_has_100_entries(self):
        assert len(SP500_TOP100) == 100

    def test_no_duplicates(self):
        assert len(SP500_TOP100) == len(set(SP500_TOP100))

    def test_spy_not_included(self):
        assert "SPY" not in SP500_TOP100
```

- [ ] **Step 2: Run to confirm failure**

```bash
.venv/bin/python -m pytest tests/test_screener.py::TestScreenCandidate tests/test_screener.py::TestSP500Universe -v
```

Expected: `ModuleNotFoundError: No module named 'src.data.screener'`

- [ ] **Step 3: Create `src/data/screener.py` with data types and universe**

```python
"""
Dynamic watchlist screener — surfaces high-momentum S&P 500 candidates.

Fetches 1-year OHLCV for a hardcoded universe (separate from the 3-month
watchlist price feed) and scores against three criteria:
  - Volume spike: today's volume >= 2.5x 30-day average
  - Relative strength vs SPY: 5-day return >= SPY + 3pp
  - Near 52-week high: current price within 2% of 52w high

Results are cached for 15 minutes. Returns up to max_results ScreenCandidates,
excluding tickers already in the permanent watchlist.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

CACHE_TTL = 900  # 15 minutes

_cache: dict[str, dict] = {}
_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="screener")

SP500_TOP100: list[str] = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "BRK-B", "JPM",
    "UNH", "LLY", "V", "AVGO", "XOM", "MA", "JNJ", "PG", "HD", "ABBV", "MRK",
    "KO", "COST", "BAC", "WMT", "CVX", "CRM", "AMD", "NFLX", "MCD", "PEP",
    "TMO", "ABT", "LIN", "ACN", "CSCO", "DHR", "NKE", "ADBE", "DIS", "WFC",
    "TXN", "NEE", "ORCL", "UPS", "PM", "VZ", "BMY", "CMCSA", "RTX", "QCOM",
    "T", "LOW", "INTU", "AMGN", "SPGI", "HON", "IBM", "GS", "CAT", "BA",
    "DE", "SCHW", "SBUX", "MDLZ", "BLK", "AXP", "GE", "AMAT", "ADP", "GILD",
    "C", "LMT", "ISRG", "MU", "BKNG", "PLD", "REGN", "CI", "SYK", "ZTS",
    "ADI", "NOW", "PANW", "LRCX", "VRTX", "EOG", "COP", "SLB", "MMC", "TJX",
    "BSX", "ELV", "UBER", "PLTR", "KLAC", "SNPS", "CDNS", "FTNT", "MCHP",
]


@dataclass
class ScreenCandidate:
    ticker: str
    trigger: str   # human-readable description of matched criteria
    score: float   # composite 0.0–1.0; higher = stronger signal
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
.venv/bin/python -m pytest tests/test_screener.py::TestScreenCandidate tests/test_screener.py::TestSP500Universe -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/data/screener.py tests/test_screener.py
git commit -m "feat: add ScreenCandidate dataclass and SP500_TOP100 universe"
```

---

## Task 3: Screener — fetch, cache, scoring, run_screener

**Files:**
- Modify: `src/data/screener.py`
- Modify: `tests/test_screener.py`

- [ ] **Step 1: Write failing tests for _score_candidate and run_screener**

Append to `tests/test_screener.py`:

```python
class TestScoreCandidate:
    def test_volume_spike_detected(self):
        data = _make_data(today_vol=2_600_000, avg_vol_30d=1_000_000)
        trigger, score = _score_candidate(data, spy_ret_5d=0.0)
        assert trigger is not None
        assert "vol=" in trigger
        assert score > 0

    def test_volume_spike_not_detected_below_threshold(self):
        data = _make_data(today_vol=2_000_000, avg_vol_30d=1_000_000)  # 2.0× < 2.5×
        trigger, score = _score_candidate(data, spy_ret_5d=0.0)
        assert trigger is None
        assert score == 0.0

    def test_relative_strength_detected(self):
        data = _make_data(ret_5d=5.0)
        trigger, score = _score_candidate(data, spy_ret_5d=1.0)  # diff=4pp >= 3pp
        assert trigger is not None
        assert "RS=" in trigger

    def test_relative_strength_not_detected(self):
        data = _make_data(ret_5d=2.0)
        trigger, score = _score_candidate(data, spy_ret_5d=0.0)  # diff=2pp < 3pp
        assert trigger is None

    def test_near_52w_high_detected(self):
        data = _make_data(current=99.0, high_52w=100.0)  # 1% from high
        trigger, score = _score_candidate(data, spy_ret_5d=0.0)
        assert trigger is not None
        assert "52w high" in trigger

    def test_not_near_52w_high(self):
        data = _make_data(current=90.0, high_52w=100.0)  # 10% from high
        trigger, score = _score_candidate(data, spy_ret_5d=0.0)
        assert trigger is None

    def test_multiple_criteria_increase_score(self):
        # Both volume spike and near 52w high
        data = _make_data(
            today_vol=3_000_000, avg_vol_30d=1_000_000,
            current=99.5, high_52w=100.0,
        )
        _, score_multi = _score_candidate(data, spy_ret_5d=0.0)
        # Single criterion only
        data_single = _make_data(today_vol=3_000_000, avg_vol_30d=1_000_000)
        _, score_single = _score_candidate(data_single, spy_ret_5d=0.0)
        assert score_multi > score_single

    def test_score_capped_at_1(self):
        # Extreme values — score must not exceed 1.0
        data = _make_data(
            today_vol=100_000_000, avg_vol_30d=1_000_000,
            current=99.99, high_52w=100.0,
            ret_5d=50.0,
        )
        _, score = _score_candidate(data, spy_ret_5d=0.0)
        assert score <= 1.0


class TestRunScreener:
    def _patch_data(self, data: dict):
        return patch("src.data.screener._get_screener_data", return_value=data)

    def test_returns_screen_candidates(self):
        data = {
            "SPY": _make_data(ret_5d=0.0),
            "GOOG": _make_data(today_vol=3_000_000, avg_vol_30d=1_000_000),
        }
        with self._patch_data(data):
            result = run_screener(["GOOG"], watchlist=[], max_results=3)
        assert len(result) == 1
        assert isinstance(result[0], ScreenCandidate)
        assert result[0].ticker == "GOOG"

    def test_max_results_respected(self):
        data = {
            "SPY": _make_data(ret_5d=0.0),
            "A": _make_data(today_vol=3_000_000, avg_vol_30d=1_000_000),
            "B": _make_data(today_vol=3_000_000, avg_vol_30d=1_000_000),
            "C": _make_data(today_vol=3_000_000, avg_vol_30d=1_000_000),
            "D": _make_data(today_vol=3_000_000, avg_vol_30d=1_000_000),
        }
        with self._patch_data(data):
            result = run_screener(["A", "B", "C", "D"], watchlist=[], max_results=2)
        assert len(result) <= 2

    def test_watchlist_tickers_excluded(self):
        data = {
            "SPY": _make_data(ret_5d=0.0),
            "AAPL": _make_data(today_vol=3_000_000, avg_vol_30d=1_000_000),
            "GOOG": _make_data(today_vol=3_000_000, avg_vol_30d=1_000_000),
        }
        with self._patch_data(data):
            result = run_screener(["AAPL", "GOOG"], watchlist=["AAPL"], max_results=3)
        tickers = [c.ticker for c in result]
        assert "AAPL" not in tickers
        assert "GOOG" in tickers

    def test_empty_universe_returns_empty(self):
        with self._patch_data({"SPY": _make_data()}):
            result = run_screener([], watchlist=[], max_results=3)
        assert result == []

    def test_no_qualifying_tickers_returns_empty(self):
        data = {
            "SPY": _make_data(ret_5d=0.0),
            "GOOG": _make_data(),  # no spike, no RS, not near 52w high
        }
        with self._patch_data(data):
            result = run_screener(["GOOG"], watchlist=[], max_results=3)
        assert result == []

    def test_results_sorted_by_score_descending(self):
        # GOOG has higher vol ratio than AMZN
        data = {
            "SPY": _make_data(ret_5d=0.0),
            "GOOG": _make_data(today_vol=5_000_000, avg_vol_30d=1_000_000),  # 5× spike
            "AMZN": _make_data(today_vol=2_600_000, avg_vol_30d=1_000_000),  # 2.6× spike
        }
        with self._patch_data(data):
            result = run_screener(["GOOG", "AMZN"], watchlist=[], max_results=3)
        assert len(result) == 2
        assert result[0].ticker == "GOOG"
```

- [ ] **Step 2: Run to confirm failure**

```bash
.venv/bin/python -m pytest tests/test_screener.py -v -k "TestScoreCandidate or TestRunScreener"
```

Expected: `ImportError: cannot import name '_score_candidate' from 'src.data.screener'`

- [ ] **Step 3: Append fetch, cache, scoring, and run_screener to `src/data/screener.py`**

Add after the `ScreenCandidate` dataclass:

```python

def _is_fresh(entry: dict) -> bool:
    return (datetime.utcnow() - entry["fetched_at"]).total_seconds() < CACHE_TTL


def _fetch_screener_data(ticker: str) -> Optional[dict]:
    """Fetch 1-year OHLCV for a single ticker. Runs in a thread executor."""
    try:
        import yfinance as yf
    except ImportError:
        return None

    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1y", auto_adjust=True)
        if hist.empty or len(hist) < 10:
            return None

        closes = hist["Close"].dropna().tolist()
        volumes = hist["Volume"].dropna().tolist()
        if not closes or not volumes:
            return None

        current = closes[-1]
        high_52w = max(closes)
        window = volumes[-30:] if len(volumes) >= 30 else volumes
        avg_vol_30d = sum(window) / len(window)
        today_vol = float(volumes[-1])
        ret_5d = ((closes[-1] - closes[-6]) / closes[-6] * 100) if len(closes) >= 6 else 0.0

        return {
            "current": current,
            "high_52w": high_52w,
            "avg_vol_30d": avg_vol_30d,
            "today_vol": today_vol,
            "ret_5d": ret_5d,
        }
    except Exception as e:
        logger.warning("Screener fetch failed for %s: %s", ticker, e)
        return None


def _get_screener_data(tickers: list[str]) -> dict[str, dict]:
    """Return screening data for tickers, using 15-min cache where fresh."""
    stale = [t for t in tickers if t not in _cache or not _is_fresh(_cache[t])]
    result = {t: _cache[t]["data"] for t in tickers if t not in stale}

    if not stale:
        return result

    futures = {_executor.submit(_fetch_screener_data, t): t for t in stale}
    for future in as_completed(futures, timeout=30):
        ticker = futures[future]
        try:
            data = future.result()
            if data:
                _cache[ticker] = {"data": data, "fetched_at": datetime.utcnow()}
                result[ticker] = data
        except Exception as e:
            logger.warning("Screener thread error for %s: %s", ticker, e)

    return result


def _score_candidate(data: dict, spy_ret_5d: float) -> tuple[str | None, float]:
    """
    Check all three screening criteria. Returns (trigger_description, score)
    where trigger is None if no criterion matched.
    Score accumulates across matched criteria (capped at 1.0).
    """
    triggers: list[str] = []
    score = 0.0

    # Criterion 1: volume spike >= 2.5× 30-day average
    if data["avg_vol_30d"] > 0:
        vol_ratio = data["today_vol"] / data["avg_vol_30d"]
        if vol_ratio >= 2.5:
            triggers.append(f"vol={vol_ratio:.1f}× avg")
            score += vol_ratio / 10.0

    # Criterion 2: 5-day return >= SPY 5-day return + 3pp
    rs_diff = data["ret_5d"] - spy_ret_5d
    if rs_diff >= 3.0:
        triggers.append(f"RS=+{rs_diff:.1f}pp vs SPY")
        score += rs_diff / 20.0

    # Criterion 3: current price within 2% of 52-week high
    if data["high_52w"] > 0:
        pct_from_high = (data["high_52w"] - data["current"]) / data["high_52w"] * 100
        if pct_from_high <= 2.0:
            triggers.append(f"{pct_from_high:.1f}% from 52w high")
            score += (2.0 - pct_from_high) / 2.0

    if not triggers:
        return None, 0.0

    return " — ".join(triggers), min(score, 1.0)


def run_screener(
    universe: list[str],
    watchlist: list[str],
    max_results: int = 3,
) -> list[ScreenCandidate]:
    """
    Screen universe tickers against momentum criteria.

    Excludes tickers already in watchlist. Fetches SPY to compute relative
    strength baseline. Returns up to max_results candidates sorted by score.
    """
    try:
        import yfinance  # noqa — check availability before network calls
    except ImportError:
        logger.warning("yfinance not installed — screener returning empty")
        return []

    watchlist_set = set(watchlist)
    candidates_universe = [t for t in universe if t not in watchlist_set]
    if not candidates_universe:
        return []

    all_tickers = candidates_universe + ["SPY"]
    data = _get_screener_data(all_tickers)
    spy_ret_5d = (data.get("SPY") or {}).get("ret_5d", 0.0)

    candidates: list[ScreenCandidate] = []
    for ticker in candidates_universe:
        d = data.get(ticker)
        if d is None:
            continue
        trigger, score = _score_candidate(d, spy_ret_5d)
        if trigger:
            candidates.append(ScreenCandidate(ticker=ticker, trigger=trigger, score=score))

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:max_results]
```

- [ ] **Step 4: Run all screener tests**

```bash
.venv/bin/python -m pytest tests/test_screener.py -v
```

Expected: All tests PASS. (Tests that use `_patch_data` on `_get_screener_data` avoid real network calls.)

- [ ] **Step 5: Commit**

```bash
git add src/data/screener.py tests/test_screener.py
git commit -m "feat: implement screener fetch, scoring, and run_screener"
```

---

## Task 4: Engine integration

**Files:**
- Modify: `src/bot/engine.py`

The cycle currently calls `self.earnings.get_earnings_info(settings.WATCHLIST)` (line 306), `self.news.get_news(settings.WATCHLIST)` (line 309), and passes `settings.WATCHLIST` to `generate_signals` (line 315). All three must use `cycle_tickers` instead.

- [ ] **Step 1: Add imports to `src/bot/engine.py`**

After the existing `from src.data.news_feed import NewsFeed` import, add:

```python
from src.data.screener import ScreenCandidate, SP500_TOP100, run_screener
```

- [ ] **Step 2: Build cycle_tickers in `_cycle()`**

In `_cycle()`, after the instruments cache block (after line 281, the `except` block that ends the instruments loading), and before the earnings fetch, add:

```python
            # Run dynamic screener (if enabled) and extend this cycle's ticker list
            screened: list[ScreenCandidate] = []
            if settings.ENABLE_SCREENER:
                screened = run_screener(
                    SP500_TOP100,
                    watchlist=settings.WATCHLIST,
                    max_results=settings.MAX_SCREENER_ADDITIONS,
                )
                if screened:
                    logger.info(
                        "Screener found %d candidate(s): %s",
                        len(screened),
                        [c.ticker for c in screened],
                    )

            cycle_tickers = settings.WATCHLIST + [c.ticker for c in screened]
```

- [ ] **Step 3: Replace settings.WATCHLIST usages with cycle_tickers in _cycle()**

Change line 306:
```python
            earnings_info = self.earnings.get_earnings_info(settings.WATCHLIST)
```
To:
```python
            earnings_info = self.earnings.get_earnings_info(cycle_tickers)
```

Change line 309:
```python
            news_data = self.news.get_news(settings.WATCHLIST)
```
To:
```python
            news_data = self.news.get_news(cycle_tickers)
```

Change line 315 (the `generate_signals` call), replacing `settings.WATCHLIST` with `cycle_tickers` and adding `screened_candidates=screened`:

```python
            signals = self.strategy.generate_signals(
                positions, cash, cycle_tickers, instruments,
                provider_config=self._provider_config,
                earnings_info=earnings_info,
                news_data=news_data,
                macro_events=macro_events,
                outcome_log=self.outcome_log,
                regime=self._last_regime,
                screened_candidates=screened,
            )
```

- [ ] **Step 4: Run existing engine tests to confirm no regression**

```bash
.venv/bin/python -m pytest tests/test_engine_close.py tests/test_engine_outcomes.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bot/engine.py
git commit -m "feat: integrate screener into engine cycle, expand cycle_tickers"
```

---

## Task 5: Strategy integration

**Files:**
- Modify: `src/bot/strategy.py`

- [ ] **Step 1: Add ScreenCandidate import to `src/bot/strategy.py`**

At the top of the file, after:
```python
from src.bot.price_feed import get_price_summary
```
Add:
```python
from src.data.screener import ScreenCandidate
```

- [ ] **Step 2: Update the system prompt rule (line 27)**

Change:
```python
- Only generate signals for tickers on the watchlist.
```
To:
```python
- Only generate signals for tickers on the watchlist or listed as screened candidates.
```

- [ ] **Step 3: Add screened_candidates parameter to `_build_market_context()`**

Change the function signature at line 150 from:
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
    screened_candidates: "list[ScreenCandidate] | None" = None,
) -> str:
```

- [ ] **Step 4: Build screened_section and inject into the prompt**

In `_build_market_context()`, after the `regime_section` block (after the closing `"""` at line ~262), add:

```python
    screened_section = ""
    if screened_candidates:
        lines = [
            f"  {c.ticker}: {c.trigger}"
            for c in screened_candidates
        ]
        screened_section = (
            "\n=== SCREENED CANDIDATES (this cycle only) ===\n"
            + "\n".join(lines)
            + "\n  (transient additions — not permanent watchlist members;"
            " apply same signal discipline)\n"
        )
```

Then in the `context = f"""..."""` string (around line 264), insert `{screened_section}` just before `=== WATCHLIST ===`:

```python
    context = f"""Current datetime (UTC): {datetime.now(UTC).isoformat()}

=== PORTFOLIO ===
Free cash: {cash.free:.2f}
Total value: {cash.total:.2f}
Invested: {cash.invested:.2f}
Overall PnL: {cash.ppl:.2f}

Open positions ({len(positions)}):
{chr(10).join(pos_summary) if pos_summary else '  (none)'}

=== PRICE FEED (30-day) ===
{chr(10).join(price_lines) if price_lines else '  (unavailable)'}
{earnings_section}{macro_section}{news_section}{perf_section}{regime_section}{screened_section}
=== WATCHLIST ===
{json.dumps({t: instrument_info.get(t, t) for t in watchlist}, indent=2)}

=== TASK ===
Analyse the portfolio and market conditions using the price feed data.
Generate trading signals for up to 5 tickers.
Focus on tickers where there is a clear directional view.
Return ONLY a JSON array of TradeSignal objects.
"""
```

- [ ] **Step 5: Add screened_candidates parameter to `generate_signals()`**

Change the `generate_signals` method signature (line 293) from:
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
    ) -> list[TradeSignal]:
```
To:
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
        screened_candidates: "list[ScreenCandidate] | None" = None,
    ) -> list[TradeSignal]:
```

Then update the `_build_market_context` call inside `generate_signals` (line 311) to pass the new argument:

```python
        user_prompt = _build_market_context(
            positions, cash, watchlist, instruments, price_data,
            earnings_info, news_data, macro_events, outcome_log,
            regime=regime,
            screened_candidates=screened_candidates,
        )
```

- [ ] **Step 6: Run strategy tests to confirm no regression**

```bash
.venv/bin/python -m pytest tests/test_strategy.py -v
```

Expected: All tests PASS.

- [ ] **Step 7: Run full test suite**

```bash
.venv/bin/python -m pytest tests/ -v --ignore=tests/test_dashboard_positions_live.py
```

Expected: All tests PASS (live dashboard test excluded as it requires a real T212 connection).

- [ ] **Step 8: Commit**

```bash
git add src/bot/strategy.py
git commit -m "feat: inject screened candidates into strategy prompt"
```

---

## Task 6: GitHub issue update + PR

- [ ] **Step 1: Update issue #47 with implementation notes**

```bash
gh issue comment 47 --repo pkhaninejad/Claude-trade-bot --body "Implementation complete. PR incoming.

**Files added/modified:**
- \`src/data/screener.py\` — new: ScreenCandidate, SP500_TOP100, run_screener
- \`src/config/settings.py\` — ENABLE_SCREENER, MAX_SCREENER_ADDITIONS
- \`src/bot/engine.py\` — screener called at cycle start; cycle_tickers replaces settings.WATCHLIST
- \`src/bot/strategy.py\` — screened_candidates rendered as distinct prompt section
- \`tests/test_screener.py\` — 15 unit tests covering all three criteria + integration paths"
```

- [ ] **Step 2: Push branch and open PR**

```bash
git push -u origin HEAD
gh pr create \
  --title "feat: dynamic watchlist screener (issue #47)" \
  --body "$(cat <<'EOF'
## Summary

- Adds `src/data/screener.py` with `run_screener()` that screens the top-100 S&P 500 universe for volume spikes (≥2.5×), relative strength vs SPY (≥+3pp), and proximity to 52-week high (≤2%)
- Engine expands each cycle's ticker list with up to `MAX_SCREENER_ADDITIONS` candidates (default 3)
- Strategy renders a distinct `=== SCREENED CANDIDATES ===` prompt section so Claude knows they are transient
- Controlled by `ENABLE_SCREENER=false` (off by default)
- Risk manager unchanged — screened tickers get identical validation

Closes #47

## Test plan

- [ ] `pytest tests/test_screener.py -v` — 15 unit tests all pass
- [ ] `pytest tests/ -v --ignore=tests/test_dashboard_positions_live.py` — full suite passes
- [ ] Set `ENABLE_SCREENER=true` in `.env`, run bot, confirm screener log line appears at cycle start
- [ ] Confirm screened tickers appear in the Claude prompt under `=== SCREENED CANDIDATES ===`
- [ ] Confirm risk manager still rejects low-confidence screened signals

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
