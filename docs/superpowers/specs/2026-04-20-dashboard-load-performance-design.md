# Dashboard Load Performance Fix — Design Spec

**Date:** 2026-04-20
**Issue:** [#72 — dashboard takes too long to load / appears unresponsive on refresh](https://github.com/pkhaninejad/Claude-trade-bot/issues/72)
**Branch:** `fix/dashboard-load-performance`

## Problem

The `GET /` route blocks on two SQLite calls before returning HTML:
- `engine.paper_trader.store.get_stats()`
- `engine.paper_trader.store.get_recent_trades(limit=50)`

If the engine event loop is busy (mid-scan or waiting on LLM), these queue behind it and the browser hangs. Additionally, `new EventSource('/api/stream')` is opened immediately on script execution, before the DOM is ready, which can delay initial paint.

## Solution — Option 1: Minimal Fix

Remove all async I/O from `GET /`. Serve the dashboard from `engine.status` (already in-memory, updated after every cycle). Load trades and "if all win" asynchronously via JS after paint. Defer SSE connection to `DOMContentLoaded`.

## Architecture

### Data Flow

```
Browser requests GET /
  → FastAPI returns HTML immediately (no awaits, reads engine.status only)
  → Browser paints stat cards from Jinja-rendered values
  → DOMContentLoaded fires:
      → fetch /api/trades       → populate trades table
      → fetch /api/trades/open  → compute "if all win" value
      → new EventSource(...)    → open SSE for live updates
```

### Backend: `app.py`

`dashboard()` drops both `await` calls. Template context:

```python
{
    "status": engine.status,
    "interval_seconds": engine.settings.SCAN_INTERVAL_SECONDS,
}
```

`engine.status` (PMBotStatus) already carries:
- `bankroll`, `total_pnl`, `win_rate`, `open_trades`, `enabled`

These are updated at the end of every `_cycle()` call in `engine.py`.

### Frontend: `dashboard.html`

- Stat cards render from Jinja template values on first paint — no change to markup
- Trades `<tbody>` initially shows a single "Loading…" row
- "If All Win" card initially shows `—`
- After `DOMContentLoaded`:
  - `fetch('/api/trades')` → parse JSON → rebuild trades `<tbody>` rows
  - `fetch('/api/trades/open')` → compute `sum((1 - entry_price) * quantity)` → update "if all win" card
  - `new EventSource('/api/stream')` → open SSE (moved from top-level script)
- Countdown timer init (`fetch('/api/status')`) also moves inside `DOMContentLoaded`

### Error Handling

- If `/api/trades` fetch fails: table shows "Error loading trades"
- If `/api/trades/open` fetch fails: "If All Win" card stays `—`
- Page remains fully functional in both cases

## Acceptance Criteria

- [ ] Dashboard initial HTML renders in < 300ms (no I/O in route handler)
- [ ] SSE connection does not block page paint (deferred to DOMContentLoaded)
- [ ] Stats and trades load asynchronously after initial render

## Files Changed

- `prediction_bot/src/dashboard/app.py` — remove awaits from `dashboard()`
- `prediction_bot/src/dashboard/templates/dashboard.html` — async trade loading, deferred SSE

## Out of Scope

- CSS skeleton shimmer (Option 2)
- Caching trades list in engine memory (Option 3)
- New tests (route simplification, no new logic)
