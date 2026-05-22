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
