# Signal Outcome Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Track trade outcomes (TP_HIT / SL_HIT / MANUAL_CLOSE) in memory and inject a rolling performance summary into every Claude prompt for self-calibration.

**Architecture:** Add a `TradeOutcome` Pydantic model and a separate `_outcome_log` list in `TradingEngine`. On signal execution, append an OPEN outcome. On close (auto or manual), find the last OPEN outcome for that ticker and update it with the result + pnl_pct. A performance summary is computed from the last 20 closed outcomes and injected into the Claude prompt when ≥5 closed trades exist. A new `/api/performance` endpoint exposes the full outcome log.

**Tech Stack:** Python 3.14, Pydantic v2, FastAPI, pytest, pytest-asyncio

---

## File Map

| File | Change |
|---|---|
| `src/api/models.py` | Add `TradeOutcome` Pydantic model |
| `src/bot/engine.py` | Add `_outcome_log`, `outcome_log` property, `_update_outcome()` helper; update `_execute_signal`, `_manage_exits`, `close_position`, `close_all_positions`, `_cycle` |
| `src/bot/strategy.py` | Add `_build_performance_summary()` helper; update `_build_market_context()` and `generate_signals()` |
| `src/dashboard/app.py` | Add `GET /api/performance` endpoint |
| `tests/test_models.py` | Add `TestTradeOutcome` class |
| `tests/test_engine_outcomes.py` | New file — outcome log lifecycle tests |
| `tests/test_strategy.py` | Add `TestPerformanceSummaryInjection` class |

---

## Task 1: TradeOutcome model

**Files:**
- Modify: `src/api/models.py`
- Modify: `tests/test_models.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_models.py` — update the import line at the top to include `TradeOutcome`:

```python
from src.api.models import (
    Position, TradeSignal, CashInfo, Order, Instrument,
    MarketOrderRequest, LimitOrderRequest, StopOrderRequest, BotStatus,
    TradeOutcome,
)
```

Then add at the bottom of the file:

```python
class TestTradeOutcome:
    def test_defaults(self):
        outcome = TradeOutcome(
            ticker="NVDA", action="BUY", direction="LONG",
            confidence=0.8, opened_at=datetime(2026, 4, 6, 10, 0, 0),
        )
        assert outcome.outcome == "OPEN"
        assert outcome.pnl_pct is None
        assert outcome.closed_at is None

    def test_closed_outcome(self):
        now = datetime(2026, 4, 6, 12, 0, 0)
        outcome = TradeOutcome(
            ticker="AAPL", action="SELL", direction="SHORT",
            confidence=0.72, opened_at=datetime(2026, 4, 5, 10, 0, 0),
            outcome="SL_HIT", pnl_pct=-2.0, closed_at=now,
        )
        assert outcome.outcome == "SL_HIT"
        assert outcome.pnl_pct == -2.0
        assert outcome.closed_at == now

    def test_tp_hit_outcome(self):
        outcome = TradeOutcome(
            ticker="TSLA", action="BUY", direction="LONG",
            confidence=0.9, opened_at=datetime(2026, 4, 1, 9, 30, 0),
            outcome="TP_HIT", pnl_pct=4.1,
            closed_at=datetime(2026, 4, 3, 14, 0, 0),
        )
        assert outcome.outcome == "TP_HIT"
        assert outcome.pnl_pct == pytest.approx(4.1)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_models.py::TestTradeOutcome -v
```

Expected: `ImportError: cannot import name 'TradeOutcome'`

- [ ] **Step 3: Add TradeOutcome to `src/api/models.py`**

Add after the `BotStatus` class at the end of the file:

```python
class TradeOutcome(BaseModel):
    ticker: str
    action: str                    # "BUY" or "SELL"
    direction: str                 # "LONG" or "SHORT"
    confidence: float
    outcome: Literal["TP_HIT", "SL_HIT", "MANUAL_CLOSE", "OPEN"] = "OPEN"
    pnl_pct: float | None = None
    opened_at: datetime
    closed_at: datetime | None = None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/test_models.py::TestTradeOutcome -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/api/models.py tests/test_models.py
git commit -m "feat: add TradeOutcome Pydantic model"
```

