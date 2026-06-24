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

    def test_returns_empty_when_bankroll_is_zero(self):
        params = PREDICTION_SCHEMA.fill_defaults({})
        runner = StrategyRunner(params)
        decisions = runner.run([_candidate("m1", edge=0.05)], bankroll=0, open_market_ids=set())
        assert decisions == []


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

    def test_contrarian_flips_entry_price(self):
        """Contrarian: entry_price on the decision should be 1 - original yes_price."""
        params = PREDICTION_SCHEMA.fill_defaults({"BET_STRATEGY": "contrarian"})
        runner = StrategyRunner(params)
        c = _candidate("m1", yes_price=0.90, best_side="YES", edge=0.05)
        decisions = runner.run([c], 1000.0, set())
        assert len(decisions) == 1
        assert decisions[0].candidate.market_price == pytest.approx(round(1.0 - 0.90, 8))

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
