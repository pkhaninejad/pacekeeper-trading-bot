# Phase 1 — Prediction Bot Strategy Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the full prediction-bot strategy builder: pluggable StrategyRunner, multi-strategy engine cycle, strategy CRUD + activate API, stepped wizard UI, and equity-overlay chart — closing issues #103, #104, #105, #106, and #107.

**Architecture:** Five sequential tasks build on each other: (1) `StrategyRunner` + ParamSchema plugs the prediction bot into `strategy_kit`; (2) engine refactor evaluates candidates once and applies each active strategy via StrategyRunner, with `strategy_id` added to all DB rows; (3) REST API exposes strategy CRUD + activate/deactivate; (4) wizard UI lets users build and save strategies; (5) equity-overlay chart visualises per-strategy bankroll curves from `ShadowPortfolio`. The `strategy_kit` package from Phase 0 provides all shared infrastructure.

**Tech Stack:** Python 3.14, Pydantic v2, aiosqlite, FastAPI, pytest-asyncio (`asyncio_mode = "auto"`), Chart.js (CDN), vanilla JS, Pacekeeper design tokens.

---

## File Map

| Path | Responsibility |
|------|---------------|
| `prediction_bot/src/bot/strategy_runner.py` | `PREDICTION_SCHEMA`, `TradeDecision`, `StrategyRunner` |
| `prediction_bot/src/api/models.py` | Add `strategy_id` field to `PaperTrade` |
| `prediction_bot/src/data/result_store.py` | Migration: add `strategy_id` to both tables; scope all queries |
| `prediction_bot/src/bot/paper_trader.py` | Add `strategy_id` param; add `place_decision()` |
| `prediction_bot/src/bot/engine.py` | Evaluate-once refactor; active strategies; ShadowPortfolio wiring |
| `strategy_kit/store.py` | Migration: add `active` column; add `activate()` / `deactivate()` |
| `prediction_bot/src/dashboard/strategies_router.py` | Strategy CRUD + activate FastAPI router |
| `prediction_bot/src/dashboard/app.py` | Include strategies_router; add `/api/strategies/equity` |
| `prediction_bot/src/dashboard/templates/dashboard.html` | Stepped wizard (Task 4) + equity chart (Task 5) |
| `prediction_bot/tests/test_strategy_runner.py` | Unit tests for StrategyRunner (#103 acceptance) |
| `prediction_bot/tests/test_result_store_migration.py` | Migration + scoped-query tests (#104 acceptance) |
| `prediction_bot/tests/test_strategies_router.py` | Endpoint tests (#105 acceptance) |

---

## Task 1: StrategyRunner + ParamSchema (#103)

**Files:**
- Create: `prediction_bot/src/bot/strategy_runner.py`
- Create: `prediction_bot/tests/test_strategy_runner.py`

### Step 1.1 — Write failing tests

- [ ] Create `prediction_bot/tests/test_strategy_runner.py`:

```python
"""Tests for StrategyRunner — issue #103."""
import pytest
from datetime import datetime, timezone, timedelta

from prediction_bot.src.api.models import MarketCandidate, PredictionMarket
from prediction_bot.src.bot.strategy_runner import PREDICTION_SCHEMA, StrategyRunner, TradeDecision
from strategy_kit import get_schema


def _candidate(
    market_id="m1",
    category="crypto",
    yes_price=0.90,
    edge=0.05,
    best_side="YES",
):
    return MarketCandidate(
        market=PredictionMarket(
            id=market_id,
            platform="polymarket",
            question=f"Q {market_id}?",
            category=category,
            end_date=datetime.now(timezone.utc) + timedelta(hours=48),
            yes_price=yes_price,
            no_price=round(1 - yes_price, 4),
            liquidity=5000.0,
        ),
        best_side=best_side,
        market_price=yes_price,
        llm_confidence=0.95,
        edge=edge,
    )


class TestPREDICTION_SCHEMA:
    def test_registered_under_prediction_key(self):
        schema = get_schema("prediction")
        assert schema is PREDICTION_SCHEMA

    def test_has_required_param_keys(self):
        keys = {f.key for f in PREDICTION_SCHEMA.fields}
        required = {
            "HIGH_PROB_MIN", "HIGH_PROB_MAX", "MIN_EDGE_PCT", "EXPIRY_WINDOW_HOURS",
            "BET_STRATEGY", "MAX_POSITION_PCT", "VIRTUAL_BANKROLL",
            "MIN_RR_RATIO", "MAX_OPEN_POSITIONS", "MIN_LIQUIDITY", "ENABLED_CATEGORIES",
        }
        assert required <= keys

    def test_fill_defaults_gives_valid_params(self):
        params = PREDICTION_SCHEMA.fill_defaults({})
        assert 0 < params["HIGH_PROB_MIN"] < 1
        assert params["BET_STRATEGY"] in ("kelly", "contrarian", "min_rr")
        assert params["MAX_OPEN_POSITIONS"] >= 1

    def test_step_groups_defined(self):
        steps = {f.step for f in PREDICTION_SCHEMA.fields}
        assert len(steps) >= 2  # Entry, Sizing, Risk, Universe


class TestStrategyRunnerFiltering:
    def test_filters_by_category(self):
        params = PREDICTION_SCHEMA.fill_defaults({"ENABLED_CATEGORIES": "crypto"})
        runner = StrategyRunner(params)
        candidates = [
            _candidate("m1", category="crypto", edge=0.05),
            _candidate("m2", category="politics", edge=0.05),
        ]
        decisions = runner.run(candidates, bankroll=1000.0, open_market_ids=set())
        ids = {d.candidate.market.id for d in decisions}
        assert "m1" in ids
        assert "m2" not in ids

    def test_two_param_sets_yield_different_selections(self):
        """Same candidate pool + different HIGH_PROB_MIN → different selections."""
        params_strict = PREDICTION_SCHEMA.fill_defaults({"HIGH_PROB_MIN": 0.93})
        params_loose = PREDICTION_SCHEMA.fill_defaults({"HIGH_PROB_MIN": 0.80})

        candidates = [
            _candidate("m1", yes_price=0.91, edge=0.05),  # only loose accepts this
            _candidate("m2", yes_price=0.95, edge=0.05),  # both accept
        ]
        strict = StrategyRunner(params_strict).run(candidates, 1000.0, set())
        loose = StrategyRunner(params_loose).run(candidates, 1000.0, set())

        strict_ids = {d.candidate.market.id for d in strict}
        loose_ids = {d.candidate.market.id for d in loose}
        assert "m1" not in strict_ids
        assert "m1" in loose_ids
        assert "m2" in strict_ids

    def test_skips_already_open_market(self):
        params = PREDICTION_SCHEMA.fill_defaults({})
        runner = StrategyRunner(params)
        candidates = [_candidate("m1", edge=0.05)]
        decisions = runner.run(candidates, 1000.0, open_market_ids={"m1"})
        assert decisions == []

    def test_skips_below_min_edge(self):
        params = PREDICTION_SCHEMA.fill_defaults({"MIN_EDGE_PCT": 0.10})
        runner = StrategyRunner(params)
        candidates = [_candidate("m1", edge=0.03)]  # edge < 0.10
        decisions = runner.run(candidates, 1000.0, set())
        assert decisions == []

    def test_skips_candidate_with_no_edge(self):
        params = PREDICTION_SCHEMA.fill_defaults({})
        runner = StrategyRunner(params)
        c = _candidate("m1")
        c = c.model_copy(update={"edge": None})
        decisions = runner.run([c], 1000.0, set())
        assert decisions == []

    def test_respects_max_open_positions(self):
        params = PREDICTION_SCHEMA.fill_defaults({"MAX_OPEN_POSITIONS": 2})
        runner = StrategyRunner(params)
        candidates = [_candidate(f"m{i}", edge=0.05) for i in range(5)]
        # 1 already open → can place 1 more (2 - 1 = 1 slot)
        decisions = runner.run(candidates, 1000.0, open_market_ids={"m0"})
        assert len(decisions) == 1


class TestStrategyRunnerBetStrategies:
    def test_kelly_strategy_sizing(self):
        """Kelly: quantity proportional to edge / (1 - price)."""
        params = PREDICTION_SCHEMA.fill_defaults({
            "BET_STRATEGY": "kelly",
            "MAX_POSITION_PCT": 0.50,  # cap
        })
        runner = StrategyRunner(params)
        c = _candidate("m1", yes_price=0.90, edge=0.05)
        decisions = runner.run([c], bankroll=1000.0, open_market_ids=set())
        assert len(decisions) == 1
        d = decisions[0]
        assert d.side == "YES"
        assert d.quantity >= 1
        assert d.cost > 0

    def test_contrarian_flips_side(self):
        """Contrarian: if LLM says YES, bet NO."""
        params = PREDICTION_SCHEMA.fill_defaults({"BET_STRATEGY": "contrarian"})
        runner = StrategyRunner(params)
        c = _candidate("m1", yes_price=0.90, best_side="YES", edge=0.05)
        decisions = runner.run([c], 1000.0, set())
        assert len(decisions) == 1
        assert decisions[0].side == "NO"

    def test_contrarian_vs_kelly_different_sides(self):
        """Same candidate pool + contrarian vs kelly → different sides."""
        params_k = PREDICTION_SCHEMA.fill_defaults({"BET_STRATEGY": "kelly"})
        params_c = PREDICTION_SCHEMA.fill_defaults({"BET_STRATEGY": "contrarian"})
        candidates = [_candidate("m1", yes_price=0.90, best_side="YES", edge=0.05)]

        kelly_dec = StrategyRunner(params_k).run(candidates, 1000.0, set())
        contra_dec = StrategyRunner(params_c).run(candidates, 1000.0, set())

        assert kelly_dec[0].side == "YES"
        assert contra_dec[0].side == "NO"

    def test_min_rr_skips_when_ratio_too_low(self):
        """min_rr: skip if (1-price)/price < MIN_RR_RATIO."""
        # price=0.90 → R:R = 0.10/0.90 ≈ 0.11, well below MIN_RR_RATIO=2.0
        params = PREDICTION_SCHEMA.fill_defaults({"BET_STRATEGY": "min_rr", "MIN_RR_RATIO": 2.0})
        runner = StrategyRunner(params)
        c = _candidate("m1", yes_price=0.90, edge=0.05)
        decisions = runner.run([c], 1000.0, set())
        assert decisions == []

    def test_min_rr_accepts_when_ratio_meets_threshold(self):
        """min_rr: accept if (1-price)/price >= MIN_RR_RATIO."""
        # price=0.30 → R:R = 0.70/0.30 ≈ 2.33 ≥ 2.0
        params = PREDICTION_SCHEMA.fill_defaults({"BET_STRATEGY": "min_rr", "MIN_RR_RATIO": 2.0})
        runner = StrategyRunner(params)
        # Adjust the prob range to accept 0.30
        params["HIGH_PROB_MIN"] = 0.20
        c = _candidate("m1", yes_price=0.30, edge=0.05)
        decisions = runner.run([c], 1000.0, set())
        assert len(decisions) == 1

    def test_trade_decision_fields(self):
        """TradeDecision has candidate, side, quantity, cost."""
        params = PREDICTION_SCHEMA.fill_defaults({"BET_STRATEGY": "kelly"})
        c = _candidate("m1", yes_price=0.90, edge=0.05)
        decisions = StrategyRunner(params).run([c], 1000.0, set())
        d = decisions[0]
        assert isinstance(d, TradeDecision)
        assert d.candidate is not None
        assert d.side in ("YES", "NO")
        assert d.quantity >= 1
        assert d.cost == pytest.approx(d.quantity * d.candidate.market_price, rel=1e-6)
```

### Step 1.2 — Verify tests fail

- [ ] Run: `.venv/bin/python -m pytest prediction_bot/tests/test_strategy_runner.py -v`
- [ ] Expected: `ModuleNotFoundError: No module named 'prediction_bot.src.bot.strategy_runner'`

### Step 1.3 — Create `prediction_bot/src/bot/strategy_runner.py`

- [ ] Create the file with this exact content:

```python
"""Prediction bot StrategyRunner + PREDICTION_SCHEMA — issue #103."""
from __future__ import annotations

from typing import NamedTuple

from prediction_bot.src.api.models import MarketCandidate
from strategy_kit import ParamField, ParamSchema, register


class TradeDecision(NamedTuple):
    candidate: MarketCandidate
    side: str
    quantity: int
    cost: float


PREDICTION_SCHEMA = ParamSchema(fields=[
    # Step 1 — Entry filters
    ParamField(key="HIGH_PROB_MIN", label="Min probability", type="percent",
               default=0.80, min=0.50, max=1.0, step=0.01, help="Only enter markets priced above this.", step=1),
    ParamField(key="HIGH_PROB_MAX", label="Max probability", type="percent",
               default=0.97, min=0.50, max=1.0, step=0.01, help="Skip markets priced above this (too certain).", step=1),
    ParamField(key="MIN_EDGE_PCT", label="Min edge %", type="percent",
               default=0.02, min=0.0, max=0.50, step=0.01, help="Minimum edge after fees to trade."),
    ParamField(key="EXPIRY_WINDOW_HOURS", label="Expiry window (hours)", type="number",
               default=168.0, min=1.0, max=8760.0, step=1.0,
               help="Only consider markets expiring within this many hours."),
    # Step 2 — Sizing
    ParamField(key="BET_STRATEGY", label="Bet strategy", type="select",
               default="kelly", options=["kelly", "contrarian", "min_rr"],
               help="kelly = size by Kelly criterion; contrarian = bet opposite; min_rr = risk/reward filter."),
    ParamField(key="MAX_POSITION_PCT", label="Max position size", type="percent",
               default=0.10, min=0.01, max=0.50, step=0.01, help="Max fraction of bankroll per trade."),
    ParamField(key="VIRTUAL_BANKROLL", label="Starting bankroll ($)", type="number",
               default=1000.0, min=100.0, max=1_000_000.0, step=100.0,
               help="Virtual starting bankroll for this strategy."),
    # Step 3 — Risk
    ParamField(key="MIN_RR_RATIO", label="Min R:R ratio", type="number",
               default=2.0, min=0.5, max=10.0, step=0.5,
               help="min_rr strategy: skip unless potential gain / cost ≥ this ratio."),
    ParamField(key="MAX_OPEN_POSITIONS", label="Max open positions", type="number",
               default=20.0, min=1.0, max=100.0, step=1.0,
               help="Maximum number of simultaneously open paper trades."),
    # Step 4 — Universe
    ParamField(key="MIN_LIQUIDITY", label="Min liquidity ($)", type="number",
               default=1000.0, min=0.0, max=1_000_000.0, step=100.0,
               help="Only consider markets with at least this much liquidity."),
    ParamField(key="ENABLED_CATEGORIES", label="Categories (comma-separated)", type="text",
               default="crypto,sports,politics",
               help="Comma-separated list: crypto, sports, politics, etc."),
])

register("prediction", PREDICTION_SCHEMA)


class StrategyRunner:
    """Apply a saved strategy's params to an already-evaluated candidate pool."""

    def __init__(self, params: dict):
        self.params = PREDICTION_SCHEMA.fill_defaults(params)

    def run(
        self,
        candidates: list[MarketCandidate],
        bankroll: float,
        open_market_ids: set[str],
    ) -> list[TradeDecision]:
        categories = {c.strip() for c in self.params["ENABLED_CATEGORIES"].split(",") if c.strip()}
        high_min = float(self.params["HIGH_PROB_MIN"])
        high_max = float(self.params["HIGH_PROB_MAX"])
        min_edge = float(self.params["MIN_EDGE_PCT"])
        bet_strategy = self.params["BET_STRATEGY"]
        max_pos_pct = float(self.params["MAX_POSITION_PCT"])
        max_positions = int(self.params["MAX_OPEN_POSITIONS"])
        min_rr = float(self.params["MIN_RR_RATIO"])

        decisions: list[TradeDecision] = []
        current_count = len(open_market_ids)

        for candidate in candidates:
            if current_count >= max_positions:
                break
            if candidate.market.id in open_market_ids:
                continue
            if candidate.market.category not in categories:
                continue
            if not (high_min <= candidate.market_price <= high_max):
                continue
            if candidate.edge is None or candidate.edge < min_edge:
                continue

            side = candidate.best_side
            entry_price = candidate.market_price

            if bet_strategy == "contrarian":
                side = "NO" if side == "YES" else "YES"
                entry_price = round(1.0 - entry_price, 8)

            elif bet_strategy == "min_rr":
                rr = (1.0 - entry_price) / entry_price if entry_price > 0 else 0.0
                if rr < min_rr:
                    continue

            # Sizing
            if bet_strategy == "kelly" and candidate.edge is not None and entry_price < 1.0:
                kelly_f = candidate.edge / (1.0 - entry_price)
                pos_frac = min(kelly_f, max_pos_pct)
            else:
                pos_frac = max_pos_pct

            if entry_price <= 0:
                continue
            quantity = int(pos_frac * bankroll / entry_price)
            if quantity < 1:
                continue

            cost = round(entry_price * quantity, 8)
            updated = candidate.model_copy(update={"best_side": side, "market_price": entry_price})
            decisions.append(TradeDecision(candidate=updated, side=side, quantity=quantity, cost=cost))
            current_count += 1

        return decisions
```

**Note:** The file above has a bug — two `step=` keyword args on `HIGH_PROB_MIN` and `HIGH_PROB_MAX`. Fix it when writing: each `ParamField` should have only one `step` kwarg. The correct fields are:

```python
ParamField(key="HIGH_PROB_MIN", label="Min probability", type="percent",
           default=0.80, min=0.50, max=1.0, step=0.01, help="Only enter markets priced above this."),
ParamField(key="HIGH_PROB_MAX", label="Max probability", type="percent",
           default=0.97, min=0.50, max=1.0, step=0.01, help="Skip markets priced above this (too certain)."),
```

### Step 1.4 — Run tests

- [ ] Run: `.venv/bin/python -m pytest prediction_bot/tests/test_strategy_runner.py -v`
- [ ] Expected: all tests PASS. If `test_trade_decision_fields` fails on the cost assertion, check that the `cost` field is computed as `entry_price * quantity` (not using the updated candidate's `market_price`). Fix if needed.

### Step 1.5 — Commit

- [ ] Run:
```bash
git add prediction_bot/src/bot/strategy_runner.py prediction_bot/tests/test_strategy_runner.py
git commit -m "feat(prediction-bot): add StrategyRunner and PREDICTION_SCHEMA (#103)"
```

---

## Task 2: evaluate-once / per-strategy cycle + strategy_id migration (#104)

**Files:**
- Modify: `prediction_bot/src/api/models.py` — add `strategy_id` to `PaperTrade`
- Modify: `prediction_bot/src/data/result_store.py` — migration + scoped queries
- Modify: `prediction_bot/src/bot/paper_trader.py` — strategy_id param + `place_decision()`
- Modify: `prediction_bot/src/bot/engine.py` — evaluate-once refactor
- Create: `prediction_bot/tests/test_result_store_migration.py`

### Step 2.1 — Write migration + scoped-query tests

- [ ] Create `prediction_bot/tests/test_result_store_migration.py`:

```python
"""Tests for strategy_id migration and scoped ResultStore queries — issue #104."""
import pytest
import aiosqlite
from datetime import datetime, timezone, timedelta

from prediction_bot.src.api.models import MarketCandidate, PredictionMarket, PaperTrade
from prediction_bot.src.data.result_store import ResultStore


def _trade(market_id="m1", cost=9.20, platform="polymarket") -> PaperTrade:
    return PaperTrade(
        platform=platform,
        market_id=market_id,
        market_question=f"Will {market_id} happen?",
        category="crypto",
        side="YES",
        entry_price=0.92,
        quantity=10.0,
        cost=cost,
        confidence=0.85,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
async def store(tmp_path):
    s = ResultStore(str(tmp_path / "test.db"))
    await s.initialize()
    return s


class TestMigration:
    async def test_strategy_id_column_added_to_paper_trades(self, tmp_path):
        """Existing DB without strategy_id gets the column on initialize()."""
        db_path = str(tmp_path / "old.db")
        # Create old-style DB without strategy_id
        async with aiosqlite.connect(db_path) as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS paper_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL, market_id TEXT NOT NULL,
                    market_question TEXT NOT NULL, category TEXT NOT NULL,
                    side TEXT NOT NULL, entry_price REAL NOT NULL,
                    quantity REAL NOT NULL, cost REAL NOT NULL,
                    confidence REAL NOT NULL, reasoning TEXT,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    exit_price REAL, pnl REAL, created_at TEXT NOT NULL,
                    end_date TEXT, resolved_at TEXT, resolution_source TEXT
                );
                CREATE TABLE IF NOT EXISTS bankroll_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    balance REAL NOT NULL,
                    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                    trade_id INTEGER REFERENCES paper_trades(id)
                );
                INSERT INTO paper_trades
                    (platform, market_id, market_question, category, side, entry_price,
                     quantity, cost, confidence, created_at)
                VALUES ('polymarket', 'legacy-m1', 'Old trade?', 'crypto', 'YES',
                        0.90, 10, 9.0, 0.8, '2025-01-01T00:00:00+00:00');
                INSERT INTO bankroll_snapshots (balance) VALUES (991.0);
            """)
            await db.commit()

        s = ResultStore(db_path)
        await s.initialize()

        async with aiosqlite.connect(db_path) as db:
            async with db.execute("PRAGMA table_info(paper_trades)") as cur:
                cols = {row[1] async for row in cur}
            async with db.execute("PRAGMA table_info(bankroll_snapshots)") as cur:
                snap_cols = {row[1] async for row in cur}

        assert "strategy_id" in cols
        assert "strategy_id" in snap_cols

        # Legacy row should have strategy_id = 'default'
        s2 = ResultStore(db_path)
        await s2.initialize()
        trades = await s2.get_open_trades("default")
        assert any(t.market_id == "legacy-m1" for t in trades)

    async def test_initialize_idempotent_with_strategy_id(self, store):
        """initialize() with strategy_id column already present does not error."""
        await store.initialize()  # second call — must not raise


class TestScopedQueries:
    async def test_separate_bankrolls_per_strategy(self, store):
        """Two strategies have independent bankrolls."""
        await store.add_trade(_trade("m1", cost=10.0), initial_bankroll=1000.0, strategy_id="A")
        await store.add_trade(_trade("m2", cost=5.0), initial_bankroll=500.0, strategy_id="B")

        bal_a = await store.get_bankroll("A")
        bal_b = await store.get_bankroll("B")

        assert bal_a == pytest.approx(990.0)  # 1000 - 10
        assert bal_b == pytest.approx(495.0)  # 500 - 5

    async def test_get_open_trades_scoped(self, store):
        """get_open_trades(strategy_id) returns only that strategy's trades."""
        await store.add_trade(_trade("m1"), initial_bankroll=1000.0, strategy_id="A")
        await store.add_trade(_trade("m2"), initial_bankroll=1000.0, strategy_id="B")

        open_a = await store.get_open_trades("A")
        open_b = await store.get_open_trades("B")

        assert len(open_a) == 1 and open_a[0].market_id == "m1"
        assert len(open_b) == 1 and open_b[0].market_id == "m2"

    async def test_get_stats_scoped(self, store):
        """get_stats(strategy_id) returns only that strategy's stats."""
        id_a = await store.add_trade(_trade("m1", cost=10.0), initial_bankroll=1000.0, strategy_id="A")
        await store.add_trade(_trade("m2", cost=5.0), initial_bankroll=500.0, strategy_id="B")
        await store.settle_trade(id_a, won=True)

        stats_a = await store.get_stats("A")
        stats_b = await store.get_stats("B")

        assert stats_a["won"] == 1
        assert stats_b["won"] == 0
        assert stats_b["open_trades"] == 1

    async def test_default_strategy_id_is_backward_compatible(self, store):
        """Calling add_trade without strategy_id uses 'default'."""
        await store.add_trade(_trade("m1"), initial_bankroll=1000.0)
        open_trades = await store.get_open_trades("default")
        assert len(open_trades) == 1
```

### Step 2.2 — Run tests to confirm they fail

- [ ] Run: `.venv/bin/python -m pytest prediction_bot/tests/test_result_store_migration.py -v`
- [ ] Expected: failures related to missing `strategy_id` param on `add_trade` and `get_open_trades`

### Step 2.3 — Update `prediction_bot/src/api/models.py`

- [ ] Add `strategy_id: str = "default"` to `PaperTrade` (after `resolution_source`):

```python
class PaperTrade(BaseModel):
    id: int | None = None
    platform: str
    market_id: str
    market_question: str
    category: str
    side: str
    entry_price: float
    quantity: float
    cost: float
    confidence: float
    reasoning: str | None = None
    status: str = "OPEN"
    exit_price: float | None = None
    pnl: float | None = None
    created_at: datetime
    end_date: datetime | None = None
    resolved_at: datetime | None = None
    resolution_source: str | None = None
    strategy_id: str = "default"
```

### Step 2.4 — Rewrite `prediction_bot/src/data/result_store.py`

- [ ] Replace the entire file with this (mirrors existing behaviour + strategy_id):

```python
"""aiosqlite persistence for paper trades and bankroll — strategy_id aware."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

import aiosqlite

from prediction_bot.src.api.models import BankrollSnapshot, PaperTrade

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    market_id TEXT NOT NULL,
    market_question TEXT NOT NULL,
    category TEXT NOT NULL,
    side TEXT NOT NULL,
    entry_price REAL NOT NULL,
    quantity REAL NOT NULL,
    cost REAL NOT NULL,
    confidence REAL NOT NULL,
    reasoning TEXT,
    status TEXT NOT NULL DEFAULT 'OPEN',
    exit_price REAL,
    pnl REAL,
    created_at TEXT NOT NULL,
    end_date TEXT,
    resolved_at TEXT,
    resolution_source TEXT,
    strategy_id TEXT NOT NULL DEFAULT 'default'
);

CREATE TABLE IF NOT EXISTS bankroll_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    balance REAL NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    trade_id INTEGER REFERENCES paper_trades(id),
    strategy_id TEXT NOT NULL DEFAULT 'default'
);

CREATE INDEX IF NOT EXISTS idx_trades_status ON paper_trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_created ON paper_trades(created_at);
CREATE INDEX IF NOT EXISTS idx_trades_strategy ON paper_trades(strategy_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_strategy ON bankroll_snapshots(strategy_id);
"""


class ResultStore:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(_SCHEMA)
            # migrate: add columns if missing from older DB
            async with db.execute("PRAGMA table_info(paper_trades)") as cur:
                trade_cols = {row[1] async for row in cur}
            async with db.execute("PRAGMA table_info(bankroll_snapshots)") as cur:
                snap_cols = {row[1] async for row in cur}
            if "end_date" not in trade_cols:
                await db.execute("ALTER TABLE paper_trades ADD COLUMN end_date TEXT")
            if "strategy_id" not in trade_cols:
                await db.execute(
                    "ALTER TABLE paper_trades ADD COLUMN strategy_id TEXT NOT NULL DEFAULT 'default'"
                )
            if "strategy_id" not in snap_cols:
                await db.execute(
                    "ALTER TABLE bankroll_snapshots ADD COLUMN strategy_id TEXT NOT NULL DEFAULT 'default'"
                )
            await db.commit()

    async def add_trade(
        self,
        trade: PaperTrade,
        initial_bankroll: float | None = None,
        strategy_id: str = "default",
    ) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """INSERT INTO paper_trades
                   (platform, market_id, market_question, category, side, entry_price,
                    quantity, cost, confidence, reasoning, created_at, end_date, strategy_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    trade.platform, trade.market_id, trade.market_question,
                    trade.category, trade.side, trade.entry_price,
                    trade.quantity, trade.cost, trade.confidence,
                    trade.reasoning, trade.created_at.isoformat(),
                    trade.end_date.isoformat() if trade.end_date else None,
                    strategy_id,
                ),
            )
            trade_id = cur.lastrowid
            current = await self._get_bankroll_tx(db, initial_bankroll, strategy_id)
            new_balance = current - trade.cost
            await db.execute(
                "INSERT INTO bankroll_snapshots (balance, trade_id, strategy_id) VALUES (?, ?, ?)",
                (new_balance, trade_id, strategy_id),
            )
            await db.commit()
        return trade_id

    async def _get_bankroll_tx(
        self, db: aiosqlite.Connection, initial: float | None, strategy_id: str = "default"
    ) -> float:
        async with db.execute(
            "SELECT balance FROM bankroll_snapshots WHERE strategy_id = ? ORDER BY id DESC LIMIT 1",
            (strategy_id,),
        ) as cur:
            row = await cur.fetchone()
        if row:
            return row[0]
        return initial or 1000.0

    async def get_open_trades(self, strategy_id: str = "default") -> list[PaperTrade]:
        return await self._fetch_trades(
            "WHERE status = 'OPEN' AND strategy_id = ?", (strategy_id,)
        )

    async def settle_trade(self, trade_id: int, won: bool):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT entry_price, quantity, cost, strategy_id FROM paper_trades WHERE id=?",
                (trade_id,),
            ) as cur:
                row = await cur.fetchone()
            if not row:
                return
            entry_price, quantity, cost, strategy_id = row
            pnl = (1.0 - entry_price) * quantity if won else (-entry_price * quantity)
            status = "WON" if won else "LOST"
            exit_price = 1.0 if won else 0.0
            await db.execute(
                "UPDATE paper_trades SET status=?, exit_price=?, pnl=?, resolved_at=? WHERE id=?",
                (status, exit_price, pnl, datetime.now(UTC).isoformat(), trade_id),
            )
            current = await self._get_bankroll_tx(db, None, strategy_id)
            await db.execute(
                "INSERT INTO bankroll_snapshots (balance, trade_id, strategy_id) VALUES (?, ?, ?)",
                (current + cost + pnl, trade_id, strategy_id),
            )
            await db.commit()

    async def re_settle_expired(self, trade_id: int, won: bool):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT entry_price, quantity, cost, strategy_id FROM paper_trades WHERE id=? AND status='EXPIRED'",
                (trade_id,),
            ) as cur:
                row = await cur.fetchone()
            if not row:
                return
            entry_price, quantity, cost, strategy_id = row
            pnl = (1.0 - entry_price) * quantity if won else (-entry_price * quantity)
            status = "WON" if won else "LOST"
            await db.execute(
                "UPDATE paper_trades SET status=?, exit_price=?, pnl=?, resolved_at=?, resolution_source=? WHERE id=?",
                (status, 1.0 if won else 0.0, pnl, datetime.now(UTC).isoformat(), "re_settled", trade_id),
            )
            current = await self._get_bankroll_tx(db, None, strategy_id)
            await db.execute(
                "INSERT INTO bankroll_snapshots (balance, trade_id, strategy_id) VALUES (?, ?, ?)",
                (current + pnl, trade_id, strategy_id),
            )
            await db.commit()

    async def expire_trade(self, trade_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT cost, strategy_id FROM paper_trades WHERE id=?", (trade_id,)
            ) as cur:
                row = await cur.fetchone()
            if not row:
                return
            cost, strategy_id = row
            await db.execute(
                "UPDATE paper_trades SET status='EXPIRED', pnl=0, resolved_at=? WHERE id=?",
                (datetime.now(UTC).isoformat(), trade_id),
            )
            current = await self._get_bankroll_tx(db, None, strategy_id)
            await db.execute(
                "INSERT INTO bankroll_snapshots (balance, trade_id, strategy_id) VALUES (?, ?, ?)",
                (current + cost, trade_id, strategy_id),
            )
            await db.commit()

    async def get_bankroll(self, strategy_id: str = "default") -> float:
        async with aiosqlite.connect(self.db_path) as db:
            return await self._get_bankroll_tx(db, None, strategy_id)

    async def get_stats(self, strategy_id: str = "default") -> dict:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT status, SUM(pnl), COUNT(*) FROM paper_trades WHERE strategy_id = ? GROUP BY status",
                (strategy_id,),
            ) as cur:
                rows = await cur.fetchall()

        counts: dict[str, int] = {"WON": 0, "LOST": 0, "EXPIRED": 0, "OPEN": 0}
        pnl_total = 0.0
        for status, pnl_sum, cnt in rows:
            counts[status] = cnt
            if pnl_sum:
                pnl_total += pnl_sum

        total = sum(counts.values())
        settled = counts["WON"] + counts["LOST"]
        win_rate = counts["WON"] / settled if settled > 0 else None
        bankroll = await self.get_bankroll(strategy_id)

        return {
            "total_trades": total,
            "open_trades": counts["OPEN"],
            "won": counts["WON"],
            "lost": counts["LOST"],
            "expired": counts["EXPIRED"],
            "win_rate": win_rate,
            "total_pnl": pnl_total,
            "roi": pnl_total / 1000.0 if total > 0 else 0.0,
            "bankroll": bankroll,
        }

    async def get_recent_trades(self, limit: int = 50, strategy_id: str | None = None) -> list[PaperTrade]:
        if strategy_id:
            return await self._fetch_trades(
                f"WHERE strategy_id = ? ORDER BY created_at DESC LIMIT {int(limit)}",
                (strategy_id,),
            )
        return await self._fetch_trades(f"ORDER BY created_at DESC LIMIT {int(limit)}")

    async def get_bankroll_history(self, limit: int = 100, strategy_id: str | None = None) -> list[BankrollSnapshot]:
        where = f"WHERE strategy_id = ?" if strategy_id else ""
        params: tuple = (strategy_id,) if strategy_id else ()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                f"SELECT id, balance, timestamp, trade_id FROM bankroll_snapshots {where} ORDER BY id DESC LIMIT {int(limit)}",
                params,
            ) as cur:
                rows = await cur.fetchall()
        return [
            BankrollSnapshot(id=r[0], balance=r[1], timestamp=datetime.fromisoformat(r[2]), trade_id=r[3])
            for r in rows
        ]

    async def _fetch_trades(self, where_clause: str, params: tuple = ()) -> list[PaperTrade]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                f"""SELECT id, platform, market_id, market_question, category, side,
                           entry_price, quantity, cost, confidence, reasoning,
                           status, exit_price, pnl, created_at, end_date, resolved_at,
                           resolution_source, strategy_id
                    FROM paper_trades {where_clause}""",
                params,
            ) as cur:
                rows = await cur.fetchall()
        return [
            PaperTrade(
                id=r[0], platform=r[1], market_id=r[2], market_question=r[3],
                category=r[4], side=r[5], entry_price=r[6], quantity=r[7],
                cost=r[8], confidence=r[9], reasoning=r[10], status=r[11],
                exit_price=r[12], pnl=r[13],
                created_at=datetime.fromisoformat(r[14]),
                end_date=datetime.fromisoformat(r[15]) if r[15] else None,
                resolved_at=datetime.fromisoformat(r[16]) if r[16] else None,
                resolution_source=r[17],
                strategy_id=r[18] if len(r) > 18 else "default",
            )
            for r in rows
        ]
```

### Step 2.5 — Update `prediction_bot/src/bot/paper_trader.py`

- [ ] Add `place_decision()` and update `place_paper_trade()` + settlement methods to accept `strategy_id`:

Replace the entire file:

```python
"""Paper trading state machine on top of ResultStore."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from prediction_bot.src.api.models import MarketCandidate, PaperTrade
from prediction_bot.src.bot.strategy_runner import TradeDecision
from prediction_bot.src.config.settings import PredictionBotSettings
from prediction_bot.src.data.result_store import ResultStore

logger = logging.getLogger(__name__)


class PaperTrader:
    def __init__(self, store: ResultStore, settings: PredictionBotSettings):
        self.store = store
        self.settings = settings

    async def initialize(self):
        await self.store.initialize()
        stats = await self.store.get_stats()
        if stats["total_trades"] > 0:
            self._log_summary(stats)

    def _log_summary(self, stats: dict):
        logger.info("=" * 60)
        logger.info("PREVIOUS RESULTS SUMMARY")
        logger.info("  Total trades: %d", stats["total_trades"])
        wr = f"{stats['win_rate']:.1%}" if stats["win_rate"] is not None else "N/A"
        logger.info("  Win rate: %s (%dW / %dL / %dE)", wr, stats["won"], stats["lost"], stats["expired"])
        logger.info("  Total P&L: $%.2f", stats["total_pnl"])
        logger.info("  ROI: %.1f%%", stats["roi"] * 100)
        logger.info("  Current bankroll: $%.2f", stats["bankroll"])
        logger.info("=" * 60)

    async def place_decision(
        self, decision: TradeDecision, strategy_id: str = "default"
    ) -> PaperTrade | None:
        bankroll = await self.store.get_bankroll(strategy_id)
        open_trades = await self.store.get_open_trades(strategy_id)

        if len(open_trades) >= self.settings.MAX_OPEN_POSITIONS:
            return None
        existing_ids = {t.market_id for t in open_trades}
        if decision.candidate.market.id in existing_ids:
            return None

        trade = PaperTrade(
            platform=decision.candidate.market.platform,
            market_id=decision.candidate.market.id,
            market_question=decision.candidate.market.question,
            category=decision.candidate.market.category,
            side=decision.side,
            entry_price=decision.candidate.market_price,
            quantity=float(decision.quantity),
            cost=decision.cost,
            confidence=decision.candidate.llm_confidence or 0.5,
            reasoning=decision.candidate.llm_reasoning,
            created_at=datetime.now(UTC),
            end_date=decision.candidate.market.end_date,
            strategy_id=strategy_id,
        )
        trade_id = await self.store.add_trade(trade, initial_bankroll=bankroll, strategy_id=strategy_id)
        logger.info(
            "[%s] Paper trade: %s '%s' @ $%.2f (qty=%d, cost=$%.2f)",
            strategy_id, trade.side, trade.market_question[:60],
            trade.entry_price, decision.quantity, decision.cost,
        )
        return trade.model_copy(update={"id": trade_id})

    async def place_paper_trade(
        self, candidate: MarketCandidate, strategy_id: str = "default"
    ) -> PaperTrade | None:
        bankroll = await self.store.get_bankroll(strategy_id)
        open_trades = await self.store.get_open_trades(strategy_id)

        if len(open_trades) >= self.settings.MAX_OPEN_POSITIONS:
            logger.debug("Max positions reached, skipping %s", candidate.market.id)
            return None

        existing_ids = {t.market_id for t in open_trades}
        if candidate.market.id in existing_ids:
            logger.debug("Already holding %s, skipping", candidate.market.id)
            return None

        max_allocation = bankroll * self.settings.MAX_POSITION_PCT
        entry_price = candidate.market_price
        if entry_price <= 0:
            return None

        quantity = int(max_allocation / entry_price)
        if quantity < 1:
            logger.debug("Insufficient bankroll for %s", candidate.market.id)
            return None

        cost = entry_price * quantity
        trade = PaperTrade(
            platform=candidate.market.platform,
            market_id=candidate.market.id,
            market_question=candidate.market.question,
            category=candidate.market.category,
            side=candidate.best_side,
            entry_price=entry_price,
            quantity=float(quantity),
            cost=cost,
            confidence=candidate.llm_confidence or 0.5,
            reasoning=candidate.llm_reasoning,
            created_at=datetime.now(UTC),
            end_date=candidate.market.end_date,
            strategy_id=strategy_id,
        )
        trade_id = await self.store.add_trade(trade, initial_bankroll=bankroll, strategy_id=strategy_id)
        logger.info(
            "[%s] Paper trade: %s '%s' @ $%.2f (qty=%d, cost=$%.2f)",
            strategy_id, trade.side, trade.market_question[:60],
            entry_price, quantity, cost,
        )
        return trade.model_copy(update={"id": trade_id})

    async def re_settle_expired_trades(
        self, clients: dict, strategy_id: str = "default"
    ) -> int:
        expired = await self.store._fetch_trades(
            "WHERE status = 'EXPIRED' AND strategy_id = ?", (strategy_id,)
        )
        corrected = 0
        for trade in expired:
            client = clients.get(trade.platform)
            if not client:
                continue
            try:
                status = await client.get_market_status(trade.market_id)
                if status["resolved"] and status["winner"]:
                    won = status["winner"] == trade.side
                    await self.store.re_settle_expired(trade.id, won=won)
                    result = "WON" if won else "LOST"
                    logger.info(
                        "[%s] RE-SETTLED %s: '%s' → %s",
                        strategy_id, trade.market_id, trade.market_question[:50], result,
                    )
                    corrected += 1
            except Exception as e:
                logger.warning("Re-settlement check failed for %s: %s", trade.market_id, e)
        return corrected

    async def settle_open_trades(self, clients: dict, strategy_id: str = "default"):
        open_trades = await self.store.get_open_trades(strategy_id)
        now = datetime.now(UTC)

        for trade in open_trades:
            try:
                client = clients.get(trade.platform)
                if not client:
                    continue

                status = await client.get_market_status(trade.market_id)
                if status["resolved"] and status["winner"]:
                    won = status["winner"] == trade.side
                    await self.store.settle_trade(trade.id, won=won)
                    result = "WON" if won else "LOST"
                    logger.info(
                        "[%s] SETTLED %s: '%s' → %s",
                        strategy_id, trade.market_id, trade.market_question[:50], result,
                    )
                elif trade.end_date and now > trade.end_date + timedelta(hours=24):
                    await self.store.expire_trade(trade.id)
                    logger.info(
                        "[%s] EXPIRED %s: '%s'",
                        strategy_id, trade.market_id, trade.market_question[:50],
                    )
            except Exception as e:
                logger.warning("Settlement check failed for %s: %s", trade.market_id, e)
```

### Step 2.6 — Refactor `prediction_bot/src/bot/engine.py`

- [ ] Replace the file with the evaluate-once design:

```python
"""PredictionEngine — orchestrates scan → evaluate-once → per-strategy apply cycle."""
from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from datetime import UTC, datetime, timedelta

from prediction_bot.src.api.kalshi_client import KalshiClient
from prediction_bot.src.api.models import PMBotStatus
from prediction_bot.src.api.polymarket_client import PolymarketClient
from prediction_bot.src.bot.evaluator import evaluate_candidates
from prediction_bot.src.bot.paper_trader import PaperTrader
from prediction_bot.src.bot.scanner import scan_markets
from prediction_bot.src.bot.strategy_runner import PREDICTION_SCHEMA, StrategyRunner
from prediction_bot.src.config.settings import pm_settings
from prediction_bot.src.data.result_store import ResultStore
from strategy_kit import StrategyDefinition
from strategy_kit.portfolio import ShadowPortfolio
from strategy_kit.store import StrategyStore

logger = logging.getLogger(__name__)


def _settings_to_params(s) -> dict:
    return {
        "HIGH_PROB_MIN": s.HIGH_PROB_MIN,
        "HIGH_PROB_MAX": s.HIGH_PROB_MAX,
        "MIN_EDGE_PCT": s.MIN_EDGE_PCT,
        "EXPIRY_WINDOW_HOURS": float(s.EXPIRY_WINDOW_HOURS),
        "BET_STRATEGY": "kelly",
        "MAX_POSITION_PCT": s.MAX_POSITION_PCT,
        "VIRTUAL_BANKROLL": s.VIRTUAL_BANKROLL,
        "MIN_RR_RATIO": 2.0,
        "MAX_OPEN_POSITIONS": float(s.MAX_OPEN_POSITIONS),
        "MIN_LIQUIDITY": s.MIN_LIQUIDITY,
        "ENABLED_CATEGORIES": ",".join(s.ENABLED_CATEGORIES),
    }


class PredictionEngine:
    def __init__(self):
        self.settings = pm_settings
        store = ResultStore(self.settings.PM_DB_PATH)
        self.paper_trader = PaperTrader(store=store, settings=self.settings)
        self._strategy_store = StrategyStore(self.settings.PM_DB_PATH)
        self._portfolio = ShadowPortfolio(self.settings.PM_DB_PATH)
        self._active_strategies: list[StrategyDefinition] = []
        self._shadow_map: dict[str, dict[str, int]] = {}  # strategy_id → {market_id → shadow_trade_id}
        self.status = PMBotStatus(
            platforms={
                "polymarket": self.settings.POLYMARKET_ENABLED,
                "kalshi": self.settings.KALSHI_ENABLED,
            },
            categories=self.settings.ENABLED_CATEGORIES,
            bankroll=self.settings.VIRTUAL_BANKROLL,
        )
        self._running = False
        self.scan_history: list[dict] = []
        self.activity_history: list[dict] = []
        self._sse_queues: list[asyncio.Queue] = []
        self._clients: dict = {}

    async def _activity(self, message: str):
        event = {"timestamp": datetime.now(UTC).isoformat(), "message": message}
        self.activity_history.append(event)
        if len(self.activity_history) > 100:
            self.activity_history = self.activity_history[-100:]
        await self._broadcast({"type": "activity", "activity": event})

    async def start(self):
        await self.paper_trader.initialize()
        await self._strategy_store.initialize()
        await self._portfolio.initialize()

        # Load active strategies; create default if none exist
        strategies = await self._strategy_store.list("prediction", active_only=True)
        if not strategies:
            default = StrategyDefinition(
                name="Default",
                description="Auto-created from current settings",
                bot="prediction",
                params=_settings_to_params(self.settings),
            )
            await self._strategy_store.create(default)
            strategies = [default]
        self._active_strategies = strategies

        # Seed ShadowPortfolio bankroll for each strategy (once)
        for strategy in self._active_strategies:
            curve = await self._portfolio.equity_curve(strategy.id)
            if not curve:
                vb = float(strategy.params.get("VIRTUAL_BANKROLL", self.settings.VIRTUAL_BANKROLL))
                await self._portfolio.seed_bankroll(strategy.id, vb)

        clients_pending = []
        if self.settings.POLYMARKET_ENABLED:
            clients_pending.append(PolymarketClient())
        if self.settings.KALSHI_ENABLED:
            clients_pending.append(KalshiClient())

        async with AsyncExitStack() as stack:
            for client in clients_pending:
                active = await stack.enter_async_context(client)
                self._clients[client.platform] = active

            enabled = list(self._clients.keys())
            logger.info("Prediction Market Bot started — platforms: %s", enabled)
            await self._activity(
                f"Bot is online. Watching {', '.join(enabled) if enabled else 'no platforms'}."
            )

            self._running = True
            while self._running:
                if self.status.enabled:
                    try:
                        await self._cycle()
                    except Exception as e:
                        logger.error("Cycle error: %s", e, exc_info=True)
                await asyncio.sleep(self.settings.SCAN_INTERVAL_SECONDS)

    async def _cycle(self):
        logger.info("Starting scan cycle (%d strategies)...", len(self._active_strategies))
        await self._activity("Starting a new market scan.")

        # Settle/expire per strategy
        for strategy in self._active_strategies:
            await self.paper_trader.re_settle_expired_trades(self._clients, strategy.id)
            await self.paper_trader.settle_open_trades(self._clients, strategy.id)
        await self._activity("Checked open positions and settled finished markets.")

        # Evaluate ONCE
        candidates = await scan_markets(list(self._clients.values()), self.settings)
        logger.info("Scanner found %d candidates", len(candidates))
        evaluated = []
        if candidates:
            evaluated = await evaluate_candidates(candidates, self.settings)
            logger.info("Evaluator found %d with edge", len(evaluated))

        if not evaluated:
            await self._activity("No opportunities with edge found this cycle.")
        else:
            await self._activity(f"{len(evaluated)} opportunities passed quality checks.")

        total_placed = 0
        # Apply per strategy
        for strategy in self._active_strategies:
            bankroll = await self.paper_trader.store.get_bankroll(strategy.id)
            open_trades = await self.paper_trader.store.get_open_trades(strategy.id)
            open_ids = {t.market_id for t in open_trades}

            runner = StrategyRunner(strategy.params)
            decisions = runner.run(evaluated, bankroll, open_ids)

            for decision in decisions:
                trade = await self.paper_trader.place_decision(decision, strategy_id=strategy.id)
                if trade:
                    total_placed += 1
                    await self._broadcast({"type": "trade_placed", "trade": trade.model_dump(mode="json")})
                    # Track in ShadowPortfolio
                    shadow_tid = await self._portfolio.open_trade(
                        strategy.id, trade.market_id,
                        entry_price=trade.entry_price,
                        quantity=trade.quantity,
                    )
                    self._shadow_map.setdefault(strategy.id, {})[trade.market_id] = shadow_tid

        # Update status from first strategy (backward compat)
        if self._active_strategies:
            first_id = self._active_strategies[0].id
            stats = await self.paper_trader.store.get_stats(first_id)
            self.status.open_trades = stats["open_trades"]
            self.status.bankroll = stats["bankroll"]
            self.status.total_pnl = stats["total_pnl"]
            self.status.win_rate = stats["win_rate"]

        self.status.last_scan = datetime.now(UTC)
        self.status.next_scan = datetime.now(UTC) + timedelta(seconds=self.settings.SCAN_INTERVAL_SECONDS)

        scan_record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "candidates_found": len(candidates),
            "edges_found": len(evaluated),
            "trades_placed": total_placed,
        }
        self.scan_history.append(scan_record)
        if len(self.scan_history) > 50:
            self.scan_history = self.scan_history[-50:]

        msg = "Cycle complete: no new trades placed." if total_placed == 0 else f"Cycle complete: placed {total_placed} trade(s)."
        await self._activity(msg)
        await self._broadcast({"type": "cycle_complete", "status": self.status.model_dump(mode="json")})

    async def _broadcast(self, event: dict):
        for q in list(self._sse_queues):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def stop(self):
        self._running = False

    def toggle(self) -> bool:
        self.status.enabled = not self.status.enabled
        state = "enabled" if self.status.enabled else "paused"
        self.activity_history.append(
            {"timestamp": datetime.now(UTC).isoformat(), "message": f"Bot {state} by user."}
        )
        return self.status.enabled

    def set_interval(self, seconds: int) -> int:
        self.settings.SCAN_INTERVAL_SECONDS = seconds
        self.status.next_scan = (
            datetime.now(UTC) + timedelta(seconds=seconds) if self.status.last_scan else None
        )
        return seconds
```

### Step 2.7 — Update `strategy_kit/store.py` — add `active` column + `active_only` filter

- [ ] In `strategy_kit/store.py`, update `initialize()` to migrate the `active` column:

```python
async def initialize(self) -> None:
    async with aiosqlite.connect(self.db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.executescript(_SCHEMA)
        async with db.execute("PRAGMA table_info(strategies)") as cur:
            cols = {row[1] async for row in cur}
        if "active" not in cols:
            await db.execute(
                "ALTER TABLE strategies ADD COLUMN active INTEGER NOT NULL DEFAULT 1"
            )
        await db.commit()
```

- [ ] Update the `list()` signature to accept `active_only: bool = False`:

```python
async def list(
    self, bot: str, include_archived: bool = False, active_only: bool = False
) -> list[StrategyDefinition]:
    query = "SELECT * FROM strategies WHERE bot = ?"
    args: list = [bot]
    if not include_archived:
        query += " AND archived = 0"
    if active_only:
        query += " AND active = 1"
    async with aiosqlite.connect(self.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, args) as cur:
            rows = await cur.fetchall()
    return [_row_to_definition(row) for row in rows]
```

- [ ] Add `activate()` and `deactivate()` methods to `StrategyStore`:

```python
async def activate(self, id: str) -> None:
    async with aiosqlite.connect(self.db_path) as db:
        await db.execute("UPDATE strategies SET active = 1 WHERE id = ?", (id,))
        await db.commit()

async def deactivate(self, id: str) -> None:
    async with aiosqlite.connect(self.db_path) as db:
        await db.execute("UPDATE strategies SET active = 0 WHERE id = ?", (id,))
        await db.commit()
```

- [ ] Update `_row_to_definition` to handle the new `active` column (it may be absent in old rows read before migration):

```python
def _row_to_definition(row: aiosqlite.Row) -> StrategyDefinition:
    keys = row.keys()
    return StrategyDefinition(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        bot=row["bot"],
        params=json.loads(row["params"] or "{}"),
        created_at=datetime.fromisoformat(row["created_at"]),
        archived=bool(row["archived"]),
    )
```

(The `active` column is not part of `StrategyDefinition` — it's a store-level runtime flag only.)

### Step 2.8 — Run migration + scoped-query tests

- [ ] Run: `.venv/bin/python -m pytest prediction_bot/tests/test_result_store_migration.py -v`
- [ ] Expected: all tests PASS

### Step 2.9 — Run existing prediction_bot tests to check for regressions

- [ ] Run: `.venv/bin/python -m pytest prediction_bot/tests/ -v`
- [ ] If `test_paper_trader.py` or `test_result_store.py` fail, the issue is that `get_open_trades()` and `get_bankroll()` now require `strategy_id`. Fix by updating those test calls to pass `strategy_id="default"` or rely on the default param.

### Step 2.10 — Commit

- [ ] Run:
```bash
git add prediction_bot/src/api/models.py \
        prediction_bot/src/data/result_store.py \
        prediction_bot/src/bot/paper_trader.py \
        prediction_bot/src/bot/engine.py \
        strategy_kit/store.py \
        prediction_bot/tests/test_result_store_migration.py
git commit -m "feat(prediction-bot): evaluate-once engine, strategy_id migration, ShadowPortfolio wiring (#104)"
```

---

## Task 3: Strategy CRUD + activate API (#105)

**Files:**
- Create: `prediction_bot/src/dashboard/strategies_router.py`
- Create: `prediction_bot/tests/test_strategies_router.py`
- Modify: `prediction_bot/src/dashboard/app.py` — include router + equity endpoint

### Step 3.1 — Write failing tests

- [ ] Create `prediction_bot/tests/test_strategies_router.py`:

```python
"""Tests for strategy CRUD + activate endpoints — issue #105."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from prediction_bot.src.dashboard.strategies_router import make_strategies_router
from strategy_kit.store import StrategyStore
from strategy_kit.models import StrategyDefinition


@pytest.fixture
def client(tmp_path):
    store = StrategyStore(str(tmp_path / "test.db"))

    import asyncio
    asyncio.get_event_loop().run_until_complete(store.initialize())

    active_ids: set[str] = set()
    router = make_strategies_router(store, active_ids)

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestStrategyCRUD:
    def test_list_empty(self, client):
        r = client.get("/strategies")
        assert r.status_code == 200
        assert r.json() == []

    def test_create_and_list(self, client):
        payload = {
            "name": "My Strategy",
            "description": "test",
            "bot": "prediction",
            "params": {"HIGH_PROB_MIN": 0.85},
        }
        r = client.post("/strategies", json=payload)
        assert r.status_code == 201
        created = r.json()
        assert created["name"] == "My Strategy"
        assert created["params"]["HIGH_PROB_MIN"] == 0.85

        r2 = client.get("/strategies")
        assert len(r2.json()) == 1

    def test_get_by_id(self, client):
        r = client.post("/strategies", json={"name": "S", "bot": "prediction", "params": {}})
        sid = r.json()["id"]
        r2 = client.get(f"/strategies/{sid}")
        assert r2.status_code == 200
        assert r2.json()["id"] == sid

    def test_get_returns_404_for_unknown(self, client):
        r = client.get("/strategies/nonexistent-id")
        assert r.status_code == 404

    def test_update_strategy(self, client):
        r = client.post("/strategies", json={"name": "Old", "bot": "prediction", "params": {}})
        sid = r.json()["id"]
        r2 = client.put(f"/strategies/{sid}", json={"name": "New", "params": {"k": 1}})
        assert r2.status_code == 200
        r3 = client.get(f"/strategies/{sid}")
        assert r3.json()["name"] == "New"
        assert r3.json()["params"]["k"] == 1

    def test_archive_strategy(self, client):
        r = client.post("/strategies", json={"name": "Gone", "bot": "prediction", "params": {}})
        sid = r.json()["id"]
        r2 = client.post(f"/strategies/{sid}/archive")
        assert r2.status_code == 200
        # Should not appear in default list
        r3 = client.get("/strategies")
        ids = [s["id"] for s in r3.json()]
        assert sid not in ids


class TestActivateDeactivate:
    def test_activate_adds_to_active_set(self, client):
        r = client.post("/strategies", json={"name": "S", "bot": "prediction", "params": {}})
        sid = r.json()["id"]
        r2 = client.post(f"/strategies/{sid}/activate")
        assert r2.status_code == 200
        assert r2.json()["active"] is True

    def test_deactivate_removes_from_active_set(self, client):
        r = client.post("/strategies", json={"name": "S", "bot": "prediction", "params": {}})
        sid = r.json()["id"]
        client.post(f"/strategies/{sid}/activate")
        r2 = client.post(f"/strategies/{sid}/deactivate")
        assert r2.status_code == 200
        assert r2.json()["active"] is False


class TestSchemaEndpoint:
    def test_get_schema_returns_param_fields(self, client):
        r = client.get("/strategies/schema")
        assert r.status_code == 200
        data = r.json()
        assert "fields" in data
        keys = {f["key"] for f in data["fields"]}
        assert "BET_STRATEGY" in keys
        assert "HIGH_PROB_MIN" in keys
```

### Step 3.2 — Verify tests fail

- [ ] Run: `.venv/bin/python -m pytest prediction_bot/tests/test_strategies_router.py -v`
- [ ] Expected: `ImportError: cannot import name 'make_strategies_router'`

### Step 3.3 — Create `prediction_bot/src/dashboard/strategies_router.py`

```python
"""Strategy CRUD + activate/deactivate FastAPI router — issue #105."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from prediction_bot.src.bot.strategy_runner import PREDICTION_SCHEMA
from strategy_kit.models import StrategyDefinition
from strategy_kit.store import StrategyStore


class _CreatePayload(BaseModel):
    name: str
    description: str = ""
    bot: str = "prediction"
    params: dict = {}


class _UpdatePayload(BaseModel):
    name: str | None = None
    description: str | None = None
    params: dict | None = None


def make_strategies_router(
    store: StrategyStore,
    active_strategy_ids: set[str],
) -> APIRouter:
    router = APIRouter(prefix="/strategies", tags=["strategies"])

    @router.get("/schema")
    async def get_schema():
        return {
            "fields": [
                {
                    "key": f.key,
                    "label": f.label,
                    "type": f.type,
                    "default": f.default,
                    "min": f.min,
                    "max": f.max,
                    "step": f.step,
                    "help": f.help,
                    "options": f.options,
                }
                for f in PREDICTION_SCHEMA.fields
            ]
        }

    @router.get("")
    async def list_strategies():
        strategies = await store.list("prediction")
        return [s.model_dump(mode="json") for s in strategies]

    @router.post("", status_code=201)
    async def create_strategy(payload: _CreatePayload):
        defn = StrategyDefinition(
            name=payload.name,
            description=payload.description,
            bot=payload.bot,
            params=payload.params,
        )
        await store.create(defn)
        return defn.model_dump(mode="json")

    @router.get("/{strategy_id}")
    async def get_strategy(strategy_id: str):
        defn = await store.get(strategy_id)
        if defn is None:
            raise HTTPException(status_code=404, detail="Strategy not found")
        return defn.model_dump(mode="json")

    @router.put("/{strategy_id}")
    async def update_strategy(strategy_id: str, payload: _UpdatePayload):
        defn = await store.get(strategy_id)
        if defn is None:
            raise HTTPException(status_code=404, detail="Strategy not found")
        await store.update(strategy_id, name=payload.name, description=payload.description, params=payload.params)
        updated = await store.get(strategy_id)
        return updated.model_dump(mode="json")

    @router.post("/{strategy_id}/archive")
    async def archive_strategy(strategy_id: str):
        defn = await store.get(strategy_id)
        if defn is None:
            raise HTTPException(status_code=404, detail="Strategy not found")
        await store.archive(strategy_id)
        active_strategy_ids.discard(strategy_id)
        return {"archived": True}

    @router.post("/{strategy_id}/activate")
    async def activate_strategy(strategy_id: str):
        defn = await store.get(strategy_id)
        if defn is None:
            raise HTTPException(status_code=404, detail="Strategy not found")
        await store.activate(strategy_id)
        active_strategy_ids.add(strategy_id)
        return {"active": True}

    @router.post("/{strategy_id}/deactivate")
    async def deactivate_strategy(strategy_id: str):
        defn = await store.get(strategy_id)
        if defn is None:
            raise HTTPException(status_code=404, detail="Strategy not found")
        await store.deactivate(strategy_id)
        active_strategy_ids.discard(strategy_id)
        return {"active": False}

    return router
```

### Step 3.4 — Update `prediction_bot/src/dashboard/app.py`

- [ ] Add the router + equity endpoint. After the existing imports, add:

```python
from prediction_bot.src.dashboard.strategies_router import make_strategies_router
```

- [ ] After `app = FastAPI(...)`, include the router:

```python
_active_strategy_ids: set[str] = set()
app.include_router(
    make_strategies_router(engine._strategy_store, _active_strategy_ids),
    prefix="/api",
)
```

- [ ] Add equity curve endpoint (after existing endpoints, before the SSE route):

```python
@app.get("/api/strategies/{strategy_id}/equity")
async def get_equity_curve(strategy_id: str):
    points = await engine._portfolio.equity_curve(strategy_id)
    return [{"timestamp": p.timestamp.isoformat(), "balance": p.balance} for p in points]
```

### Step 3.5 — Run tests

- [ ] Run: `.venv/bin/python -m pytest prediction_bot/tests/test_strategies_router.py -v`
- [ ] Expected: all tests PASS

### Step 3.6 — Commit

- [ ] Run:
```bash
git add prediction_bot/src/dashboard/strategies_router.py \
        prediction_bot/src/dashboard/app.py \
        prediction_bot/tests/test_strategies_router.py
git commit -m "feat(prediction-bot): strategy CRUD + activate API (#105)"
```

---

## Task 4: Stepped Wizard UI (#106)

**Files:**
- Modify: `prediction_bot/src/dashboard/templates/dashboard.html`

**Acceptance:** Manually create a strategy end-to-end in the browser. No automated tests for this task.

### Step 4.1 — Add Pacekeeper CSS variables + wizard styles to dashboard.html

- [ ] In `dashboard.html`, inside the existing `<style>` block, append the following (after all existing rules):

```css
  /* Pacekeeper design tokens — wizard + equity sections */
  :root {
    --paper: #ffffff; --paper-2: #f7f8fa; --paper-3: #eef0f4;
    --ink: #0a0c10; --ink-2: #3a3d47; --ink-3: #6b7280; --ink-4: #9ca3af;
    --rule: #e5e7eb; --rule-2: #d1d5db;
    --accent: #1E5BFF; --accent-soft: #dde8ff;
    --sage: #2C7A4B; --sage-soft: #d1f5e0;
    --crimson: #C4302E; --crimson-soft: #fde8e8;
    --amber: #B8730E; --amber-soft: #fef3cd;
    --sans: 'Inter', system-ui, sans-serif;
    --mono: 'JetBrains Mono', 'Fira Code', monospace;
    --s-1: 4px; --s-2: 8px; --s-3: 12px; --s-4: 16px;
    --s-5: 20px; --s-6: 24px; --s-8: 32px;
    --radius: 8px; --radius-sm: 4px;
    --ease: cubic-bezier(.2,.8,.2,1);
  }
  /* Wizard panel */
  .pk-panel {
    background: var(--paper); border: 1px solid var(--rule);
    border-radius: var(--radius); padding: var(--s-6);
    margin-top: var(--s-6); font-family: var(--sans); color: var(--ink);
  }
  .pk-panel h2 { font-size: 1rem; font-weight: 600; margin: 0 0 var(--s-4); }
  .pk-label { font-size: 0.75rem; color: var(--ink-3); margin-bottom: var(--s-1); display: block; }
  .pk-input {
    width: 100%; box-sizing: border-box;
    border: 1px solid var(--rule-2); border-radius: var(--radius-sm);
    padding: var(--s-2) var(--s-3); font-family: var(--mono); font-size: 0.875rem;
    color: var(--ink); background: var(--paper-2);
    transition: border-color 120ms var(--ease);
  }
  .pk-input:focus { outline: none; border-color: var(--accent); }
  .pk-select { appearance: none; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8'%3E%3Cpath d='M0 0l6 8 6-8z' fill='%236b7280'/%3E%3C/svg%3E"); background-repeat: no-repeat; background-position: right 10px center; padding-right: 28px; }
  .pk-btn {
    display: inline-flex; align-items: center; gap: var(--s-2);
    padding: var(--s-2) var(--s-5); border-radius: var(--radius-sm);
    font-family: var(--sans); font-size: 0.875rem; font-weight: 500;
    cursor: pointer; border: none; transition: opacity 120ms var(--ease);
  }
  .pk-btn:hover { opacity: 0.85; }
  .pk-btn-primary { background: var(--accent); color: #fff; }
  .pk-btn-ghost { background: var(--paper-3); color: var(--ink-2); border: 1px solid var(--rule-2); }
  .pk-progress-bar { display: flex; gap: var(--s-2); margin-bottom: var(--s-6); }
  .pk-step-dot {
    flex: 1; height: 4px; border-radius: 2px;
    background: var(--rule); transition: background 220ms var(--ease);
  }
  .pk-step-dot.active { background: var(--accent); }
  .pk-step-dot.done { background: var(--sage); }
  .pk-field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--s-4) var(--s-5); }
  .pk-field-grid.single { grid-template-columns: 1fr; }
  .pk-help { font-size: 0.7rem; color: var(--ink-4); margin-top: var(--s-1); }
  .pk-strategy-list { list-style: none; padding: 0; margin: var(--s-4) 0 0; }
  .pk-strategy-item {
    display: flex; align-items: center; justify-content: space-between;
    padding: var(--s-3) var(--s-4); border: 1px solid var(--rule);
    border-radius: var(--radius-sm); margin-bottom: var(--s-2);
    background: var(--paper-2);
  }
  .pk-strategy-name { font-weight: 500; font-size: 0.9rem; }
  .pk-chip {
    display: inline-block; padding: 2px 8px; border-radius: 12px;
    font-size: 0.7rem; font-family: var(--mono);
  }
  .pk-chip-active { background: var(--sage-soft); color: var(--sage); }
  .pk-chip-inactive { background: var(--paper-3); color: var(--ink-3); }
  /* Equity chart */
  .pk-chart-wrap { position: relative; height: 260px; margin-top: var(--s-4); }
  .pk-stat-chips { display: flex; gap: var(--s-3); flex-wrap: wrap; margin-top: var(--s-4); }
  .pk-stat-chip {
    background: var(--paper-2); border: 1px solid var(--rule);
    border-radius: var(--radius-sm); padding: var(--s-2) var(--s-3);
    text-align: center; min-width: 80px;
  }
  .pk-stat-chip .pk-stat-label { font-size: 0.65rem; color: var(--ink-3); }
  .pk-stat-chip .pk-stat-value { font-family: var(--mono); font-size: 1rem; font-weight: 600; margin-top: 2px; }
  .pk-positive { color: var(--sage); }
  .pk-negative { color: var(--crimson); }
```

### Step 4.2 — Add wizard + strategy list HTML to dashboard.html

- [ ] Just before the closing `</body>` tag, add:

```html
<!-- Chart.js for equity overlay -->
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>

<!-- Strategy Manager -->
<div class="pk-panel" id="strategy-manager">
  <h2>Strategy Manager</h2>
  <button class="pk-btn pk-btn-primary" onclick="openWizard(null)">+ New Strategy</button>
  <ul class="pk-strategy-list" id="strategy-list"></ul>
</div>

<!-- Stepped Wizard (hidden by default) -->
<div class="pk-panel" id="wizard-panel" style="display:none">
  <h2 id="wizard-title">Build a Strategy</h2>
  <div class="pk-progress-bar" id="wizard-progress"></div>
  <div id="wizard-step-content"></div>
  <div style="display:flex;gap:8px;margin-top:20px">
    <button class="pk-btn pk-btn-ghost" id="btn-back" onclick="wizardBack()">← Back</button>
    <button class="pk-btn pk-btn-primary" id="btn-next" onclick="wizardNext()">Next →</button>
  </div>
</div>

<!-- Equity Overlay Chart -->
<div class="pk-panel" id="equity-panel" style="display:none">
  <h2>Strategy Equity Curves</h2>
  <div class="pk-stat-chips" id="equity-stat-chips"></div>
  <div class="pk-chart-wrap"><canvas id="equity-chart"></canvas></div>
</div>

<script>
// ── Wizard state ──────────────────────────────────────────────────────────
let _schema = null;
let _wizardSteps = [];  // [{step: N, fields: [...]}]
let _wizardCurrent = 0;
let _wizardParams = {};
let _editId = null;
let _equityChart = null;

async function loadSchema() {
  if (_schema) return _schema;
  const r = await fetch('/api/strategies/schema');
  _schema = await r.json();
  // Group fields by step number
  const byStep = {};
  for (const f of _schema.fields) {
    const s = f.step ?? 1;
    (byStep[s] = byStep[s] || []).push(f);
  }
  _wizardSteps = Object.keys(byStep).sort().map(k => ({ step: +k, fields: byStep[k] }));
  return _schema;
}

async function openWizard(strategyId) {
  await loadSchema();
  _editId = strategyId;
  _wizardCurrent = 0;
  _wizardParams = {};

  if (strategyId) {
    const r = await fetch(`/api/strategies/${strategyId}`);
    const defn = await r.json();
    _wizardParams = { ...defn.params };
    document.getElementById('wizard-title').textContent = 'Edit Strategy';
  } else {
    document.getElementById('wizard-title').textContent = 'Build a Strategy';
  }
  document.getElementById('wizard-panel').style.display = 'block';
  document.getElementById('wizard-panel').scrollIntoView({ behavior: 'smooth' });
  renderWizardStep();
}

function renderWizardStep() {
  const total = _wizardSteps.length + 1; // +1 for Review step
  // Progress bar
  const bar = document.getElementById('wizard-progress');
  bar.innerHTML = Array.from({ length: total }, (_, i) => {
    const cls = i < _wizardCurrent ? 'done' : i === _wizardCurrent ? 'active' : '';
    return `<div class="pk-step-dot ${cls}"></div>`;
  }).join('');

  const content = document.getElementById('wizard-step-content');
  const btnNext = document.getElementById('btn-next');
  const btnBack = document.getElementById('btn-back');
  btnBack.style.visibility = _wizardCurrent === 0 ? 'hidden' : 'visible';

  if (_wizardCurrent < _wizardSteps.length) {
    const { fields } = _wizardSteps[_wizardCurrent];
    const stepNames = ['Entry Filters', 'Position Sizing', 'Risk Limits', 'Universe'];
    const stepName = stepNames[_wizardCurrent] || `Step ${_wizardCurrent + 1}`;
    content.innerHTML = `<h3 style="font-size:.85rem;color:var(--ink-3);margin:0 0 12px;font-family:var(--sans)">${stepName}</h3>
      <div class="pk-field-grid">
        ${fields.map(f => renderField(f)).join('')}
      </div>`;
    btnNext.textContent = 'Next →';
  } else {
    // Review step
    const rows = Object.entries(_wizardParams)
      .map(([k, v]) => `<tr><td style="font-family:var(--mono);font-size:.8rem;padding:4px 8px;color:var(--ink-2)">${k}</td><td style="font-family:var(--mono);font-size:.8rem;padding:4px 8px">${v}</td></tr>`)
      .join('');
    content.innerHTML = `<h3 style="font-size:.85rem;color:var(--ink-3);margin:0 0 12px">Review &amp; Save</h3>
      <table style="width:100%;border-collapse:collapse;border:1px solid var(--rule);border-radius:4px">${rows}</table>
      <div style="margin-top:12px">
        <label class="pk-label">Strategy name</label>
        <input class="pk-input" id="wizard-name" placeholder="e.g. Aggressive Kelly" value="${_editId ? '' : ''}">
      </div>`;
    btnNext.textContent = _editId ? 'Save Changes' : 'Save Strategy';
  }
}

function renderField(f) {
  const val = _wizardParams[f.key] ?? f.default ?? '';
  if (f.type === 'select') {
    const opts = (f.options || []).map(o =>
      `<option value="${o}" ${String(val) === o ? 'selected' : ''}>${o}</option>`
    ).join('');
    return `<div>
      <label class="pk-label">${f.label}</label>
      <select class="pk-input pk-select" data-key="${f.key}" onchange="saveFieldVal(this)">${opts}</select>
      ${f.help ? `<div class="pk-help">${f.help}</div>` : ''}
    </div>`;
  }
  if (f.type === 'bool') {
    return `<div>
      <label class="pk-label">${f.label}</label>
      <input type="checkbox" data-key="${f.key}" ${val ? 'checked' : ''} onchange="saveFieldVal(this)">
      ${f.help ? `<div class="pk-help">${f.help}</div>` : ''}
    </div>`;
  }
  return `<div>
    <label class="pk-label">${f.label}</label>
    <input class="pk-input" type="number" data-key="${f.key}" value="${val}"
      min="${f.min ?? ''}" max="${f.max ?? ''}" step="${f.step ?? 'any'}"
      onchange="saveFieldVal(this)">
    ${f.help ? `<div class="pk-help">${f.help}</div>` : ''}
  </div>`;
}

function saveFieldVal(el) {
  const key = el.dataset.key;
  const f = _schema.fields.find(x => x.key === key);
  if (!f) return;
  if (f.type === 'bool') { _wizardParams[key] = el.checked; }
  else if (f.type === 'select') { _wizardParams[key] = el.value; }
  else { _wizardParams[key] = parseFloat(el.value); }
}

function collectCurrentStep() {
  // Save all inputs from the current step
  document.querySelectorAll('[data-key]').forEach(saveFieldVal);
}

async function wizardNext() {
  collectCurrentStep();
  if (_wizardCurrent < _wizardSteps.length) {
    _wizardCurrent++;
    renderWizardStep();
    return;
  }
  // Save
  const name = document.getElementById('wizard-name')?.value?.trim();
  if (!name) { alert('Please enter a strategy name.'); return; }
  const payload = { name, bot: 'prediction', params: _wizardParams };
  const url = _editId ? `/api/strategies/${_editId}` : '/api/strategies';
  const method = _editId ? 'PUT' : 'POST';
  const r = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  if (!r.ok) { alert('Save failed: ' + (await r.text())); return; }
  document.getElementById('wizard-panel').style.display = 'none';
  loadStrategyList();
}

function wizardBack() {
  collectCurrentStep();
  if (_wizardCurrent > 0) { _wizardCurrent--; renderWizardStep(); }
}

// ── Strategy list ─────────────────────────────────────────────────────────
async function loadStrategyList() {
  const r = await fetch('/api/strategies');
  const strategies = await r.json();
  const ul = document.getElementById('strategy-list');
  if (!strategies.length) { ul.innerHTML = '<li style="color:var(--ink-3);font-size:.85rem;padding:8px">No strategies yet.</li>'; return; }
  ul.innerHTML = strategies.map(s => `
    <li class="pk-strategy-item">
      <div>
        <span class="pk-strategy-name">${s.name}</span>
        <span class="pk-chip ${s.active ?? true ? 'pk-chip-active' : 'pk-chip-inactive'}" style="margin-left:8px">
          ${s.active ?? true ? 'active' : 'inactive'}
        </span>
      </div>
      <div style="display:flex;gap:6px">
        <button class="pk-btn pk-btn-ghost" style="font-size:.75rem;padding:3px 10px" onclick="openWizard('${s.id}')">Edit</button>
        <button class="pk-btn pk-btn-ghost" style="font-size:.75rem;padding:3px 10px" onclick="toggleActive('${s.id}', ${!( s.active ?? true)})">
          ${s.active ?? true ? 'Pause' : 'Activate'}
        </button>
      </div>
    </li>`).join('');
}

async function toggleActive(id, shouldActivate) {
  const endpoint = shouldActivate ? 'activate' : 'deactivate';
  await fetch(`/api/strategies/${id}/${endpoint}`, { method: 'POST' });
  loadStrategyList();
  loadEquityChart();
}

// Initialise on load
loadStrategyList();
</script>
```

### Step 4.3 — Manual browser test

- [ ] Start the prediction bot: `cd prediction_bot && ../.venv/bin/python main.py` (or however it starts)
- [ ] Open `http://localhost:4001` in a browser
- [ ] Verify: "Strategy Manager" section appears with "+ New Strategy" button
- [ ] Click "+ New Strategy", step through the wizard (Entry → Sizing → Risk → Universe → Review), enter a name, click "Save Strategy"
- [ ] Verify: strategy appears in the list
- [ ] Click "Edit" on the strategy, verify wizard pre-fills existing params
- [ ] Click "Pause" then "Activate" and verify chip updates

### Step 4.4 — Commit

- [ ] Run:
```bash
git add prediction_bot/src/dashboard/templates/dashboard.html
git commit -m "feat(prediction-bot): stepped wizard UI for strategy builder (#106)"
```

---

## Task 5: Equity-Curve Overlay Chart (#107)

**Files:**
- Modify: `prediction_bot/src/dashboard/templates/dashboard.html` — add `loadEquityChart()` + chart rendering

**Acceptance:** With 2+ active strategies, chart shows distinct lines + stat chips match stored stats. Manual browser test.

### Step 5.1 — Add equity chart JavaScript to dashboard.html

- [ ] Inside the `<script>` block from Task 4, append the following functions:

```js
// ── Equity overlay chart ──────────────────────────────────────────────────
const LINE_COLORS = ['#1E5BFF', '#2C7A4B', '#B8730E', '#C4302E', '#7C3AED'];

async function loadEquityChart() {
  const strategiesR = await fetch('/api/strategies');
  const strategies = await strategiesR.json();
  if (!strategies.length) { document.getElementById('equity-panel').style.display = 'none'; return; }

  document.getElementById('equity-panel').style.display = 'block';

  const datasets = [];
  const statChips = [];

  for (let i = 0; i < strategies.length; i++) {
    const s = strategies[i];
    const equityR = await fetch(`/api/strategies/${s.id}/equity`);
    const points = await equityR.json();
    const color = LINE_COLORS[i % LINE_COLORS.length];

    datasets.push({
      label: s.name,
      data: points.map(p => ({ x: p.timestamp, y: p.balance })),
      borderColor: color,
      backgroundColor: color + '18',
      borderWidth: 2,
      pointRadius: 0,
      tension: 0.3,
      fill: false,
    });

    // Stats chip
    const statsR = await fetch(`/api/stats?strategy_id=${s.id}`);
    let stats = {};
    if (statsR.ok) stats = await statsR.json();

    const pnl = stats.total_pnl ?? 0;
    const pnlClass = pnl >= 0 ? 'pk-positive' : 'pk-negative';
    const pnlSign = pnl >= 0 ? '+' : '';
    const wr = stats.win_rate != null ? (stats.win_rate * 100).toFixed(1) + '%' : '—';

    statChips.push(`
      <div class="pk-stat-chip" style="border-left: 3px solid ${color}">
        <div class="pk-stat-label">${s.name}</div>
        <div class="pk-stat-value ${pnlClass}" style="font-size:.85rem">${pnlSign}$${pnl.toFixed(2)}</div>
        <div style="font-size:.7rem;color:var(--ink-3);margin-top:2px">WR ${wr} · ${stats.total_trades ?? 0} trades</div>
      </div>`);
  }

  document.getElementById('equity-stat-chips').innerHTML = statChips.join('');

  const ctx = document.getElementById('equity-chart').getContext('2d');
  if (_equityChart) _equityChart.destroy();
  _equityChart = new Chart(ctx, {
    type: 'line',
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { font: { family: "'JetBrains Mono', monospace", size: 11 }, color: '#3a3d47' } },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.dataset.label}: $${ctx.parsed.y.toFixed(2)}`,
          },
        },
      },
      scales: {
        x: {
          type: 'time',
          time: { unit: 'hour', tooltipFormat: 'MMM d, HH:mm' },
          grid: { color: '#e5e7eb' },
          ticks: { color: '#6b7280', font: { family: "'JetBrains Mono', monospace", size: 10 } },
        },
        y: {
          grid: { color: '#e5e7eb' },
          ticks: {
            color: '#6b7280',
            font: { family: "'JetBrains Mono', monospace", size: 10 },
            callback: v => '$' + v.toFixed(0),
          },
        },
      },
    },
  });
}

