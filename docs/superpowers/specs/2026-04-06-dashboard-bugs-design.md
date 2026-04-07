# Dashboard Bugs Fix — Design Spec

**Issue:** [#48](https://github.com/pkhaninejad/Claude-trade-bot/issues/48)
**Date:** 2026-04-06
**Status:** Approved

---

## Overview

Four dashboard bugs reported in issue #48. All root causes are in `src/bot/engine.py` and `src/dashboard/app.py`. The fix centralises close logic inside `TradingEngine` so the engine owns all trade execution and state updates; the dashboard becomes a thin delegate.

---

## Bugs & Root Causes

### Bug 1 — Pause bot does not work
`toggle()` calls `stop()` which sets `_running = False`, permanently killing the `start()` loop. Re-enabling sets `status.enabled = True` but the loop is already dead — the bot never resumes.

**Root cause:** `toggle()` conflates "pause" with "stop".

### Bug 2 — Close position / Close all not working
`close_position(ticker)` in `app.py` receives the short ticker (e.g. `NVDA`) from the URL and passes it directly to `Trading212Client.get_position()` and `place_market_order()`, both of which require the T212 format (`NVDA_US_EQ`). Results in a 404.

**Root cause:** Dashboard endpoint does not resolve ticker format before calling T212.

### Bug 3 — Trade history not filled after manual close
`close_position` and `close_all_positions` in `app.py` place orders but never call `engine._log_trade()`.

**Root cause:** Trade logging is not called from dashboard close endpoints.

### Bug 4 — PnL session history resets after manual close
`_pnl_history` is only appended during full engine cycles. Manual closes do not trigger a PnL snapshot, so the chart appears stale or empty.

**Root cause:** PnL snapshot not taken after manual close.

---

## Architecture

Close logic moves into `TradingEngine`. Dashboard endpoints delegate entirely.

```
Dashboard /close endpoint
    └── engine.close_position(ticker)
            ├── resolve ticker via _ticker_map
            ├── Trading212Client.place_market_order()
            ├── _log_trade(action="MANUAL_CLOSE")
            └── fetch cash → append _pnl_history snapshot
```

---

## Engine Changes (`src/bot/engine.py`)

### Fix 1 — `toggle()`

Remove the `stop()` call. `_cycle()` already returns early when `status.enabled` is `False`; the loop keeps running and resumes immediately when re-enabled.

```python
def toggle(self) -> bool:
    self.status.enabled = not self.status.enabled
    return self.status.enabled
```

`stop()` remains unchanged for actual shutdown (called from the FastAPI lifespan context).

### Fix 2 — `close_position(ticker: str) -> dict`

```python
async def close_position(self, ticker: str) -> dict:
    """Close a single open position by short ticker (e.g. 'NVDA').

    Resolves to T212 format, places market order, logs trade, snapshots PnL.
    Raises ValueError if no open position found for ticker.
    """
```

Steps:
1. Open a `Trading212Client` context
2. Fetch current positions via `client.get_positions()`
3. Find position matching short ticker (match `pos.ticker.split("_")[0] == ticker` OR direct match)
4. If not found: raise `ValueError(f"No open position for {ticker}")`
5. Resolve T212 ticker via `self._ticker_map.get(ticker, pos.ticker)`
6. Place `MarketOrderRequest(ticker=t212_ticker, quantity=-pos.quantity)`
7. Call `self._log_trade({"action": "MANUAL_CLOSE", "ticker": ticker, "quantity": -pos.quantity, "order_id": order.id, "timestamp": ...})`
8. Fetch fresh cash via `client.get_cash()` and append PnL snapshot to `self._pnl_history`
9. Return `{"message": f"Closed {ticker}", "order_id": order.id}`

### Fix 3 — `close_all_positions() -> list[dict]`

```python
async def close_all_positions(self) -> list[dict]:
    """Close all open positions. Logs each trade. Snapshots PnL once at the end."""
```

Steps:
1. Open a `Trading212Client` context
2. Fetch current positions
3. For each position: place market order, call `_log_trade`, collect result dict
4. Catch per-position exceptions and append error entry (same shape as current behaviour)
5. After all closes: fetch fresh cash, append one PnL snapshot
6. Return list of result dicts

---

## Dashboard Changes (`src/dashboard/app.py`)

Both endpoints become thin delegates — no T212 calls, no state mutation:

```python
@app.post("/api/positions/{ticker}/close", tags=["Positions"])
async def close_position(ticker: str):
    try:
        result = await engine.close_position(ticker)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    _cache.pop("positions", None)
    return result

@app.post("/api/positions/close-all", tags=["Positions"])
async def close_all_positions():
    results = await engine.close_all_positions()
    _cache.pop("positions", None)
    return {"closed": results}
```

No other dashboard changes needed.

---

## Tests

Four new tests in `tests/test_engine_close.py`:

1. **`test_toggle_pause_does_not_kill_loop`** — call `toggle()` to disable then re-enable; assert `_running` stays `True`, `status.enabled` correctly flips both ways

2. **`test_close_position_logs_trade_and_pnl`** — mock `Trading212Client` (get_positions returns one NVDA position, get_cash returns cash, place_market_order succeeds); call `engine.close_position("NVDA")`; assert `_trade_log` has one entry with `action="MANUAL_CLOSE"` and `_pnl_history` has one new entry

3. **`test_close_position_unknown_ticker_raises`** — mock `get_positions` returns empty list; assert `close_position("NVDA")` raises `ValueError`

4. **`test_close_all_logs_trades`** — mock two open positions; call `engine.close_all_positions()`; assert `_trade_log` has two entries and returned list has two entries with `"closed"` status

---

## Files Changed

| File | Change |
|------|--------|
| `src/bot/engine.py` | Fix `toggle()`, add `close_position()`, add `close_all_positions()` |
| `src/dashboard/app.py` | Replace close endpoint bodies with engine delegation |
| `tests/test_engine_close.py` | New — 4 unit tests |

---

## Definition of Done

- [ ] Toggling bot off and on resumes trading on next cycle
- [ ] `/api/positions/{ticker}/close` successfully closes position and returns order ID
- [ ] `/api/positions/close-all` closes all positions
- [ ] Closed positions appear in trade history after manual close
- [ ] PnL chart updates after manual close
- [ ] All 4 new tests pass
- [ ] Full test suite passes