---

## Task 2: Engine outcome log — init, property, open on execute

**Files:**
- Modify: `src/bot/engine.py`
- Create: `tests/test_engine_outcomes.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_engine_outcomes.py`:

```python
"""Tests for TradingEngine outcome log — open/close lifecycle."""
import pytest
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock
from src.bot.engine import TradingEngine
from src.api.models import CashInfo, Position, Order, TradeSignal, TradeOutcome


def make_cash(**kwargs) -> CashInfo:
    defaults = dict(free=10_000.0, total=20_000.0, ppl=500.0,
                    result=500.0, invested=19_500.0, pieCash=0.0)
    defaults.update(kwargs)
    return CashInfo(**defaults)


def make_position(**kwargs) -> Position:
    defaults = dict(ticker="NVDA_US_EQ", quantity=10.0,
                    averagePrice=100.0, currentPrice=104.0, ppl=40.0)
    defaults.update(kwargs)
    return Position(**defaults)


def make_order(**kwargs) -> Order:
    defaults = dict(id=1, ticker="NVDA_US_EQ", orderedQuantity=10.0)
    defaults.update(kwargs)
    return Order(**defaults)


def make_signal(**kwargs) -> TradeSignal:
    defaults = dict(ticker="NVDA", action="BUY", direction="LONG",
                    confidence=0.8, reasoning="test")
    defaults.update(kwargs)
    return TradeSignal(**defaults)


class TestOutcomeLogInit:
    def test_outcome_log_starts_empty(self):
        engine = TradingEngine()
        assert engine._outcome_log == []

    def test_outcome_log_property_returns_last_200(self):
        engine = TradingEngine()
        now = datetime.now(UTC)
        for i in range(250):
            engine._outcome_log.append(TradeOutcome(
                ticker="AAPL", action="BUY", direction="LONG",
                confidence=0.8, opened_at=now,
            ))
        assert len(engine.outcome_log) == 200


class TestExecuteSignalCreatesOpenOutcome:
    @pytest.mark.asyncio
    async def test_buy_signal_creates_open_outcome(self):
        engine = TradingEngine()
        engine._ticker_map["NVDA"] = "NVDA_US_EQ"
        signal = make_signal(ticker="NVDA", action="BUY", direction="LONG", confidence=0.8)
        mock_client = MagicMock()
        mock_client.place_market_order = AsyncMock(return_value=make_order())

        await engine._execute_signal(mock_client, signal, make_cash(), [])

        assert len(engine._outcome_log) == 1
        o = engine._outcome_log[0]
        assert o.ticker == "NVDA"
        assert o.action == "BUY"
        assert o.direction == "LONG"
        assert o.confidence == 0.8
        assert o.outcome == "OPEN"
        assert o.pnl_pct is None
        assert o.closed_at is None

    @pytest.mark.asyncio
    async def test_failed_order_does_not_create_outcome(self):
        engine = TradingEngine()
        signal = make_signal()
        mock_client = MagicMock()
        mock_client.place_market_order = AsyncMock(side_effect=Exception("T212 error"))

        await engine._execute_signal(mock_client, signal, make_cash(), [])

        assert engine._outcome_log == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_engine_outcomes.py::TestOutcomeLogInit tests/test_engine_outcomes.py::TestExecuteSignalCreatesOpenOutcome -v
```

Expected: `AttributeError: 'TradingEngine' object has no attribute '_outcome_log'`

- [ ] **Step 3: Update `src/bot/engine.py`**

Update the import at the top of the file:

```python
from src.api.models import (
    MarketOrderRequest, LimitOrderRequest, StopOrderRequest,
    TradeSignal, BotStatus, Position, TradeOutcome,
)
```

In `__init__`, add after `self._pnl_history`:

```python
self._outcome_log: list[TradeOutcome] = []
```

Add `outcome_log` property after `pnl_history`:

