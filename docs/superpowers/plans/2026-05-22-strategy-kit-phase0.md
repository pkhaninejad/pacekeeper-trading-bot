# Strategy Kit Phase 0 — Shared Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `strategy_kit/` shared package (GitHub issues #100, #101, #102) — a bot-agnostic foundation for defining, persisting, and shadow-running named strategies across both bots.

**Architecture:** Three independent subsystems layered in dependency order: (1) `models.py` + `registry.py` define the domain types with no I/O, (2) `store.py` persists strategy definitions via aiosqlite mirroring the existing `ResultStore` pattern, (3) `portfolio.py` provides per-strategy virtual bankrolls + equity curves. All live in a new top-level `strategy_kit/` package importable by both `src/` and `prediction_bot/`.

**Tech Stack:** Python 3.14, Pydantic v2, aiosqlite, pytest-asyncio (`asyncio_mode = "auto"`), pytest `tmp_path` fixture for DB isolation.

---

## File Map

| Path | Responsibility |
|------|---------------|
| `strategy_kit/__init__.py` | Public re-exports |
| `strategy_kit/models.py` | `StrategyDefinition`, `ParamField`, `ParamSchema` Pydantic models |
| `strategy_kit/registry.py` | Bot-schema registry (`register`, `get_schema`) |
| `strategy_kit/store.py` | `StrategyStore` — aiosqlite CRUD for strategy definitions |
| `strategy_kit/portfolio.py` | `ShadowPortfolio` — per-strategy bankroll, equity curve, stats |
| `tests/strategy_kit/__init__.py` | Package marker |
| `tests/strategy_kit/test_models.py` | Schema validation, default fill-in, registry round-trips |
| `tests/strategy_kit/test_store.py` | CRUD round-trips against `tmp_path` sqlite |
| `tests/strategy_kit/test_portfolio.py` | Independent bankrolls, equity curve, stats correctness |

---

## Task 1: Domain Models (`strategy_kit/models.py`)

**Files:**
- Create: `strategy_kit/__init__.py`
- Create: `strategy_kit/models.py`
- Create: `strategy_kit/registry.py`
- Create: `tests/strategy_kit/__init__.py`
- Create: `tests/strategy_kit/test_models.py`

### Step 1.1 — Write failing tests

- [ ] Create `tests/strategy_kit/__init__.py` (empty)
- [ ] Create `tests/strategy_kit/test_models.py`:

