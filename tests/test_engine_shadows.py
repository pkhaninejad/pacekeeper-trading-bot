"""Engine-level tests for LIVE designation + parallel shadows — issue #109."""
from datetime import datetime

import pytest

from src.api.models import TradeSignal
from src.bot.engine import TradingEngine
from src.bot.live_designation import LiveDesignation
from strategy_kit import StrategyDefinition
from strategy_kit.portfolio import ShadowPortfolio
from strategy_kit.store import StrategyStore


def _signal(ticker="AAPL", confidence=0.9, qty=10.0, price=100.0):
    return TradeSignal(
        ticker=ticker, action="BUY", direction="LONG", confidence=confidence,
        reasoning="t", suggested_quantity=qty, suggested_price=price,
        order_type="MARKET", timestamp=datetime.now(),
    )


@pytest.fixture
async def engine(tmp_path, monkeypatch):
    eng = TradingEngine()
    db = str(tmp_path / "stock.db")
    eng._strategy_store = StrategyStore(db)
    eng._portfolio = ShadowPortfolio(db)
    eng._live_designation = LiveDesignation(tmp_path / "live.json")
    await eng._strategy_store.initialize()
    await eng._portfolio.initialize()
    # No network during shadow valuation.
    monkeypatch.setattr("src.bot.engine.get_price_summary", lambda tickers: {})
    return eng


async def test_only_live_trades_real_rest_shadow(engine):
    live = StrategyDefinition(name="Live", bot="stock",
                              params={"MIN_CONFIDENCE": 0.5, "MAX_POSITION_SIZE_PCT": 0.10})
    shadow_a = StrategyDefinition(name="ShadowA", bot="stock",
                                  params={"MIN_CONFIDENCE": 0.5, "MAX_POSITION_SIZE_PCT": 0.10})
    shadow_b = StrategyDefinition(name="ShadowB", bot="stock",
                                  params={"MIN_CONFIDENCE": 0.99})  # rejects the 0.9 signal
    engine._active_strategies = [live, shadow_a, shadow_b]
    for s in engine._active_strategies:
        await engine._portfolio.seed_bankroll(s.id, 10_000.0)
    engine._live_designation.designate(live.id, env="demo", live_confirmed=False)

    assert engine._real_trading_strategy().id == live.id

    await engine._run_shadow_strategies([_signal("AAPL")], exclude_id=live.id)

    # LIVE strategy trades real → excluded from the shadow book entirely.
    assert engine._shadow_holdings.get(live.id, {}) == {}
    # ShadowA opened a virtual AAPL position.
    assert "AAPL" in engine._shadow_holdings[shadow_a.id]
    balance = (await engine._portfolio.equity_curve(shadow_a.id))[-1].balance
    assert balance == pytest.approx(10_000.0 - 1_000.0)
    # ShadowB rejected the signal on its stricter confidence gate.
    assert engine._shadow_holdings.get(shadow_b.id, {}) == {}


async def test_no_designation_means_no_real_strategy(engine):
    s = StrategyDefinition(name="A", bot="stock", params={})
    engine._active_strategies = [s]
    await engine._portfolio.seed_bankroll(s.id, 10_000.0)
    assert engine._real_trading_strategy() is None


async def test_init_strategies_creates_default_and_designates(engine):
    await engine._init_strategies()
    assert len(engine._active_strategies) == 1
    assert engine._active_strategies[0].name == "Default"
    # In demo, the Default strategy is auto-designated LIVE.
    assert engine._real_trading_strategy() is not None