```python
@property
def outcome_log(self) -> list[TradeOutcome]:
    return self._outcome_log[-200:]
```

In `_execute_signal`, inside the `if order:` block, after `self._log_trade({...})`, add:

```python
if signal.action in ("BUY", "SELL"):
    self._outcome_log.append(TradeOutcome(
        ticker=signal.ticker,
        action=signal.action,
        direction=signal.direction,
        confidence=signal.confidence,
        opened_at=datetime.now(UTC),
    ))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_engine_outcomes.py::TestOutcomeLogInit tests/test_engine_outcomes.py::TestExecuteSignalCreatesOpenOutcome -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/bot/engine.py tests/test_engine_outcomes.py
git commit -m "feat: add outcome_log to TradingEngine, record OPEN outcome on signal execute"
```

---

## Task 3: _update_outcome helper + _manage_exits closes outcomes

**Files:**
- Modify: `src/bot/engine.py`
- Modify: `tests/test_engine_outcomes.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_engine_outcomes.py`:

```python
class TestUpdateOutcome:
    def test_updates_most_recent_open_for_ticker(self):
        engine = TradingEngine()
        now = datetime.now(UTC)
        engine._outcome_log.append(TradeOutcome(
            ticker="NVDA", action="BUY", direction="LONG",
            confidence=0.8, opened_at=now,
        ))
        engine._update_outcome("NVDA", "TP_HIT", pnl_pct=4.0)
        o = engine._outcome_log[0]
        assert o.outcome == "TP_HIT"
        assert o.pnl_pct == 4.0
        assert o.closed_at is not None

    def test_ignores_already_closed_outcomes(self):
        engine = TradingEngine()
        now = datetime.now(UTC)
        engine._outcome_log.append(TradeOutcome(
            ticker="NVDA", action="BUY", direction="LONG",
            confidence=0.8, opened_at=now, outcome="TP_HIT",
            pnl_pct=4.0, closed_at=now,
        ))
        engine._outcome_log.append(TradeOutcome(
            ticker="NVDA", action="BUY", direction="LONG",
            confidence=0.75, opened_at=now,
        ))
        engine._update_outcome("NVDA", "SL_HIT", pnl_pct=-2.0)
        assert engine._outcome_log[0].outcome == "TP_HIT"   # unchanged
        assert engine._outcome_log[1].outcome == "SL_HIT"

    def test_no_open_outcome_for_ticker_is_noop(self):
        engine = TradingEngine()
        engine._update_outcome("NVDA", "SL_HIT", pnl_pct=-2.0)  # must not raise
        assert engine._outcome_log == []


class TestManageExitsUpdatesOutcomes:
    @pytest.mark.asyncio
    async def test_stop_loss_sets_sl_hit(self):
        from unittest.mock import patch
        engine = TradingEngine()
        now = datetime.now(UTC)
        engine._outcome_log.append(TradeOutcome(
            ticker="NVDA", action="BUY", direction="LONG",
            confidence=0.8, opened_at=now,
        ))
        pos = make_position(ticker="NVDA_US_EQ", quantity=10.0,
                            averagePrice=100.0, currentPrice=97.9, ppl=-21.0)
        mock_client = MagicMock()
        mock_client.place_market_order = AsyncMock(return_value=make_order())

        with patch.object(engine.risk, "check_stop_loss", return_value=True):
            with patch.object(engine.risk, "check_take_profit", return_value=False):
                await engine._manage_exits(mock_client, [pos])

        o = engine._outcome_log[0]
        assert o.outcome == "SL_HIT"
        assert o.ticker == "NVDA"
        assert o.pnl_pct == pytest.approx(-2.1, abs=0.1)
        assert o.closed_at is not None

    @pytest.mark.asyncio
    async def test_take_profit_sets_tp_hit(self):
        from unittest.mock import patch
        engine = TradingEngine()
        now = datetime.now(UTC)
        engine._outcome_log.append(TradeOutcome(
            ticker="NVDA", action="BUY", direction="LONG",
            confidence=0.8, opened_at=now,
        ))
        pos = make_position(ticker="NVDA_US_EQ", quantity=10.0,
                            averagePrice=100.0, currentPrice=104.0, ppl=40.0)
        mock_client = MagicMock()
        mock_client.place_market_order = AsyncMock(return_value=make_order())

        with patch.object(engine.risk, "check_stop_loss", return_value=False):
            with patch.object(engine.risk, "check_take_profit", return_value=True):
                await engine._manage_exits(mock_client, [pos])

        o = engine._outcome_log[0]
        assert o.outcome == "TP_HIT"
        assert o.pnl_pct == pytest.approx(4.0, abs=0.1)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_engine_outcomes.py::TestUpdateOutcome tests/test_engine_outcomes.py::TestManageExitsUpdatesOutcomes -v
```