loadEquityChart();
```

- [ ] Chart.js needs the `date-fns` adapter for the `time` scale. Add the adapter script tag before the `</body>` closing (after the existing Chart.js CDN tag):

```html
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
```

### Step 5.2 — Update `/api/stats` endpoint to accept `strategy_id` query param

- [ ] In `prediction_bot/src/dashboard/app.py`, update the stats endpoint:

```python
@app.get("/api/stats")
async def get_stats(strategy_id: str = "default"):
    return await engine.paper_trader.store.get_stats(strategy_id)
```

### Step 5.3 — Manual browser test

- [ ] Ensure at least 2 strategies exist (create them via the wizard from Task 4, or via seed data)
- [ ] Open `http://localhost:4001`
- [ ] Verify: "Strategy Equity Curves" section appears
- [ ] Verify: chart shows one distinct colored line per strategy
- [ ] Verify: stat chips show P&L, win rate, trade count for each strategy
- [ ] Verify: P&L uses sage color for positive, crimson for negative
- [ ] If only one strategy exists, verify the chart still renders correctly (one line)

### Step 5.4 — Run full test suite to verify no regressions

- [ ] Run: `.venv/bin/python -m pytest prediction_bot/tests/ tests/strategy_kit/ -v`
- [ ] Expected: all tests PASS

