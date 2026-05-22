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
