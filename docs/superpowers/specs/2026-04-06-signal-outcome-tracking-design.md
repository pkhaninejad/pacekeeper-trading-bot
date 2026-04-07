# Signal Outcome Tracking — Design Spec

**Issue:** [#38](https://github.com/pkhaninejad/Claude-trade-bot/issues/38)
**Date:** 2026-04-06

## Overview

Claude generates trade signals but never learns which ones worked. This feature records the outcome of each signal (TP_HIT, SL_HIT, MANUAL_CLOSE) and injects a rolling performance summary into every Claude prompt, creating a lightweight self-calibration loop.

## Data Model

Add `TradeOutcome` Pydantic model to `src/api/models.py`:

```python
class TradeOutcome(BaseModel):
    ticker: str
    action: str                    # "BUY" or "SELL"
    direction: str                 # "LONG" or "SHORT"
    confidence: float
    outcome: Literal["TP_HIT", "SL_HIT", "MANUAL_CLOSE", "OPEN"] = "OPEN"
    pnl_pct: float | None = None   # filled at close from Position.pnl_pct
    opened_at: datetime
    closed_at: datetime | None = None
```

No raw entry/exit prices — `pnl_pct` from `Position.pnl_pct` at close time is sufficient for the feedback loop.

## Engine Changes (`src/bot/engine.py`)

- **`__init__`**: add `self._outcome_log: list[TradeOutcome] = []`
- **`outcome_log` property**: expose last 200 outcomes (mirrors `trade_log`)
- **`_execute_signal()`**: after successful order, append `TradeOutcome(outcome="OPEN", ...)`
- **`_manage_exits()`**: after closing a position, find last OPEN outcome for that ticker; set `outcome="TP_HIT"` or `"SL_HIT"`, `pnl_pct=pos.pnl_pct`, `closed_at=now`
- **`close_position()`**: same — set `outcome="MANUAL_CLOSE"`, `pnl_pct`, `closed_at`
- **`close_all_positions()`**: same for each position closed
- **`_cycle()`**: pass `self.outcome_log` into `strategy.generate_signals()`

The existing `_trade_log` and all existing endpoints are unchanged.

## Strategy Changes (`src/bot/strategy.py`)

- **`_build_market_context()`**: add `outcome_log: list[TradeOutcome] | None = None` parameter
- When ≥5 closed outcomes exist, inject a `=== YOUR RECENT SIGNAL PERFORMANCE ===` section before `=== TASK ===`
- Stats computed from last 20 closed outcomes (TP_HIT + SL_HIT + MANUAL_CLOSE); OPEN excluded from win/loss but counted separately
- Summary includes: overall win rate, BUY vs SELL breakdown, avg winner %, avg loser %, expectancy %, last 3 losses by name
- **`generate_signals()`**: accept and forward `outcome_log` to `_build_market_context()`

### Example injected section

```
=== YOUR RECENT SIGNAL PERFORMANCE (last 20 trades) ===
  Overall: 11 wins / 7 losses / 2 open  (win rate 61%)
  BUY signals:  9W / 4L  (69% — well calibrated)
  SELL signals: 2W / 3L  (40% — consider raising confidence threshold for shorts)
  Avg winner: +3.8%  |  Avg loser: -2.0%  |  Expectancy: +1.5%/trade

  Recent losses:
    TSLA SHORT (conf=0.72) → SL_HIT -2.0% — 2 days ago
    AMD  LONG  (conf=0.65) → SL_HIT -2.1% — 3 days ago
```

## Dashboard Changes (`src/dashboard/app.py`)

Add one new endpoint:

```
GET /api/performance
```

Returns full `_outcome_log` as a JSON list of serialized `TradeOutcome` objects. No cap on results. No changes to existing endpoints.

## Files to Modify

| File | Change |
|---|---|
| `src/api/models.py` | Add `TradeOutcome` model |
| `src/bot/engine.py` | Add `_outcome_log`, update open/close paths, expose property, pass to strategy |
| `src/bot/strategy.py` | Inject performance section in `_build_market_context()`, accept `outcome_log` param |
| `src/dashboard/app.py` | Add `GET /api/performance` endpoint |

## Out of Scope

- Persisting outcomes across restarts (in-memory only, cleared on restart)
- Dashboard UI for the performance endpoint (JSON only)
- Replacing `_trade_log` with `TradeOutcome` (separate concern, future PR)
