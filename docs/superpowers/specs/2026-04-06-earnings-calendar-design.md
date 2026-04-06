# Earnings Calendar — Design Spec

**Issue:** [#14](https://github.com/pkhaninejad/Claude-trade-bot/issues/14)
**Date:** 2026-04-06
**Status:** Approved

---

## Problem

Earnings announcements cause unpredictable ±10–20% price swings. The bot currently has no concept of the earnings calendar, meaning a technically strong BUY signal the day before earnings can result in a large loss. This is a pure risk management gap.

---

## Approach

Option A — standalone `EarningsCalendar` module, instantiated in `TradingEngine` and injected into `RiskManager.validate()` and `ClaudeStrategy.generate_signals()` as an explicit argument. Neither module fetches data itself; the engine orchestrates.

---

## Architecture

### Files changed

| File | Change |
|------|--------|
| `src/data/earnings_calendar.py` | **New** — `EarningsCalendar` class |
| `src/bot/risk_manager.py` | Add earnings window check in `validate()` |
| `src/bot/strategy.py` | Inject per-ticker warnings in `_build_market_context()` |
| `src/bot/engine.py` | Instantiate `EarningsCalendar`, pass to risk/strategy |
| `src/config/settings.py` | Add 3 new env vars |

### New dataclass

```python
@dataclass
class EarningsInfo:
    ticker: str
    earnings_date: date | None
    days_until: int | None        # None if earnings_date is None
    in_window: bool
    source: Literal["yfinance", "finnhub", "unavailable"]
```

### EarningsCalendar class

```python
class EarningsCalendar:
    def get_next_earnings(ticker: str) -> date | None
    def is_earnings_window(ticker: str, days_before: int = 2, days_after: int = 1) -> bool
    def get_earnings_info(tickers: list[str]) -> dict[str, EarningsInfo]
```

---

## Data Sources

1. **yfinance** (`ticker.calendar`) — primary, no API key, already a dependency
2. **Finnhub** (`/calendar/earnings`) — fallback, free tier (60 req/min), requires `FINNHUB_API_KEY`

Fetch order per ticker:
1. Try yfinance — if returns a valid date, use it
2. On failure or missing data — try Finnhub (if `FINNHUB_API_KEY` is set)
3. If both fail — return `EarningsInfo(in_window=False, source="unavailable")`

---

## Data Flow

```
TradingEngine._cycle()
  │
  ├─ earnings.get_earnings_info(watchlist)   ← dict[ticker, EarningsInfo]
  │
  ├─ RiskManager.validate(signal, positions, cash, earnings_info)
  │    └─ if earnings_info[ticker].in_window and signal.direction != "CLOSE" → reject
  │
  └─ ClaudeStrategy.generate_signals(..., earnings_info)
       └─ _build_market_context injects per-ticker line:
            ⚠️  AAPL: earnings in 1 day (2026-04-07 after-market) — new positions blocked
            ✅  TSLA: next earnings 2026-07-20 — no restriction
```

**CLOSE signals always pass** — reducing risk during earnings is always permitted. Only new position opens (BUY/SELL) are blocked.

---

## Cache

- TTL: 24 hours per ticker (earnings dates don't change intraday)
- Storage: module-level dict in `earnings_calendar.py` — same pattern as `price_feed.py`
- Cache key: ticker string; cache value: `(EarningsInfo, fetched_at: datetime)`

---

## Configuration

Three new env vars added to `src/config/settings.py`:

```
EARNINGS_DAYS_BEFORE=2          # days before earnings to start blocking
EARNINGS_DAYS_AFTER=1           # days after earnings to stop blocking
BLOCK_NEW_POSITIONS_ON_EARNINGS=true   # master switch
FINNHUB_API_KEY=                # optional; enables Finnhub fallback
```

---

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| yfinance returns no earnings date | Try Finnhub fallback |
| Both sources fail | `in_window=False` — fail open, don't block trading due to data outage |
| `FINNHUB_API_KEY` not set | Skip Finnhub silently, yfinance only |
| `BLOCK_NEW_POSITIONS_ON_EARNINGS=false` | Warnings still injected into prompt; hard block disabled |
| Finnhub rate limit hit | Log warning, treat as unavailable |

---

## Testing

- `test_earnings_calendar.py` — unit tests with mocked yfinance/Finnhub responses:
  - `is_earnings_window()` returns True when earnings is tomorrow
  - `is_earnings_window()` returns False when earnings is 10 days away
  - Falls back to Finnhub when yfinance returns no date
  - Returns `in_window=False` when both sources fail
- `test_risk_manager.py` — extend existing tests:
  - BUY signal rejected during earnings window
  - CLOSE signal approved during earnings window
- `test_strategy.py` — extend existing tests:
  - Prompt includes `⚠️` warning line when `in_window=True`
  - Prompt includes `✅` line when no earnings restriction

---

## Acceptance Criteria

- [ ] `EarningsCalendar` class in `src/data/earnings_calendar.py`
- [ ] `get_next_earnings(ticker) -> date | None`
- [ ] `is_earnings_window(ticker, days_before, days_after) -> bool`
- [ ] `RiskManager.validate()` rejects new position signals during earnings window
- [ ] Claude prompt includes earnings date warning per ticker
- [ ] `EARNINGS_DAYS_BEFORE`, `EARNINGS_DAYS_AFTER`, `BLOCK_NEW_POSITIONS_ON_EARNINGS` configurable via `.env`
- [ ] 24-hour cache
- [ ] No new positions opened during blackout; existing positions can still be closed
- [ ] Unit tests covering blackout logic