```python
"""Tests for strategy_kit models and registry."""
import pytest
from strategy_kit import ParamField, ParamSchema, StrategyDefinition, get_schema, register


class TestParamSchema:
    def test_fill_defaults_fills_missing_keys(self):
        schema = ParamSchema(fields=[
            ParamField(key="threshold", label="Threshold", type="number", default=0.6),
            ParamField(key="side", label="Side", type="select", default="YES",
                       options=["YES", "NO"]),
        ])
        result = schema.fill_defaults({"threshold": 0.8})
        assert result == {"threshold": 0.8, "side": "YES"}

    def test_fill_defaults_empty_params(self):
        schema = ParamSchema(fields=[
            ParamField(key="k", label="K", type="number", default=1.5),
        ])
        result = schema.fill_defaults({})
        assert result == {"k": 1.5}

    def test_validate_params_rejects_below_min(self):
        schema = ParamSchema(fields=[
            ParamField(key="conf", label="Confidence", type="percent", default=0.6,
                       min=0.0, max=1.0),
        ])
        with pytest.raises(ValueError, match="conf"):
            schema.validate_params({"conf": -0.1})

    def test_validate_params_rejects_above_max(self):
        schema = ParamSchema(fields=[
            ParamField(key="conf", label="Confidence", type="percent", default=0.6,
                       min=0.0, max=1.0),
        ])
        with pytest.raises(ValueError, match="conf"):
            schema.validate_params({"conf": 1.5})

    def test_validate_params_rejects_invalid_select(self):
        schema = ParamSchema(fields=[
            ParamField(key="mode", label="Mode", type="select", default="a",
                       options=["a", "b"]),
        ])
        with pytest.raises(ValueError, match="mode"):
            schema.validate_params({"mode": "c"})

    def test_validate_params_accepts_valid_params(self):
        schema = ParamSchema(fields=[
            ParamField(key="n", label="N", type="number", default=5, min=1, max=10),
        ])
        schema.validate_params({"n": 7})  # must not raise

    def test_validate_params_skips_missing_keys(self):
        schema = ParamSchema(fields=[
            ParamField(key="n", label="N", type="number", default=5, min=1, max=10),
        ])
        schema.validate_params({})  # must not raise


class TestStrategyDefinition:
    def test_defaults_are_set(self):
        defn = StrategyDefinition(name="My Strategy", bot="prediction")
        assert defn.id != ""
        assert defn.archived is False
        assert defn.params == {}
        assert defn.created_at is not None

    def test_bot_must_be_valid_literal(self):
        with pytest.raises(Exception):
            StrategyDefinition(name="x", bot="invalid_bot")

    def test_accepts_stock_bot(self):
        defn = StrategyDefinition(name="x", bot="stock")
        assert defn.bot == "stock"


class TestRegistry:
    def test_register_and_get_schema(self):
        schema = ParamSchema(fields=[
            ParamField(key="x", label="X", type="number", default=1),
        ])
        register("test_bot", schema)
        retrieved = get_schema("test_bot")
        assert retrieved is schema

    def test_get_schema_raises_for_unknown_bot(self):
        with pytest.raises(KeyError, match="no_such_bot"):
            get_schema("no_such_bot")
```

### Step 1.2 — Run tests to verify they fail

- [ ] Run: `.venv/bin/python -m pytest tests/strategy_kit/test_models.py -v`
- [ ] Expected: `ModuleNotFoundError: No module named 'strategy_kit'`

### Step 1.3 — Implement `strategy_kit/models.py`

- [ ] Create `strategy_kit/models.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ParamField(BaseModel):
    key: str
    label: str
    type: Literal["number", "percent", "select", "bool", "text"]
    default: float | str | bool | None = None
    min: float | None = None
    max: float | None = None
    help: str = ""
    step: int = 1
    options: list[str] | None = None


class ParamSchema(BaseModel):
    fields: list[ParamField]

    def fill_defaults(self, params: dict) -> dict:
        result = {}
        for field in self.fields:
            result[field.key] = params.get(field.key, field.default)
        return result

    def validate_params(self, params: dict) -> None:
        for field in self.fields:
            if field.key not in params:
                continue
            val = params[field.key]
            if field.type in ("number", "percent"):
                if field.min is not None and val < field.min:
                    raise ValueError(f"{field.key}: {val} < min {field.min}")
                if field.max is not None and val > field.max:
                    raise ValueError(f"{field.key}: {val} > max {field.max}")
            if field.type == "select" and field.options and val not in field.options:
                raise ValueError(f"{field.key}: {val!r} not in {field.options}")


class StrategyDefinition(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    bot: Literal["prediction", "stock"]
    params: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    archived: bool = False
```

### Step 1.4 — Implement `strategy_kit/registry.py`

- [ ] Create `strategy_kit/registry.py`:

```python
from __future__ import annotations

from strategy_kit.models import ParamSchema

_registry: dict[str, ParamSchema] = {}


def register(bot: str, schema: ParamSchema) -> None:
    _registry[bot] = schema


def get_schema(bot: str) -> ParamSchema:
    if bot not in _registry:
        raise KeyError(f"No schema registered for bot: {bot!r}")
    return _registry[bot]
```

### Step 1.5 — Implement `strategy_kit/__init__.py`

- [ ] Create `strategy_kit/__init__.py`:

```python
from strategy_kit.models import ParamField, ParamSchema, StrategyDefinition
from strategy_kit.registry import get_schema, register

__all__ = ["StrategyDefinition", "ParamField", "ParamSchema", "register", "get_schema"]
```