Expected: `AttributeError: 'TradingEngine' object has no attribute '_update_outcome'`

- [ ] **Step 3: Add `_update_outcome` to `src/bot/engine.py` and update `_manage_exits`**

Add after `_log_trade`:

```python
def _update_outcome(self, ticker: str, outcome: str, pnl_pct: float | None):
    """Find the last OPEN outcome for ticker and close it."""
    for entry in reversed(self._outcome_log):
        if entry.ticker == ticker and entry.outcome == "OPEN":
            entry.outcome = outcome
            entry.pnl_pct = pnl_pct
            entry.closed_at = datetime.now(UTC)
            return
```

In `_manage_exits`, after `self._log_trade({...})`, add:

```python
short_ticker = pos.ticker.split("_")[0]
outcome_type = "TP_HIT" if exit_reason == "take-profit" else "SL_HIT"
self._update_outcome(short_ticker, outcome_type, pnl_pct=pos.pnl_pct)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_engine_outcomes.py::TestUpdateOutcome tests/test_engine_outcomes.py::TestManageExitsUpdatesOutcomes -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/bot/engine.py tests/test_engine_outcomes.py
git commit -m "feat: _update_outcome helper, _manage_exits closes outcomes with TP_HIT/SL_HIT"
```

---

## Task 4: close_position and close_all_positions update outcomes

**Files:**
- Modify: `src/bot/engine.py`
- Modify: `tests/test_engine_outcomes.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_engine_outcomes.py`:

```python
class TestClosePositionUpdatesOutcome:
    @pytest.mark.asyncio
    async def test_close_position_sets_manual_close(self):
        from unittest.mock import patch
        engine = TradingEngine()
        engine._ticker_map["NVDA"] = "NVDA_US_EQ"
        now = datetime.now(UTC)
        engine._outcome_log.append(TradeOutcome(
            ticker="NVDA", action="BUY", direction="LONG",
            confidence=0.8, opened_at=now,
        ))
        pos = make_position(ticker="NVDA_US_EQ", quantity=10.0,
                            averagePrice=100.0, currentPrice=103.0, ppl=30.0)
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get_positions = AsyncMock(return_value=[pos])
        mock_client.get_cash = AsyncMock(return_value=make_cash())
        mock_client.place_market_order = AsyncMock(return_value=make_order(id=99))

        with patch("src.bot.engine.Trading212Client", return_value=mock_client):
            await engine.close_position("NVDA")

        o = engine._outcome_log[0]
        assert o.outcome == "MANUAL_CLOSE"
        assert o.pnl_pct == pytest.approx(3.0, abs=0.1)
        assert o.closed_at is not None

    @pytest.mark.asyncio
    async def test_close_all_positions_sets_manual_close_for_each(self):
        from unittest.mock import patch
        engine = TradingEngine()
        now = datetime.now(UTC)
        engine._outcome_log.append(TradeOutcome(
            ticker="NVDA", action="BUY", direction="LONG",
            confidence=0.8, opened_at=now,
        ))
        engine._outcome_log.append(TradeOutcome(
            ticker="AAPL", action="BUY", direction="LONG",
            confidence=0.75, opened_at=now,
        ))
        pos1 = make_position(ticker="NVDA_US_EQ", quantity=10.0,
                             averagePrice=100.0, currentPrice=104.0, ppl=40.0)
        pos2 = make_position(ticker="AAPL_US_EQ", quantity=5.0,
                             averagePrice=150.0, currentPrice=153.0, ppl=15.0)
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get_positions = AsyncMock(return_value=[pos1, pos2])
        mock_client.get_cash = AsyncMock(return_value=make_cash())
        mock_client.place_market_order = AsyncMock(side_effect=[
            make_order(id=101), make_order(id=102),
        ])

        with patch("src.bot.engine.Trading212Client", return_value=mock_client):
            await engine.close_all_positions()

        nvda_o = next(o for o in engine._outcome_log if o.ticker == "NVDA")
        aapl_o = next(o for o in engine._outcome_log if o.ticker == "AAPL")
        assert nvda_o.outcome == "MANUAL_CLOSE"
        assert aapl_o.outcome == "MANUAL_CLOSE"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_engine_outcomes.py::TestClosePositionUpdatesOutcome -v
```

