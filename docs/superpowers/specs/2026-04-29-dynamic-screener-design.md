# Dynamic Watchlist Screener — Design Spec

**Issue:** [#47](https://github.com/pkhaninejad/Claude-trade-bot/issues/47)
**Date:** 2026-04-29
**Status:** Approved

---

## Problem

The bot only ever evaluates the static `WATCHLIST` env var. Episodic opportunities (volume surges, breakouts, momentum shifts) in other S&P 500 components are invisible to it. This spec adds an optional screener that surfaces up to N candidates per cycle without modifying the permanent watchlist.

---

## Scope

- New file: `src/data/screener.py`
- Modified: `src/bot/engine.py`, `src/bot/strategy.py`, `src/config/settings.py`
- New test: `tests/test_screener.py`
- Screened candidates are cycle-transient — they are never persisted and never alter `settings.WATCHLIST`
- Risk manager applies unchanged to screened tickers
- Feature is opt-in: `ENABLE_SCREENER=false` by default

---

## Data Model

```python
@dataclass
class ScreenCandidate:
    ticker: str
    trigger: str   # e.g. "volume_spike", "rs_vs_spy", "near_52w_high", "volume_spike+rs_vs_spy"
    score: float   # composite float for ranking; higher = stronger signal
    details: str   # human-readable, e.g. "vol=4.2× avg, RS=+6.1pp vs SPY"
```

`details` is built in `screener.py` at screening time and injected verbatim into the Claude prompt.

---

## `src/data/screener.py`

### Candidate universe

`SP500_TOP100: list[str]` — top 100 S&P 500 components by market cap, hardcoded at module level. Stable enough to not need an API.

### Public interface

```python
def run_screener(
    universe: list[str],
    price_data: dict | None = None,   # None → fetch internally; pass mock dict for tests
    exclude: list[str] | None = None, # tickers to suppress from output (e.g. permanent watchlist)
    max_results: int = 3,
) -> list[ScreenCandidate]:
```

When `price_data` is `None` the module fetches via `yf.download(universe + ["SPY"], period="1y", group_by="ticker")` in a single batch call. Results are cached for 300 seconds keyed on `frozenset(universe)`.

SPY data is used for the RS criterion and is never included in candidate output.

### Screening criteria

All three criteria use data from the 1-year history:

| Criterion | Condition | Score contribution |
|---|---|---|
| `volume_spike` | today's volume ≥ 2.5× 30d avg | 1.0 |
| `rs_vs_spy` | 5-day return ≥ SPY 5-day return + 3pp | 0.5 + (rs_delta / 10) capped at 1.0 |
| `near_52w_high` | `(high_52w − current) / high_52w ≤ 0.02` | 0.5 + (1 − gap_pct / 0.02) × 0.5 |

where `gap_pct = (high_52w − current) / high_52w`. Score = 1.0 when exactly at 52w high, 0.5 when 2% below.

A ticker matching multiple criteria carries a combined trigger string (`"volume_spike+rs_vs_spy"`) and summed score.

### Selection

After scoring all universe tickers, filter to those passing ≥ 1 criterion, remove any ticker present in `exclude` (the engine passes `settings.WATCHLIST`), sort descending by score, return the top `max_results`.

---

## `src/config/settings.py` changes

```python
ENABLE_SCREENER: bool = False
MAX_SCREENER_ADDITIONS: int = 3
```

---

## `src/bot/engine.py` changes

In `_cycle()`, after the existing `earnings_info / news_data / macro_events / prediction_markets` fetches and before `generate_signals()`:

```python
screen_candidates: list[ScreenCandidate] = []
if settings.ENABLE_SCREENER:
    from src.data.screener import run_screener, SP500_TOP100
    screen_candidates = run_screener(
        SP500_TOP100,
        exclude=settings.WATCHLIST,
        max_results=settings.MAX_SCREENER_ADDITIONS,
    )
    logger.info("Screener found %d candidates: %s",
                len(screen_candidates), [c.ticker for c in screen_candidates])
```

Pass `screen_candidates` to `generate_signals()`. The price feed inside `generate_signals()` is already called with the extended ticker list (see strategy changes below), so no separate price fetch is needed in the engine.

---

## `src/bot/strategy.py` changes

### `generate_signals()` signature

Add `screen_candidates: list | None = None` parameter (typed as `list[ScreenCandidate]`).

Inside `generate_signals()`, extend the ticker list passed to `get_price_summary()`:

```python
all_tickers = watchlist + [c.ticker for c in (screen_candidates or [])]
price_data = get_price_summary(all_tickers)
```

Pass `screen_candidates` down to `_build_market_context()`.

### `_build_market_context()` changes

Replace the current `=== WATCHLIST ===` block with two sections:

```
=== WATCHLIST ===
  [permanent] NVDA, AAPL, TSLA, ...

=== SCREENED CANDIDATES (this cycle only) ===
  PLTR: vol=4.2× avg, RS=+6.1pp vs SPY — volume_spike+rs_vs_spy
  META: 1.8% from 52w high — near_52w_high
  (apply same signal discipline; these are not permanent watchlist members)
```

If `screen_candidates` is empty or None, only the `=== WATCHLIST ===` section is rendered (existing behaviour preserved).

### SYSTEM_PROMPT change

Update the constraint line from:

> Only generate signals for tickers on the watchlist.

To:

> Only generate signals for tickers on the watchlist or listed under SCREENED CANDIDATES.

---

## `tests/test_screener.py`

Unit tests using mocked `price_data` dicts (no yfinance calls):

| Test | What it verifies |
|---|---|
| `test_volume_spike_detected` | ticker with vol ≥ 2.5× avg passes, others don't |
| `test_rs_vs_spy_detected` | 5-day return exceeds SPY by ≥ 3pp |
| `test_near_52w_high_detected` | price within 2% of 52w high |
| `test_multi_criterion_score` | ticker matching 2 criteria has combined score > single-criterion ticker |
| `test_max_results_limit` | only top N returned even if more qualify |
| `test_watchlist_tickers_excluded` | tickers already in watchlist are filtered out |
| `test_empty_universe` | returns empty list, no error |
| `test_no_qualifying_tickers` | returns empty list when nothing passes thresholds |

---

## Error handling

- `yf.download()` failures are caught and logged; screener returns `[]` (cycle proceeds with permanent watchlist only)
- Individual ticker data gaps (missing volume, no 52w history) skip that ticker silently
- Screener errors never propagate to the main cycle — logged as warnings

---

## What does NOT change

- `RiskManager` — no special treatment for screened tickers
- `EarningsCalendar` / `NewsFeed` — only called for `settings.WATCHLIST`; screened tickers are not checked for earnings windows (acceptable trade-off; risk manager's confidence threshold still protects)
- Dashboard — no new endpoints needed; screened tickers appear in signal history naturally if signals are generated
- In-memory state — screen candidates are not persisted between cycles

---

## Environment variables

```
ENABLE_SCREENER=false
MAX_SCREENER_ADDITIONS=3
```