### Step 1.6 — Run tests and verify they pass

- [ ] Run: `.venv/bin/python -m pytest tests/strategy_kit/test_models.py -v`
- [ ] Expected: all 10 tests PASS

### Step 1.7 — Commit

- [ ] Run:
```bash
git add strategy_kit/__init__.py strategy_kit/models.py strategy_kit/registry.py \
        tests/strategy_kit/__init__.py tests/strategy_kit/test_models.py
git commit -m "feat(strategy_kit): scaffold models, ParamSchema, and registry (#100)"
```

---

## Task 2: StrategyStore — aiosqlite CRUD (`strategy_kit/store.py`)

**Files:**
- Create: `strategy_kit/store.py`
- Create: `tests/strategy_kit/test_store.py`

### Step 2.1 — Write failing tests

- [ ] Create `tests/strategy_kit/test_store.py`:

```python
"""Tests for StrategyStore CRUD."""
import pytest
from strategy_kit.models import StrategyDefinition
from strategy_kit.store import StrategyStore


@pytest.fixture
async def store(tmp_path):
    s = StrategyStore(str(tmp_path / "strategies.db"))
    await s.initialize()
    return s


def _defn(**kwargs) -> StrategyDefinition:
    defaults = dict(name="My Strategy", bot="prediction", description="test")
    defaults.update(kwargs)
    return StrategyDefinition(**defaults)


class TestStrategyStore:
    async def test_initialize_is_idempotent(self, tmp_path):
        """initialize() can be called twice without error."""
        s = StrategyStore(str(tmp_path / "strategies.db"))
        await s.initialize()
        await s.initialize()  # must not raise

    async def test_create_and_get_round_trip(self, store):
        """create() + get() returns the same definition."""
        defn = _defn(name="Alpha", params={"threshold": 0.7})
        sid = await store.create(defn)
        result = await store.get(sid)
        assert result is not None
        assert result.name == "Alpha"
        assert result.params == {"threshold": 0.7}
        assert result.bot == "prediction"
        assert result.archived is False

    async def test_get_returns_none_for_unknown(self, store):
        """get() returns None if id doesn't exist."""
        result = await store.get("nonexistent-id")
        assert result is None

    async def test_list_filters_by_bot(self, store):
        """list(bot=) returns only strategies for that bot."""
        await store.create(_defn(name="P1", bot="prediction"))
        await store.create(_defn(name="S1", bot="stock"))
        await store.create(_defn(name="P2", bot="prediction"))

        prediction = await store.list("prediction")
        stock = await store.list("stock")

        assert len(prediction) == 2
        assert all(d.bot == "prediction" for d in prediction)
        assert len(stock) == 1

    async def test_list_excludes_archived_by_default(self, store):
        """list() hides archived strategies unless include_archived=True."""
        sid = (await store.create(_defn(name="To Archive", bot="prediction"))).split
        # create and archive
        defn = _defn(name="Active", bot="prediction")
        defn2 = _defn(name="Archived", bot="prediction")
        id1 = await store.create(defn)
        id2 = await store.create(defn2)
        await store.archive(id2)

        visible = await store.list("prediction")
        all_strategies = await store.list("prediction", include_archived=True)

        assert len(visible) == 1
        assert visible[0].id == id1
        assert len(all_strategies) == 2

    async def test_update_name_and_params(self, store):
        """update() persists new name and params."""
        defn = _defn(name="Old Name", params={"k": 1})
        sid = await store.create(defn)
        await store.update(sid, name="New Name", params={"k": 2, "j": 3})
        result = await store.get(sid)
        assert result.name == "New Name"
        assert result.params == {"k": 2, "j": 3}

    async def test_update_noop_when_no_fields(self, store):
        """update() with no kwargs doesn't error or change the record."""
        defn = _defn(name="Unchanged")
        sid = await store.create(defn)
        await store.update(sid)  # no-op, must not raise
        result = await store.get(sid)
        assert result.name == "Unchanged"

    async def test_archive_sets_archived_flag(self, store):
        """archive() sets archived=True and get() reflects it."""
        sid = await store.create(_defn(name="Soon Gone", bot="prediction"))
        await store.archive(sid)
        result = await store.get(sid)
        assert result.archived is True

    async def test_params_json_survives_round_trip(self, store):
        """Nested dict params are serialized/deserialized correctly."""
        params = {"nested": {"a": 1, "b": [1, 2, 3]}, "flag": True}
        sid = await store.create(_defn(params=params))
        result = await store.get(sid)
        assert result.params == params
```