Expected: both tests FAIL — outcome remains `"OPEN"`

- [ ] **Step 3: Update `close_position` in `src/bot/engine.py`**

In `close_position`, after `self._log_trade({...})`:

```python
self._update_outcome(ticker, "MANUAL_CLOSE", pnl_pct=pos.pnl_pct)
```

In `close_all_positions`, inside the `try` block after `self._log_trade({...})`:

```python
self._update_outcome(short_ticker, "MANUAL_CLOSE", pnl_pct=pos.pnl_pct)
```

- [ ] **Step 4: Run all outcome tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_engine_outcomes.py -v
```

Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add src/bot/engine.py tests/test_engine_outcomes.py
git commit -m "feat: close_position and close_all_positions update outcomes to MANUAL_CLOSE"
```

---

## Task 5: Performance summary injection in strategy

**Files:**
- Modify: `src/bot/strategy.py`
- Modify: `tests/test_strategy.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_strategy.py`:

```python
class TestPerformanceSummaryInjection:
    def _make_outcomes(self, n_wins: int, n_losses: int) -> list:
        from src.api.models import TradeOutcome
        from datetime import datetime, UTC, timedelta
        outcomes = []
        base = datetime(2026, 4, 1, 10, 0, 0, tzinfo=UTC)
        for i in range(n_wins):
            outcomes.append(TradeOutcome(
                ticker="AAPL", action="BUY", direction="LONG", confidence=0.8,
                outcome="TP_HIT", pnl_pct=4.0,
                opened_at=base + timedelta(hours=i),
                closed_at=base + timedelta(hours=i, minutes=30),
            ))
        for i in range(n_losses):
            outcomes.append(TradeOutcome(
                ticker="TSLA", action="SELL", direction="SHORT", confidence=0.7,
                outcome="SL_HIT", pnl_pct=-2.0,
                opened_at=base + timedelta(hours=n_wins + i),
                closed_at=base + timedelta(hours=n_wins + i, minutes=30),
            ))
        return outcomes

    def test_no_section_when_fewer_than_5_closed(self):
        outcomes = self._make_outcomes(n_wins=2, n_losses=2)
        ctx = _build_market_context([], make_cash(), ["AAPL"], [], outcome_log=outcomes)
        assert "SIGNAL PERFORMANCE" not in ctx

    def test_section_present_when_5_or_more_closed(self):
        outcomes = self._make_outcomes(n_wins=3, n_losses=3)
        ctx = _build_market_context([], make_cash(), ["AAPL"], [], outcome_log=outcomes)
        assert "=== YOUR RECENT SIGNAL PERFORMANCE" in ctx
        assert "win rate" in ctx.lower()

    def test_win_rate_computed_correctly(self):
        outcomes = self._make_outcomes(n_wins=6, n_losses=4)
        ctx = _build_market_context([], make_cash(), ["AAPL"], [], outcome_log=outcomes)
        assert "60%" in ctx

    def test_recent_losses_listed(self):
        outcomes = self._make_outcomes(n_wins=3, n_losses=5)
        ctx = _build_market_context([], make_cash(), ["AAPL", "TSLA"], [], outcome_log=outcomes)
        assert "SL_HIT" in ctx
        assert "TSLA" in ctx

    def test_no_section_when_outcome_log_is_none(self):
        ctx = _build_market_context([], make_cash(), ["AAPL"], [], outcome_log=None)
        assert "SIGNAL PERFORMANCE" not in ctx

    def test_open_outcomes_excluded_from_win_loss_count(self):
        from src.api.models import TradeOutcome
        from datetime import datetime, UTC
        now = datetime(2026, 4, 1, 10, 0, 0, tzinfo=UTC)
        outcomes = self._make_outcomes(n_wins=5, n_losses=0)
        for _ in range(3):
            outcomes.append(TradeOutcome(
                ticker="NVDA", action="BUY", direction="LONG",
                confidence=0.8, opened_at=now,
            ))
        ctx = _build_market_context([], make_cash(), ["AAPL"], [], outcome_log=outcomes)
        assert "5 wins" in ctx
        assert "0 losses" in ctx
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_strategy.py::TestPerformanceSummaryInjection -v
```