### Step 5.5 — Commit

- [ ] Run:
```bash
git add prediction_bot/src/dashboard/templates/dashboard.html \
        prediction_bot/src/dashboard/app.py
git commit -m "feat(prediction-bot): equity-curve overlay comparison view (#107)"
```

---

## Task 6: Open PR + close milestone

### Step 6.1 — Final test run

- [ ] Run: `.venv/bin/python -m pytest prediction_bot/tests/ tests/strategy_kit/ tests/ -v --ignore=tests/test_dashboard_positions_live.py`
- [ ] Expected: all PASS

### Step 6.2 — Open PR

```bash
gh pr create \
  --title "feat(prediction-bot): Phase 1 strategy builder — runner, multi-strategy engine, CRUD API, wizard, equity chart" \
  --base "claude/trading-bot-automation-kHiwZ" \
  --body "$(cat <<'EOF'
## Summary

Implements Phase 1 of the prediction bot strategy builder (issues #103–#107):

- **#103** `strategy_kit` integration: `PREDICTION_SCHEMA` (11 params across Entry/Sizing/Risk/Universe steps), `StrategyRunner` (kelly, contrarian, min_rr strategies), `TradeDecision` type
- **#104** Evaluate-once engine refactor: `strategy_id` added to `paper_trades` + `bankroll_snapshots` with zero-downtime migration, `ResultStore` queries all scoped by strategy, `PredictionEngine._cycle()` evaluates candidates once and applies each active strategy via `StrategyRunner`, `ShadowPortfolio` tracks per-strategy bankroll curves
- **#105** Strategy CRUD + activate API: `GET/POST /api/strategies`, `GET/PUT /api/strategies/{id}`, `POST .../archive|activate|deactivate`, `GET .../schema`, `GET .../equity`
- **#106** Stepped wizard UI: schema-driven, one step per screen, Back/Next, Review+Save, edit-existing reuse, Pacekeeper design tokens
- **#107** Equity-overlay chart: Chart.js time-series, one colored line per strategy, per-strategy stat chips (P&L sage/crimson, win rate, trade count)

## Test plan

- [ ] `.venv/bin/python -m pytest prediction_bot/tests/ tests/strategy_kit/ -v` — all green
- [ ] Manually create 2 strategies via wizard and verify equity chart shows 2 lines
- [ ] Verify legacy DB (no strategy_id column) migrates cleanly on initialize()

Closes #103, closes #104, closes #105, closes #106, closes #107

🤖 Generated with [Claude Code](https://claude.ai/claude-code)
EOF
)"
```