### Step 2.2 — Run tests to verify they fail

- [ ] Run: `.venv/bin/python -m pytest tests/strategy_kit/test_store.py -v`
- [ ] Expected: `ImportError: cannot import name 'StrategyStore'`

### Step 2.3 — Implement `strategy_kit/store.py`

- [ ] Create `strategy_kit/store.py`:

```python
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import aiosqlite

from strategy_kit.models import StrategyDefinition

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS strategies (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    bot TEXT NOT NULL,
    params TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0
);
"""


class StrategyStore:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()

    async def create(self, definition: StrategyDefinition) -> str:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO strategies (id, name, description, bot, params, created_at, archived)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    definition.id,
                    definition.name,
                    definition.description,
                    definition.bot,
                    json.dumps(definition.params),
                    definition.created_at.isoformat(),
                    int(definition.archived),
                ),
            )
            await db.commit()
        return definition.id

    async def get(self, id: str) -> StrategyDefinition | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM strategies WHERE id = ?", (id,)
            ) as cur:
                row = await cur.fetchone()
        if row is None:
            return None
        return _row_to_definition(row)

    async def list(self, bot: str, include_archived: bool = False) -> list[StrategyDefinition]:
        query = "SELECT * FROM strategies WHERE bot = ?"
        args: list = [bot]
        if not include_archived:
            query += " AND archived = 0"
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, args) as cur:
                rows = await cur.fetchall()
        return [_row_to_definition(r) for r in rows]

    async def update(
        self,
        id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        params: dict | None = None,
    ) -> None:
        updates: list[str] = []
        vals: list = []
        if name is not None:
            updates.append("name = ?")
            vals.append(name)
        if description is not None:
            updates.append("description = ?")
            vals.append(description)
        if params is not None:
            updates.append("params = ?")
            vals.append(json.dumps(params))
        if not updates:
            return
        vals.append(id)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                f"UPDATE strategies SET {', '.join(updates)} WHERE id = ?", vals
            )
            await db.commit()

    async def archive(self, id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE strategies SET archived = 1 WHERE id = ?", (id,)
            )
            await db.commit()


def _row_to_definition(row: aiosqlite.Row) -> StrategyDefinition:
    return StrategyDefinition(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        bot=row["bot"],
        params=json.loads(row["params"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        archived=bool(row["archived"]),
    )
```

### Step 2.4 — Fix the test bug in test_store.py

The `test_list_excludes_archived_by_default` test has a bug (`sid.split` is nonsense — it came from incorrect scaffolding). Fix it before running:

- [ ] In `tests/strategy_kit/test_store.py`, replace `test_list_excludes_archived_by_default` body with:

```python
    async def test_list_excludes_archived_by_default(self, store):
        """list() hides archived strategies unless include_archived=True."""
        defn = _defn(name="Active", bot="prediction")
        defn2 = _defn(name="Archived", bot="prediction")
        id1 = await store.create(defn)
        id2 = await store.create(defn2)
        await store.archive(id2)

        visible = await store.list("prediction")
        all_strategies = await store.list("prediction", include_archived=True)

        assert len(visible) == 1
        assert visible[0].id == id1
        assert len(all_strategies) == 2
```

### Step 2.5 — Run tests and verify they pass

