"""Tests for ResultStore (aiosqlite)."""
import pytest
from datetime import datetime, timezone

from prediction_bot.src.api.models import PaperTrade


def _trade(**kwargs) -> PaperTrade:
    defaults = dict(
        platform="polymarket",
        market_id="m1",
        market_question="Will BTC stay above $80k?",
        category="crypto",
        side="YES",
        entry_price=0.92,
        quantity=10.0,
        cost=9.2,
        confidence=0.85,
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    return PaperTrade(**defaults)


@pytest.fixture
async def store(tmp_path):
    from prediction_bot.src.data.result_store import ResultStore
    s = ResultStore(str(tmp_path / "test.db"))
    await s.initialize()
    return s


class TestResultStore:
    async def test_creates_tables(self, tmp_path):
        """initialize() creates paper_trades and bankroll_snapshots tables."""
        import aiosqlite
        from prediction_bot.src.data.result_store import ResultStore

        db_path = str(tmp_path / "test.db")
        s = ResultStore(db_path)
        await s.initialize()

        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT name FROM sqlite_master WHERE type='table'") as cur:
                tables = {row[0] async for row in cur}
        assert "paper_trades" in tables
        assert "bankroll_snapshots" in tables

    async def test_add_and_fetch_trade(self, store):
        """add_trade returns ID; get_open_trades returns the trade."""
        trade_id = await store.add_trade(_trade(), initial_bankroll=1000.0)
        assert isinstance(trade_id, int)

        open_trades = await store.get_open_trades()
        assert len(open_trades) == 1
        assert open_trades[0].market_id == "m1"

    async def test_settle_trade_won(self, store):
        """settle_trade(won=True): pnl = (1-entry)*qty, status=WON."""
        trade_id = await store.add_trade(_trade(entry_price=0.92, quantity=10.0), initial_bankroll=1000.0)
        await store.settle_trade(trade_id, won=True)

        trades = await store.get_recent_trades()
        t = trades[0]
        assert t.status == "WON"
        assert abs(t.pnl - (1.0 - 0.92) * 10.0) < 0.001

    async def test_settle_trade_lost(self, store):
        """settle_trade(won=False): pnl = -entry*qty, status=LOST."""
        trade_id = await store.add_trade(_trade(entry_price=0.92, quantity=10.0), initial_bankroll=1000.0)
        await store.settle_trade(trade_id, won=False)

        trades = await store.get_recent_trades()
        t = trades[0]
        assert t.status == "LOST"
        assert abs(t.pnl - (-0.92 * 10.0)) < 0.001

    async def test_get_stats_win_rate(self, store):
        """get_stats computes win_rate correctly."""
        t1 = await store.add_trade(_trade(market_id="m1", cost=9.2), initial_bankroll=1000.0)
        t2 = await store.add_trade(_trade(market_id="m2", cost=9.2), initial_bankroll=1000.0)
        await store.settle_trade(t1, won=True)
        await store.settle_trade(t2, won=False)

        stats = await store.get_stats()
        assert stats["total_trades"] == 2
        assert stats["won"] == 1
        assert stats["lost"] == 1
        assert abs(stats["win_rate"] - 0.5) < 0.001

    async def test_get_bankroll_decreases_after_trade(self, store):
        """Bankroll decremented by trade cost after add_trade."""
        await store.add_trade(_trade(cost=9.2), initial_bankroll=1000.0)
        bankroll = await store.get_bankroll()
        assert abs(bankroll - (1000.0 - 9.2)) < 0.001
