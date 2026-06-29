"""Tests for PaperTrader."""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock

from prediction_bot.src.api.models import PredictionMarket, MarketCandidate
from prediction_bot.src.config.settings import PredictionBotSettings


def _candidate(market_id="m1", yes_price=0.92, category="crypto", platform="polymarket"):
    return MarketCandidate(
        market=PredictionMarket(
            id=market_id,
            platform=platform,
            question=f"Test question {market_id}?",
            category=category,
            end_date=datetime.now(timezone.utc) + timedelta(hours=20),
            yes_price=yes_price,
            no_price=round(1 - yes_price, 2),
            liquidity=50000,
        ),
        best_side="YES",
        market_price=yes_price,
        llm_true_prob=0.97,
        llm_confidence=0.85,
        llm_reasoning="Strong signal",
        edge=0.03,
    )


@pytest.fixture
async def trader(tmp_path):
    from prediction_bot.src.data.result_store import ResultStore
    from prediction_bot.src.bot.paper_trader import PaperTrader

    settings = PredictionBotSettings(
        VIRTUAL_BANKROLL=1000.0,
        MAX_POSITION_PCT=0.10,
        MAX_OPEN_POSITIONS=5,
    )
    store = ResultStore(str(tmp_path / "test.db"))
    pt = PaperTrader(store=store, settings=settings)
    await pt.initialize()
    return pt


class TestPaperTrader:
    async def test_place_trade_success(self, trader):
        """Trade placed, bankroll deducted."""
        c = _candidate()
        trade = await trader.place_paper_trade(c)
        assert trade is not None
        assert trade.side == "YES"
        assert trade.entry_price == 0.92
        bankroll = await trader.store.get_bankroll()
        assert bankroll < 1000.0

    async def test_quantity_calculation(self, trader):
        """Quantity = floor(bankroll * MAX_POSITION_PCT / entry_price)."""
        c = _candidate(yes_price=0.92)
        trade = await trader.place_paper_trade(c)
        assert trade.quantity == int(100.0 / 0.92)

    async def test_place_trade_duplicate_market_rejected(self, trader):
        """Second trade for same market_id is rejected."""
        c = _candidate(market_id="dup")
        trade1 = await trader.place_paper_trade(c)
        trade2 = await trader.place_paper_trade(c)
        assert trade1 is not None
        assert trade2 is None

    async def test_place_trade_max_positions_rejected(self, trader):
        """Trade rejected when open positions at MAX_OPEN_POSITIONS."""
        for i in range(5):
            await trader.place_paper_trade(_candidate(market_id=f"m{i}"))
        extra = await trader.place_paper_trade(_candidate(market_id="extra"))
        assert extra is None

    async def test_settle_open_trades_won(self, trader):
        """Winning settlement updates bankroll and status."""
        c = _candidate()
        await trader.place_paper_trade(c)
        bankroll_before = await trader.store.get_bankroll()

        poly_mock = AsyncMock()
        poly_mock.get_market_status = AsyncMock(return_value={"resolved": True, "winner": "YES"})

        await trader.settle_open_trades({"polymarket": poly_mock})

        bankroll_after = await trader.store.get_bankroll()
        assert bankroll_after > bankroll_before
        open_trades = await trader.store.get_open_trades()
        assert len(open_trades) == 0


@pytest.fixture
async def kelly_trader(tmp_path):
    from prediction_bot.src.data.result_store import ResultStore
    from prediction_bot.src.bot.paper_trader import PaperTrader

    settings = PredictionBotSettings(
        VIRTUAL_BANKROLL=1000.0,
        MAX_POSITION_PCT=0.10,
        MAX_OPEN_POSITIONS=5,
        BET_STRATEGY="kelly",
    )
    store = ResultStore(str(tmp_path / "kelly_test.db"))
    pt = PaperTrader(store=store, settings=settings)
    await pt.initialize()
    return pt


class TestKellySizing:
    async def test_kelly_sizes_by_edge(self, kelly_trader):
        """Kelly allocation is capped at MAX_POSITION_PCT when edge is large."""
        # confidence=0.85, entry=0.70 → kelly = (0.85-0.70)/(1-0.70) = 0.5
        # allocation = min(0.5 * 1000, 0.10 * 1000) = 100.0 (capped)
        c = _candidate(yes_price=0.70)
        c = c.model_copy(update={"llm_confidence": 0.85})
        trade = await kelly_trader.place_paper_trade(c)
        assert trade is not None
        assert abs(trade.cost - 100.0) < 1.0

    async def test_kelly_skips_no_edge(self, kelly_trader):
        """Kelly skips trade when llm_confidence <= entry_price."""
        # confidence=0.85, entry=0.90 → kelly = (0.85-0.90)/(1-0.90) = -0.5 → skip
        c = _candidate(yes_price=0.90)
        c = c.model_copy(update={"llm_confidence": 0.85})
        trade = await kelly_trader.place_paper_trade(c)
        assert trade is None

    async def test_kelly_small_edge_small_bet(self, kelly_trader):
        """Kelly allocates less than MAX_POSITION_PCT when edge is small."""
        # confidence=0.805, entry=0.80 → kelly = (0.805-0.80)/(1-0.80) = 0.025
        # allocation = 0.025 * 1000 = 25.0, below the 100.0 cap
        c = _candidate(yes_price=0.80)
        c = c.model_copy(update={"llm_confidence": 0.805})
        trade = await kelly_trader.place_paper_trade(c)
        assert trade is not None
        assert trade.cost < 100.0