- [ ] Run: `.venv/bin/python -m pytest tests/strategy_kit/test_store.py -v`
- [ ] Expected: all 8 tests PASS

### Step 2.6 — Commit

- [ ] Run:
```bash
git add strategy_kit/store.py tests/strategy_kit/test_store.py
git commit -m "feat(strategy_kit): add StrategyStore aiosqlite CRUD (#101)"
```

---

## Task 3: ShadowPortfolio — per-strategy bankroll + equity curve + stats

**Files:**
- Create: `strategy_kit/portfolio.py`
- Create: `tests/strategy_kit/test_portfolio.py`

### Step 3.1 — Write failing tests

- [ ] Create `tests/strategy_kit/test_portfolio.py`:

```python
"""Tests for ShadowPortfolio."""
import pytest
from strategy_kit.portfolio import ShadowPortfolio


@pytest.fixture
async def portfolio(tmp_path):
    p = ShadowPortfolio(str(tmp_path / "shadow.db"))
    await p.initialize()
    return p


class TestShadowPortfolio:
    async def test_independent_bankrolls(self, portfolio):
        """Two strategies keep separate bankrolls after opening trades."""
        await portfolio.seed_bankroll("strat-A", 1000.0)
        await portfolio.seed_bankroll("strat-B", 500.0)

        await portfolio.open_trade("strat-A", "t1", entry_price=10.0, quantity=5.0)
        # strat-B untouched

        curve_a = await portfolio.equity_curve("strat-A")
        curve_b = await portfolio.equity_curve("strat-B")

        assert curve_a[-1].balance == pytest.approx(950.0)   # 1000 - (10*5)
        assert curve_b[-1].balance == pytest.approx(500.0)   # unchanged

    async def test_equity_curve_reflects_seed_then_trade(self, portfolio):
        """Equity curve has two points after seed + one trade."""
        await portfolio.seed_bankroll("strat-A", 1000.0)
        await portfolio.open_trade("strat-A", "t1", entry_price=20.0, quantity=3.0)

        curve = await portfolio.equity_curve("strat-A")
        assert len(curve) == 2
        assert curve[0].balance == pytest.approx(1000.0)
        assert curve[1].balance == pytest.approx(940.0)   # 1000 - 60

    async def test_close_trade_adds_equity_point(self, portfolio):
        """Closing a long winning trade restores cost + pnl to bankroll."""
        await portfolio.seed_bankroll("strat-A", 1000.0)
        tid = await portfolio.open_trade("strat-A", "t1", entry_price=10.0, quantity=5.0)
        # balance = 950 after open
        await portfolio.close_trade(tid, exit_price=12.0)
        # pnl = (12-10)*5 = 10; balance = 950 + 50 + 10 = 1010
        curve = await portfolio.equity_curve("strat-A")
        assert curve[-1].balance == pytest.approx(1010.0)

    async def test_close_losing_trade(self, portfolio):
        """Closing a losing long trade deducts loss from bankroll."""
        await portfolio.seed_bankroll("strat-A", 1000.0)
        tid = await portfolio.open_trade("strat-A", "t1", entry_price=10.0, quantity=5.0)
        # balance = 950
        await portfolio.close_trade(tid, exit_price=8.0)
        # pnl = (8-10)*5 = -10; balance = 950 + 50 - 10 = 990
        curve = await portfolio.equity_curve("strat-A")
        assert curve[-1].balance == pytest.approx(990.0)

    async def test_stats_win_rate(self, portfolio):
        """Stats win_rate = wins / settled."""
        await portfolio.seed_bankroll("strat-A", 1000.0)
        tid1 = await portfolio.open_trade("strat-A", "t1", entry_price=10.0, quantity=1.0)
        tid2 = await portfolio.open_trade("strat-A", "t2", entry_price=10.0, quantity=1.0)
        await portfolio.close_trade(tid1, exit_price=12.0)   # win: pnl=2
        await portfolio.close_trade(tid2, exit_price=8.0)    # loss: pnl=-2

        stats = await portfolio.stats("strat-A")
        assert stats.settled_count == 2
        assert stats.open_count == 0
        assert stats.win_rate == pytest.approx(0.5)
        assert stats.total_pnl == pytest.approx(0.0)

    async def test_stats_roi(self, portfolio):
        """ROI = total_pnl / initial_bankroll."""
        await portfolio.seed_bankroll("strat-A", 1000.0)
        tid = await portfolio.open_trade("strat-A", "t1", entry_price=100.0, quantity=1.0)
        await portfolio.close_trade(tid, exit_price=150.0)   # pnl = 50

        stats = await portfolio.stats("strat-A")
        assert stats.roi == pytest.approx(0.05)  # 50 / 1000

    async def test_stats_open_count(self, portfolio):
        """open_count reflects trades not yet closed."""
        await portfolio.seed_bankroll("strat-A", 1000.0)
        await portfolio.open_trade("strat-A", "t1", entry_price=10.0, quantity=1.0)
        await portfolio.open_trade("strat-A", "t2", entry_price=10.0, quantity=1.0)

        stats = await portfolio.stats("strat-A")
        assert stats.open_count == 2
        assert stats.settled_count == 0

    async def test_two_strategies_stats_independent(self, portfolio):
        """Stats for strat-B are not affected by strat-A's trades."""
        await portfolio.seed_bankroll("strat-A", 1000.0)
        await portfolio.seed_bankroll("strat-B", 1000.0)

        tid = await portfolio.open_trade("strat-A", "t1", entry_price=10.0, quantity=1.0)
        await portfolio.close_trade(tid, exit_price=20.0)

        stats_b = await portfolio.stats("strat-B")
        assert stats_b.total_pnl == pytest.approx(0.0)
        assert stats_b.settled_count == 0
        assert stats_b.open_count == 0

    async def test_open_trade_raises_if_no_bankroll_seeded(self, portfolio):
        """open_trade raises ValueError if bankroll was never seeded."""
        with pytest.raises(ValueError, match="strat-X"):
            await portfolio.open_trade("strat-X", "t1", entry_price=10.0, quantity=1.0)
```

