# Dashboard Bugs Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix four dashboard bugs — pause bot, close position, trade history, and PnL history — by moving close logic into `TradingEngine` and simplifying dashboard endpoints to thin delegates.

**Architecture:** `toggle()` is simplified to only flip `status.enabled` (the cycle guard already handles pause). Two new engine methods — `close_position()` and `close_all_positions()` — handle T212 ticker resolution, order placement, trade logging, and PnL snapshotting. Dashboard endpoints delegate entirely.

**Tech Stack:** Python 3.14, FastAPI, httpx, asyncio, unittest.mock (AsyncMock for async client mocking).

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/bot/engine.py` | **Modify** | Fix `toggle()`, add `close_position()`, add `close_all_positions()` |
| `src/dashboard/app.py` | **Modify** | Replace close endpoint bodies with engine delegation |
| `tests/test_engine_close.py` | **Create** | 4 unit tests with mocked async Trading212Client |

---

## Task 1: Fix the pause bug in `toggle()`

**Files:**
- Modify: `src/bot/engine.py:86-90`
- Create: `tests/test_engine_close.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_engine_close.py`:

```python
"""Tests for TradingEngine close/toggle methods."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.bot.engine import TradingEngine
from src.api.models import CashInfo, Position, Order


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_cash(**kwargs) -> CashInfo:
    defaults = dict(free=10_000.0, total=20_000.0, ppl=500.0,
                    result=500.0, invested=19_500.0, pieCash=0.0)
    defaults.update(kwargs)
    return CashInfo(**defaults)


def make_position(**kwargs) -> Position:
    defaults = dict(ticker="NVDA_US_EQ", quantity=10.0,
                    averagePrice=100.0, currentPrice=110.0, ppl=100.0)
    defaults.update(kwargs)
    return Position(**defaults)


def make_order(**kwargs) -> Order:
    defaults = dict(id=42, ticker="NVDA_US_EQ", orderedQuantity=10.0)
    defaults.update(kwargs)
    return Order(**defaults)


def make_mock_client(positions=None, cash=None, order=None):
    """Return a mock Trading212Client usable as async context manager."""
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.get_positions = AsyncMock(return_value=positions or [])
    client.get_cash = AsyncMock(return_value=cash or make_cash())
    client.place_market_order = AsyncMock(return_value=order or make_order())
    return client


# ---------------------------------------------------------------------------
# toggle()
# ---------------------------------------------------------------------------

class TestToggle:
    def test_toggle_disable_does_not_set_running_false(self):
        """Pausing the bot must NOT kill the start() loop (_running stays True)."""
        engine = TradingEngine()
        engine._running = True

        engine.toggle()  # disable

        assert engine.status.enabled is False
        assert engine._running is True   # loop must still be alive

    def test_toggle_reenable_works(self):
        """Re-enabling after pause correctly sets enabled=True."""
        engine = TradingEngine()
        engine._running = True

        engine.toggle()   # disable
        engine.toggle()   # re-enable

        assert engine.status.enabled is True
        assert engine._running is True
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
.venv/bin/python -m pytest tests/test_engine_close.py::TestToggle -v
```

Expected: `FAILED` — `assert engine._running is True` fails because current `toggle()` calls `stop()` which sets `_running = False`.

- [ ] **Step 3: Fix `toggle()` in `src/bot/engine.py`**

Current code (lines 86–90):
```python
def toggle(self) -> bool:
    self.status.enabled = not self.status.enabled
    if not self.status.enabled:
        self.stop()
    return self.status.enabled
```

Replace with:
```python
def toggle(self) -> bool:
    self.status.enabled = not self.status.enabled
    return self.status.enabled
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
.venv/bin/python -m pytest tests/test_engine_close.py::TestToggle -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add src/bot/engine.py tests/test_engine_close.py
git commit -m "fix: toggle() no longer kills start() loop — pause now works correctly"
```

---

## Task 2: Add `engine.close_position()` with trade log + PnL snapshot

**Files:**
- Modify: `src/bot/engine.py`
- Modify: `tests/test_engine_close.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_engine_close.py`:

```python
# ---------------------------------------------------------------------------
# close_position()
# ---------------------------------------------------------------------------

class TestClosePosition:
    @pytest.mark.asyncio
    async def test_close_position_logs_trade_and_pnl(self):
        """Successful close: trade logged, PnL snapshot appended."""
        pos = make_position(ticker="NVDA_US_EQ", quantity=10.0)
        cash = make_cash(ppl=600.0, total=20_100.0, invested=19_500.0)
        order = make_order(id=99, ticker="NVDA_US_EQ", orderedQuantity=-10.0)
        mock_client = make_mock_client(positions=[pos], cash=cash, order=order)

        engine = TradingEngine()
        engine._ticker_map["NVDA"] = "NVDA_US_EQ"

        with patch("src.bot.engine.Trading212Client", return_value=mock_client):
            result = await engine.close_position("NVDA")

        # Trade logged
        assert len(engine._trade_log) == 1
        entry = engine._trade_log[0]
        assert entry["action"] == "MANUAL_CLOSE"
        assert entry["ticker"] == "NVDA"
        assert entry["order_id"] == 99

        # PnL snapshot appended
        assert len(engine._pnl_history) == 1
        snap = engine._pnl_history[0]
        assert snap["ppl"] == 600.0
        assert snap["total"] == 20_100.0

        # Return value
        assert result["order_id"] == 99

    @pytest.mark.asyncio
    async def test_close_position_unknown_ticker_raises(self):
        """Ticker with no open position raises ValueError."""
        mock_client = make_mock_client(positions=[])
        engine = TradingEngine()

        with patch("src.bot.engine.Trading212Client", return_value=mock_client):
            with pytest.raises(ValueError, match="No open position for NVDA"):
                await engine.close_position("NVDA")

        # Nothing logged
        assert engine._trade_log == []
        assert engine._pnl_history == []
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
.venv/bin/python -m pytest tests/test_engine_close.py::TestClosePosition -v
```

Expected: `ERROR AttributeError: 'TradingEngine' object has no attribute 'close_position'`

- [ ] **Step 3: Add `close_position()` to `src/bot/engine.py`**

Add this method to `TradingEngine` after the `pnl_history` property (around line 102), before the `# Core cycle` comment:

```python
async def close_position(self, ticker: str) -> dict:
    """Close a single open position by short ticker (e.g. 'NVDA').

    Resolves ticker to T212 format, places a market order, logs the trade,
    and appends a PnL snapshot. Raises ValueError if no position found.
    """
    async with Trading212Client() as client:
        positions = await client.get_positions()
        pos = next(
            (p for p in positions if p.ticker.split("_")[0] == ticker or p.ticker == ticker),
            None,
        )
        if pos is None:
            raise ValueError(f"No open position for {ticker}")

        t212_ticker = self._ticker_map.get(ticker, pos.ticker)
        quantity = -pos.quantity
        order = await client.place_market_order(
            MarketOrderRequest(ticker=t212_ticker, quantity=quantity)
        )
        self._log_trade({
            "action": "MANUAL_CLOSE",
            "ticker": ticker,
            "quantity": quantity,
            "order_id": order.id,
            "timestamp": datetime.utcnow().isoformat(),
        })
        cash = await client.get_cash()
        self._pnl_history.append({
            "t": datetime.utcnow().isoformat(),
            "ppl": round(cash.ppl, 2),
            "total": round(cash.total, 2),
            "invested": round(cash.invested, 2),
        })
        return {"message": f"Closed {ticker}", "order_id": order.id}
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
.venv/bin/python -m pytest tests/test_engine_close.py::TestClosePosition -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add src/bot/engine.py tests/test_engine_close.py
git commit -m "feat: add TradingEngine.close_position() with trade log and PnL snapshot"
```

---

## Task 3: Add `engine.close_all_positions()` with trade log + PnL snapshot

**Files:**
- Modify: `src/bot/engine.py`
- Modify: `tests/test_engine_close.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_engine_close.py`:

```python
# ---------------------------------------------------------------------------
# close_all_positions()
# ---------------------------------------------------------------------------

class TestCloseAllPositions:
    @pytest.mark.asyncio
    async def test_close_all_logs_trades_and_pnl(self):
        """Two open positions: both logged, one PnL snapshot at the end."""
        pos1 = make_position(ticker="NVDA_US_EQ", quantity=10.0)
        pos2 = make_position(ticker="AAPL_US_EQ", quantity=5.0)
        cash = make_cash(ppl=800.0, total=20_800.0, invested=20_000.0)

        order1 = make_order(id=101, ticker="NVDA_US_EQ", orderedQuantity=-10.0)
        order2 = make_order(id=102, ticker="AAPL_US_EQ", orderedQuantity=-5.0)

        mock_client = make_mock_client(
            positions=[pos1, pos2],
            cash=cash,
        )
        # Return different orders for each call
        mock_client.place_market_order = AsyncMock(side_effect=[order1, order2])

        engine = TradingEngine()

        with patch("src.bot.engine.Trading212Client", return_value=mock_client):
            results = await engine.close_all_positions()

        # Both trades logged
        assert len(engine._trade_log) == 2
        assert engine._trade_log[0]["action"] == "MANUAL_CLOSE"
        assert engine._trade_log[1]["action"] == "MANUAL_CLOSE"

        # One PnL snapshot at the end
        assert len(engine._pnl_history) == 1
        assert engine._pnl_history[0]["ppl"] == 800.0

        # Result list
        assert len(results) == 2
        assert results[0]["status"] == "closed"
        assert results[1]["status"] == "closed"

    @pytest.mark.asyncio
    async def test_close_all_handles_partial_failure(self):
        """If one position fails to close, error is captured; others still close."""
        pos1 = make_position(ticker="NVDA_US_EQ", quantity=10.0)
        pos2 = make_position(ticker="AAPL_US_EQ", quantity=5.0)
        cash = make_cash()

        mock_client = make_mock_client(positions=[pos1, pos2], cash=cash)
        mock_client.place_market_order = AsyncMock(
            side_effect=[Exception("T212 error"), make_order(id=102)]
        )

        engine = TradingEngine()

        with patch("src.bot.engine.Trading212Client", return_value=mock_client):
            results = await engine.close_all_positions()

        assert results[0]["status"] == "error"
        assert results[1]["status"] == "closed"
        # Only successful close is logged
        assert len(engine._trade_log) == 1
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
.venv/bin/python -m pytest tests/test_engine_close.py::TestCloseAllPositions -v
```

Expected: `ERROR AttributeError: 'TradingEngine' object has no attribute 'close_all_positions'`

- [ ] **Step 3: Add `close_all_positions()` to `src/bot/engine.py`**

Add this method directly after `close_position()`:

```python
async def close_all_positions(self) -> list[dict]:
    """Close all open positions. Logs each successful close.
    Appends one PnL snapshot after all closes attempt.
    Per-position errors are captured and returned as error entries.
    """
    async with Trading212Client() as client:
        positions = await client.get_positions()
        results = []
        for pos in positions:
            short_ticker = pos.ticker.split("_")[0]
            try:
                quantity = -pos.quantity
                order = await client.place_market_order(
                    MarketOrderRequest(ticker=pos.ticker, quantity=quantity)
                )
                self._log_trade({
                    "action": "MANUAL_CLOSE",
                    "ticker": short_ticker,
                    "quantity": quantity,
                    "order_id": order.id,
                    "timestamp": datetime.utcnow().isoformat(),
                })
                results.append({"ticker": short_ticker, "order_id": order.id, "status": "closed"})
            except Exception as e:
                results.append({"ticker": short_ticker, "status": "error", "detail": str(e)})

        cash = await client.get_cash()
        self._pnl_history.append({
            "t": datetime.utcnow().isoformat(),
            "ppl": round(cash.ppl, 2),
            "total": round(cash.total, 2),
            "invested": round(cash.invested, 2),
        })
        return results
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
.venv/bin/python -m pytest tests/test_engine_close.py::TestCloseAllPositions -v
```

Expected: `2 passed`

- [ ] **Step 5: Run all engine close tests**

```bash
.venv/bin/python -m pytest tests/test_engine_close.py -v
```

Expected: `6 passed`

- [ ] **Step 6: Commit**

```bash
git add src/bot/engine.py tests/test_engine_close.py
git commit -m "feat: add TradingEngine.close_all_positions() with trade log and PnL snapshot"
```

---

## Task 4: Update dashboard endpoints to delegate to engine

**Files:**
- Modify: `src/dashboard/app.py:178-207`

- [ ] **Step 1: Replace `close_position` endpoint body**

In `src/dashboard/app.py`, replace the entire `close_position` function (lines 178–189):

```python
@app.post("/api/positions/{ticker}/close", tags=["Positions"])
async def close_position(ticker: str):
    """Close a specific position by ticker."""
    try:
        result = await engine.close_position(ticker)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    _cache.pop("positions", None)
    return result
```

- [ ] **Step 2: Replace `close_all_positions` endpoint body**

Replace the entire `close_all_positions` function (lines 192–207):

```python
@app.post("/api/positions/close-all", tags=["Positions"])
async def close_all_positions():
    """Close all open positions."""
    results = await engine.close_all_positions()
    _cache.pop("positions", None)
    return {"closed": results}
```

Also remove the now-unused import inside the old function bodies — `from src.api.models import MarketOrderRequest` was imported inline. Verify `MarketOrderRequest` is not imported anywhere else in `app.py`; if not, no action needed (it was already a local import inside those functions).

- [ ] **Step 3: Verify the app imports cleanly**

```bash
.venv/bin/python -c "from src.dashboard.app import app; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Run the full test suite**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all tests pass (at least 139 — 135 existing + 6 new in `test_engine_close.py`).

- [ ] **Step 5: Commit**

```bash
git add src/dashboard/app.py
git commit -m "fix: dashboard close endpoints delegate to engine (fixes ticker format, trade log, PnL)"
```

---

## Task 5: Create PR and close issue

- [ ] **Step 1: Push branch and create PR**

```bash
git checkout -b fix/dashboard-bugs-issue-48
git push -u origin fix/dashboard-bugs-issue-48
gh pr create \
  --title "fix: dashboard bugs — pause, close position, trade history, PnL (issue #48)" \
  --body "$(cat <<'EOF'
## Summary

- **Pause bot**: `toggle()` no longer calls `stop()` — only flips `status.enabled`. The existing `_cycle()` guard handles pause correctly; the loop stays alive and resumes immediately on re-enable.
- **Close position**: Moved into `engine.close_position()` which resolves short ticker → T212 format via `_ticker_map`, places the order, logs the trade, and snapshots P&L.
- **Close all**: Moved into `engine.close_all_positions()` — same pattern, captures per-position errors gracefully.
- **Trade history**: Both close methods call `_log_trade()` so manual closes appear in trade history.
- **PnL history**: Both close methods fetch fresh cash after closing and append a PnL snapshot.
- Dashboard endpoints are now thin delegates — no T212 calls, no state mutation.

Closes #48

## Test plan

- [ ] `pytest tests/test_engine_close.py -v` — 6 new tests pass
- [ ] `pytest tests/ -v` — full suite passes, no regressions
- [ ] Toggle bot off → on in dashboard — bot resumes trading on next cycle
- [ ] Close individual position from dashboard — appears in trade history, PnL updates
- [ ] Close all positions from dashboard — all appear in trade history, PnL updates

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 2: Close issue #48 with PR reference**

```bash
gh issue comment 48 --repo pkhaninejad/Claude-trade-bot \
  --body "Fixed in PR — all 4 bugs resolved. See PR for details."
```