Expected: `TypeError: _build_market_context() got an unexpected keyword argument 'outcome_log'`

- [ ] **Step 3: Add `_build_performance_summary` to `src/bot/strategy.py`**

Add at module level, before `_build_market_context`:

```python
def _build_performance_summary(outcome_log: list) -> str:
    """Compute a performance summary string for the Claude prompt.

    Returns an empty string if fewer than 5 closed trades exist.
    """
    closed = [o for o in outcome_log if o.outcome != "OPEN"]
    if len(closed) < 5:
        return ""

    open_count = sum(1 for o in outcome_log if o.outcome == "OPEN")
    recent = closed[-20:]
    wins = [o for o in recent if o.outcome == "TP_HIT"]
    losses = [o for o in recent if o.outcome != "TP_HIT"]
    win_rate = len(wins) / len(recent) * 100

    buy_recent = [o for o in recent if o.action == "BUY"]
    sell_recent = [o for o in recent if o.action == "SELL"]
    buy_wins = sum(1 for o in buy_recent if o.outcome == "TP_HIT")
    sell_wins = sum(1 for o in sell_recent if o.outcome == "TP_HIT")

    avg_win = (sum(o.pnl_pct for o in wins if o.pnl_pct is not None) / len(wins)) if wins else 0.0
    avg_loss = (sum(o.pnl_pct for o in losses if o.pnl_pct is not None) / len(losses)) if losses else 0.0
    expectancy = (win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss)

    lines = [
        f"=== YOUR RECENT SIGNAL PERFORMANCE (last {len(recent)} trades) ===",
        f"  Overall: {len(wins)} wins / {len(losses)} losses / {open_count} open  (win rate {win_rate:.0f}%)",
    ]
    if buy_recent:
        buy_label = "well calibrated" if buy_wins / len(buy_recent) >= 0.5 else "consider raising confidence threshold"
        lines.append(
            f"  BUY signals:  {buy_wins}W / {len(buy_recent) - buy_wins}L"
            f"  ({buy_wins / len(buy_recent) * 100:.0f}% — {buy_label})"
        )
    if sell_recent:
        sell_label = "well calibrated" if sell_wins / len(sell_recent) >= 0.5 else "consider raising confidence threshold for shorts"
        lines.append(
            f"  SELL signals: {sell_wins}W / {len(sell_recent) - sell_wins}L"
            f"  ({sell_wins / len(sell_recent) * 100:.0f}% — {sell_label})"
        )
    lines.append(
        f"  Avg winner: +{avg_win:.1f}%  |  Avg loser: {avg_loss:.1f}%  |  Expectancy: {expectancy:+.1f}%/trade"
    )

    recent_losses = [o for o in reversed(closed) if o.outcome != "TP_HIT"][:3]
    if recent_losses:
        lines.append("")
        lines.append("  Recent losses:")
        now = datetime.now(UTC)
        for o in recent_losses:
            age = ""
            if o.closed_at:
                closed_at = o.closed_at if o.closed_at.tzinfo else o.closed_at.replace(tzinfo=UTC)
                days = (now - closed_at).days
                age = f" — {days} day{'s' if days != 1 else ''} ago"
            pnl = f"{o.pnl_pct:.1f}%" if o.pnl_pct is not None else "n/a"
            lines.append(
                f"    {o.ticker} {o.direction} (conf={o.confidence:.2f}) → {o.outcome} {pnl}{age}"
            )

    return "\n".join(lines)
```