### Step 3.2 — Run tests to verify they fail

- [ ] Run: `.venv/bin/python -m pytest tests/strategy_kit/test_portfolio.py -v`
- [ ] Expected: `ImportError: cannot import name 'ShadowPortfolio'`

### Step 3.3 — Implement `strategy_kit/portfolio.py`

- [ ] Create `strategy_kit/portfolio.py`:

```python
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import NamedTuple

import aiosqlite

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS shadow_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id TEXT NOT NULL,
    trade_ref TEXT NOT NULL,
    direction TEXT NOT NULL DEFAULT 'long',
    entry_price REAL NOT NULL,
    quantity REAL NOT NULL,
    cost REAL NOT NULL,
    exit_price REAL,
    pnl REAL,
    status TEXT NOT NULL DEFAULT 'open',
    opened_at TEXT NOT NULL,
    closed_at TEXT
);

CREATE TABLE IF NOT EXISTS shadow_equity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id TEXT NOT NULL,
    balance REAL NOT NULL,
    timestamp TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_shadow_strategy ON shadow_trades(strategy_id);
CREATE INDEX IF NOT EXISTS idx_shadow_equity_strategy ON shadow_equity(strategy_id);
"""


class EquityPoint(NamedTuple):
    timestamp: datetime
    balance: float


class StrategyStats(NamedTuple):
    total_pnl: float
    win_rate: float
    roi: float
    open_count: int
    settled_count: int


class ShadowPortfolio:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()

    async def seed_bankroll(self, strategy_id: str, initial_balance: float) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO shadow_equity (strategy_id, balance, timestamp) VALUES (?, ?, ?)",
                (strategy_id, initial_balance, datetime.now(UTC).isoformat()),
            )
            await db.commit()

    async def open_trade(
        self,
        strategy_id: str,
        trade_ref: str,
        entry_price: float,
        quantity: float,
        *,
        direction: str = "long",
    ) -> int:
        cost = entry_price * quantity
        async with aiosqlite.connect(self.db_path) as db:
            balance = await self._get_balance(db, strategy_id)
            cur = await db.execute(
                """INSERT INTO shadow_trades
                   (strategy_id, trade_ref, direction, entry_price, quantity, cost, opened_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    strategy_id, trade_ref, direction,
                    entry_price, quantity, cost,
                    datetime.now(UTC).isoformat(),
                ),
            )
            trade_id = cur.lastrowid
            await db.execute(
                "INSERT INTO shadow_equity (strategy_id, balance, timestamp) VALUES (?, ?, ?)",
                (strategy_id, balance - cost, datetime.now(UTC).isoformat()),
            )
            await db.commit()
        return trade_id

    async def close_trade(self, trade_id: int, exit_price: float) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT strategy_id, entry_price, quantity, direction FROM shadow_trades WHERE id = ?",
                (trade_id,),
            ) as cur:
                row = await cur.fetchone()
            if row is None:
                raise ValueError(f"trade {trade_id} not found")
            strategy_id = row["strategy_id"]
            entry_price = row["entry_price"]
            quantity = row["quantity"]
            direction = row["direction"]
            pnl = (
                (exit_price - entry_price) * quantity
                if direction == "long"
                else (entry_price - exit_price) * quantity
            )
            cost = entry_price * quantity
            balance = await self._get_balance(db, strategy_id)
            await db.execute(
                """UPDATE shadow_trades
                   SET exit_price = ?, pnl = ?, status = 'closed', closed_at = ?
                   WHERE id = ?""",
                (exit_price, pnl, datetime.now(UTC).isoformat(), trade_id),
            )
            await db.execute(
                "INSERT INTO shadow_equity (strategy_id, balance, timestamp) VALUES (?, ?, ?)",
                (strategy_id, balance + cost + pnl, datetime.now(UTC).isoformat()),
            )
            await db.commit()

    async def equity_curve(self, strategy_id: str) -> list[EquityPoint]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT timestamp, balance FROM shadow_equity WHERE strategy_id = ? ORDER BY id ASC",
                (strategy_id,),
            ) as cur:
                rows = await cur.fetchall()
        return [EquityPoint(datetime.fromisoformat(r[0]), r[1]) for r in rows]

    async def stats(self, strategy_id: str) -> StrategyStats:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT pnl, status FROM shadow_trades WHERE strategy_id = ?",
                (strategy_id,),
            ) as cur:
                rows = await cur.fetchall()
        total_pnl = 0.0
        wins = 0
        settled = 0
        open_count = 0
        for pnl, status in rows:
            if status == "open":
                open_count += 1
            else:
                settled += 1
                if pnl is not None:
                    total_pnl += pnl
                    if pnl > 0:
                        wins += 1
        win_rate = wins / settled if settled else 0.0
        curve = await self.equity_curve(strategy_id)
        initial = curve[0].balance if curve else 0.0
        roi = total_pnl / initial if initial else 0.0
        return StrategyStats(
            total_pnl=total_pnl,
            win_rate=win_rate,
            roi=roi,
            open_count=open_count,
            settled_count=settled,
        )

    async def _get_balance(self, db: aiosqlite.Connection, strategy_id: str) -> float:
        async with db.execute(
            "SELECT balance FROM shadow_equity WHERE strategy_id = ? ORDER BY id DESC LIMIT 1",
            (strategy_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            raise ValueError(f"No bankroll seeded for strategy {strategy_id!r}")
        return row[0]
```

