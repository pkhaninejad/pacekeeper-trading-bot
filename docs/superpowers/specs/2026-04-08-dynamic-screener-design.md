# Dynamic Watchlist Screener — Design Spec

**Date:** 2026-04-08
**Issue:** [#47](https://github.com/pkhaninejad/Claude-trade-bot/issues/47)
**Status:** Approved

---

## Problem

The watchlist is a static env var. The bot misses episodic momentum opportunities (e.g. a 5× volume day on a ticker not in the list). A lightweight screener run each cycle surfaces candidates and injects them into that cycle's signal generation.

---

## Architecture

### New file: `src/data/screener.py`

Self-contained module. Has its own yfinance fetch with a 1-year period (required for 52-week high) and its own 15-minute in-process cache. Does not share the watchlist price feed cache (which uses a 3-month period).

```
ScreenCandidate
  ticker: str
  trigger: str       # "volume_spike" | "relative_strength" | "near_52w_high"
  score: float       # composite 0.0–1.0 for ranking when trimming to max_results

run_screener(
  universe: list[str],      # top-100 S&P 500 hardcoded list
  watchlist: list[str],     # exclude tickers already in watchlist
  max_results: int = 3,
) -> list[ScreenCandidate]
```

**Screening criteria (any one match qualifies a ticker):**

| Criterion | Threshold |
|---|---|
| Volume spike | today's volume ≥ 2.5× 30-day average |
| Relative strength vs SPY | 5-day return ≥ SPY 5-day return + 3pp |
| Near 52-week high | current price within 2% of 52-week high |

SPY is fetched as part of the screener's own fetch loop; its 5-day return is computed before scoring candidates.

**Candidate universe:** Hardcoded list of top 100 S&P 500 components by market cap (stable enough to not need an API). Tickers already in `settings.WATCHLIST` are excluded from the screened candidates (they are already in the cycle).

**Scoring:** Each matched criterion contributes equally. Ties broken by total matched criteria count, then volume ratio.

**Cache:** 15-minute TTL, keyed by universe hash + date. Prevents redundant yfinance calls within a cycle interval.

---

### Modified: `src/config/settings.py`

```python
ENABLE_SCREENER: bool = False
MAX_SCREENER_ADDITIONS: int = 3
```

`.env.example` updated with both keys.

---

### Modified: `src/bot/engine.py`

In `_cycle()`, after positions are fetched and instruments cache is loaded, and before earnings/news fetches:

```python
screened: list[ScreenCandidate] = []
if settings.ENABLE_SCREENER:
    screened = run_screener(
        SP500_TOP100,
        watchlist=settings.WATCHLIST,
        max_results=settings.MAX_SCREENER_ADDITIONS,
    )

cycle_tickers = settings.WATCHLIST + [c.ticker for c in screened]
```

`cycle_tickers` replaces all further uses of `settings.WATCHLIST` within that cycle (earnings, news, price feed, signal generation). The permanent `settings.WATCHLIST` is unchanged.

`_ticker_map` already handles unknown tickers via the instruments API; no special handling needed for screened tickers — they use the `TICKER_US_EQ` convention and the map is extended at startup.

---

### Modified: `src/bot/strategy.py`

`generate_signals()` and `_build_market_context()` gain a new parameter:

```python
screened_candidates: list["ScreenCandidate"] | None = None
```

A new prompt section is injected before `=== WATCHLIST ===`:

```
=== SCREENED CANDIDATES (this cycle only) ===
  PLTR: vol=4.2× avg, RS=+6.1pp vs SPY — volume_spike + relative_strength
  META: 1.8% from 52w high, RS=+3.4pp vs SPY — near_52w_high + relative_strength
  (transient additions — not permanent watchlist members; apply same signal discipline)
```

System prompt rule updated from:
> "Only generate signals for tickers on the watchlist."

To:
> "Only generate signals for tickers on the watchlist or listed as screened candidates."

---

## Data Flow (per cycle)

```
engine._cycle()
  → [if ENABLE_SCREENER] run_screener(SP500_TOP100, watchlist) → screened
  → cycle_tickers = WATCHLIST + screened tickers
  → earnings.get_earnings_info(cycle_tickers)
  → news.get_news(cycle_tickers)
  → strategy.generate_signals(..., watchlist=cycle_tickers, screened_candidates=screened)
      → get_price_summary(cycle_tickers)
      → _build_market_context(...) includes SCREENED CANDIDATES section
      → LLM call
  → risk.validate() — unchanged, screened tickers get no special treatment
  → _execute_signal() — unchanged
```

---

## Risk Manager

No changes. Screened candidates pass through the same validation as watchlist tickers: confidence ≥ 0.6, max open positions, cash availability, position size limits, earnings/macro blocks.

---

## Testing

`tests/test_screener.py` — unit tests with mocked price data:

- `test_volume_spike_detected` — ticker with vol ≥ 2.5× qualifies
- `test_volume_spike_not_detected` — ticker below threshold excluded
- `test_relative_strength_detected` — 5-day RS ≥ SPY + 3pp qualifies
- `test_near_52w_high_detected` — within 2% of high qualifies
- `test_max_results_respected` — returns at most N candidates
- `test_watchlist_excluded` — tickers already in watchlist not returned
- `test_empty_universe_returns_empty` — graceful empty input
- `test_screener_disabled_returns_empty` — when data unavailable, returns empty

---

## Environment Variables

```
ENABLE_SCREENER=false
MAX_SCREENER_ADDITIONS=3
```

---

## Files Touched

| File | Change |
|---|---|
| `src/data/screener.py` | New |
| `src/config/settings.py` | Add 2 settings |
| `src/bot/engine.py` | Call screener, expand cycle_tickers |
| `src/bot/strategy.py` | Accept + render screened_candidates |
| `.env.example` | Document new env vars |
| `tests/test_screener.py` | New unit tests |