- [ ] **Step 4: Update `_build_market_context` signature in `src/bot/strategy.py`**

Replace the function signature:

```python
def _build_market_context(
    positions: list[Position],
    cash: CashInfo,
    watchlist: list[str],
    instruments: list[Instrument],
    price_data: dict | None = None,
    earnings_info: dict[str, "EarningsInfo"] | None = None,
    news_data: dict[str, list["NewsItem"]] | None = None,
    outcome_log: list | None = None,
) -> str:
```

Add performance section computation inside the function body, after the `news_section` block and before the `context = f"""...` assignment:

```python
    perf_section = ""
    if outcome_log:
        summary = _build_performance_summary(outcome_log)
        if summary:
            perf_section = f"\n{summary}\n"
```

Then insert `{perf_section}` in the context f-string between `{news_section}` and `=== WATCHLIST ===`:

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
{earnings_section}{news_section}{perf_section}
=== WATCHLIST ===
{json.dumps({t: instrument_info.get(t, t) for t in watchlist}, indent=2)}

=== TASK ===
Analyse the portfolio and market conditions using the price feed data.
Generate trading signals for up to 5 tickers.
Focus on tickers where there is a clear directional view.
Return ONLY a JSON array of TradeSignal objects.
"""
```

- [ ] **Step 5: Update `generate_signals` signature and call in `src/bot/strategy.py`**

Replace the `generate_signals` signature:

```python
def generate_signals(
    self,
    positions: list[Position],
    cash: CashInfo,
    watchlist: list[str],
    instruments: list[Instrument],
    earnings_info: dict[str, "EarningsInfo"] | None = None,
    news_data: dict[str, list["NewsItem"]] | None = None,
    outcome_log: list | None = None,
) -> list[TradeSignal]:
```

Update the `_build_market_context` call inside it:

```python
user_prompt = _build_market_context(
    positions, cash, watchlist, instruments, price_data, earnings_info, news_data, outcome_log
)
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_strategy.py::TestPerformanceSummaryInjection -v
```

Expected: 6 passed

- [ ] **Step 7: Update `_cycle` in `src/bot/engine.py` to pass `outcome_log`**

In `_cycle`, update the `generate_signals` call:

```python
signals = self.strategy.generate_signals(
    positions, cash, settings.WATCHLIST, instruments, earnings_info, news_data,
    outcome_log=self.outcome_log,
)
```

- [ ] **Step 8: Run full test suite**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all pass

- [ ] **Step 9: Commit**

```bash
git add src/bot/strategy.py src/bot/engine.py tests/test_strategy.py
git commit -m "feat: inject signal performance summary into Claude prompt"
```

---

## Task 6: GET /api/performance endpoint

**Files:**
- Modify: `src/dashboard/app.py`

- [ ] **Step 1: Add the endpoint**

In `src/dashboard/app.py`, after the `get_pnl_history` endpoint:

```python
@app.get("/api/performance", tags=["Bot"])
async def get_performance():
    """Full signal outcome history (in-memory, cleared on restart)."""
    return [o.model_dump() for o in engine._outcome_log]
```

- [ ] **Step 2: Run full test suite**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all pass

- [ ] **Step 3: Verify manually**

```bash
.venv/bin/python main.py
```

In a separate terminal:

```bash
curl -s http://localhost:4000/api/performance
```

Expected: `[]`

- [ ] **Step 4: Commit**

```bash
git add src/dashboard/app.py
git commit -m "feat: add GET /api/performance endpoint"
```