### Step 3.4 — Run tests and verify they pass

- [ ] Run: `.venv/bin/python -m pytest tests/strategy_kit/test_portfolio.py -v`
- [ ] Expected: all 9 tests PASS

### Step 3.5 — Run full strategy_kit test suite

- [ ] Run: `.venv/bin/python -m pytest tests/strategy_kit/ -v`
- [ ] Expected: all tests PASS (models + store + portfolio)

### Step 3.6 — Commit

- [ ] Run:
```bash
git add strategy_kit/portfolio.py tests/strategy_kit/test_portfolio.py
git commit -m "feat(strategy_kit): add ShadowPortfolio bankroll, equity curve, stats (#102)"
```

---

## Task 4: Run full test suite + open PR

### Step 4.1 — Run complete test suite to verify no regressions

- [ ] Run: `.venv/bin/python -m pytest tests/ -v --ignore=tests/test_dashboard_positions_live.py`
- [ ] Expected: all tests PASS (strategy_kit tests + existing tests)

### Step 4.2 — Open PR

- [ ] Run:
```bash
gh pr create \
  --title "feat(strategy_kit): Phase 0 shared foundation — models, store, portfolio (#100 #101 #102)" \
  --base claude/trading-bot-automation-kHiwZ \
  --body "$(cat <<'EOF'
## Summary

- Scaffolds `strategy_kit/` top-level package importable by both `src/` and `prediction_bot/`
- `StrategyDefinition` + `ParamSchema` + `ParamField` Pydantic v2 models with validation and default fill-in
- Bot-schema registry (`register` / `get_schema`)
- `StrategyStore`: idempotent aiosqlite CRUD mirroring `ResultStore` style (create/get/list/update/archive)
- `ShadowPortfolio`: per-strategy virtual bankroll, equity-curve snapshots, and stats (P&L, win rate, ROI, open/settled counts)
- 27 tests covering all acceptance criteria in issues #100, #101, and #102

Closes #100, closes #101, closes #102

## Test plan

- [ ] `.venv/bin/python -m pytest tests/strategy_kit/ -v` — all green
- [ ] `.venv/bin/python -m pytest tests/ -v --ignore=tests/test_dashboard_positions_live.py` — no regressions

🤖 Generated with [Claude Code](https://claude.ai/claude-code)
EOF
)"
```