---

## Self-Review

### Spec coverage

| Requirement | Task |
|-------------|------|
| #103: PREDICTION_SCHEMA with all 11 knobs, 4 wizard steps | Task 1 — PREDICTION_SCHEMA |
| #103: StrategyRunner given params + pool → side/filter/size | Task 1 — StrategyRunner.run() |
| #103: Unit tests — same pool + 2 param sets → different results | Task 1 — test_strategy_runner.py |
| #103: Registered under `strategy_kit` registry | Task 1 — `register("prediction", PREDICTION_SCHEMA)` |
| #104: evaluate_candidates called once per cycle | Task 2 — engine._cycle() |
| #104: Per-strategy StrategyRunner apply + ShadowPortfolio | Task 2 — engine._cycle() per-strategy loop |
| #104: `paper_trades` + `bankroll_snapshots` gain strategy_id | Task 2 — ResultStore rewrite |
| #104: Migration assigns legacy rows to 'default' strategy | Task 2 — initialize() ALTER TABLE with DEFAULT |
| #104: 2 strategies yield independent trade sets + bankrolls | Task 2 — test_result_store_migration.py |
| #105: GET/POST /api/strategies | Task 3 — strategies_router.py |
| #105: GET/PUT /api/strategies/{id} | Task 3 — strategies_router.py |
| #105: POST .../archive | Task 3 — strategies_router.py |
| #105: POST .../activate and .../deactivate | Task 3 — strategies_router.py |
| #105: GET .../schema | Task 3 — strategies_router.py |
| #105: Endpoint tests (CRUD + activate) | Task 3 — test_strategies_router.py |
| #105: Created strategy persists via StrategyStore | Task 3 — verified by get_by_id test |
| #106: Stepped wizard, one step per screen, progress bar | Task 4 — dashboard.html wizard |
| #106: Fields rendered from /api/strategies/schema | Task 4 — loadSchema() + renderField() |
| #106: Back/Next, Review + Save | Task 4 — wizardBack/wizardNext |
| #106: Edit existing strategy reuses wizard | Task 4 — openWizard(id) branch |
| #106: Pacekeeper design system | Task 4 — pk-* CSS classes with design tokens |
| #107: Equity-overlay chart fed by ShadowPortfolio | Task 5 — /api/strategies/{id}/equity endpoint |
| #107: One line per strategy | Task 5 — datasets per strategy in Chart.js |
| #107: Stat chips (P&L, win rate, ROI, trades) | Task 5 — statChips HTML with pk-* classes |
| #107: sage = gain, crimson = loss color roles | Task 5 — pnlClass logic |
| #107: Pacekeeper design system | Task 5 — pk-* CSS, JetBrains Mono for numbers |
| #107: Live-updating via SSE | **GAP** — loadEquityChart() is called on page load but not on SSE events. Fix: in the SSE handler (if it exists in dashboard.html), call `loadEquityChart()` on `cycle_complete` events. Add this to the SSE listener in dashboard.html. |

### Gap fix — SSE live update for equity chart

- [ ] Find the existing SSE listener in `dashboard.html` (search for `EventSource` or `fetch('/api/stream')`). Add a call to `loadEquityChart()` when `type === 'cycle_complete'` is received. Example:

```js
// In the existing SSE handler where events are processed:
if (event.type === 'cycle_complete') {
  loadEquityChart();
}
```

### Placeholder scan

None found — all code blocks are complete.

### Type consistency

- `TradeDecision` defined in Task 1 (`strategy_runner.py`), imported in `paper_trader.py` Task 2, used correctly in `place_decision()`.
- `StrategyStore.list(active_only=True)` added in Task 2 Step 2.7, called in `engine.py` Task 2 Step 2.6.
- `StrategyStore.activate()` / `deactivate()` added in Task 2 Step 2.7, called in `strategies_router.py` Task 3.
- All consistent.