---

## Self-Review

**Spec coverage check:**

| Requirement | Task |
|-------------|------|
| #100: `strategy_kit/` package importable from repo root | Task 1 |
| #100: `StrategyDefinition` with all required fields | Task 1, Step 1.3 |
| #100: `ParamField` + `ParamSchema` with validation and registry | Task 1, Steps 1.3–1.5 |
| #100: Unit tests — schema validation, defaults, registry lookup | Task 1, Step 1.1 |
| #100: No bot imports inside strategy_kit | Ensured by design — models.py has zero bot imports |
| #101: `strategies` table with all required columns | Task 2, Step 2.3 |
| #101: `initialize/create/get/list/update/archive` methods | Task 2, Step 2.3 |
| #101: Mirrors ResultStore style (idempotent CREATE TABLE IF NOT EXISTS) | Task 2, Step 2.3 |
| #101: Unit tests — create/list/get/update/archive round-trips; params JSON survives | Task 2, Step 2.1 |
| #102: Per-strategy bankroll + trade ledger keyed by `strategy_id` | Task 3, Step 3.3 |
| #102: Equity-curve query `[(timestamp, balance)]` per strategy | Task 3 — `equity_curve()` returns `list[EquityPoint]` |
| #102: Stats: total P&L, win rate, ROI, open/settled counts | Task 3 — `StrategyStats` NamedTuple |
| #102: Generic over trade shape | Task 3 — stores primitive scalars only, no bot-specific types |
| #102: Unit tests — two strategies independent bankrolls; equity curve + stats correct | Task 3, Step 3.1 |

**Placeholder scan:** None found.

**Type consistency:** `StrategyDefinition` defined in Task 1 and imported in Task 2. `StrategyStore`, `ShadowPortfolio`, `EquityPoint`, `StrategyStats` defined once and used consistently in tests.
