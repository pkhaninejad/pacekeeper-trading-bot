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
               default=0.80, min=0.50, max=1.0, step=0.01,
               help="Only enter markets priced above this."),
    ParamField(key="HIGH_PROB_MAX", label="Max probability", type="percent",
               default=0.97, min=0.50, max=1.0, step=0.01,
               help="Skip markets priced above this (too certain)."),
    ParamField(key="MIN_EDGE_PCT", label="Min edge %", type="percent",
               default=0.02, min=0.0, max=0.50, step=0.01,
               help="Minimum edge after fees to trade."),
    ParamField(key="EXPIRY_WINDOW_HOURS", label="Expiry window (hours)", type="number",
               default=168.0, min=1.0, max=8760.0, step=1.0,
               help="Only consider markets expiring within this many hours."),
    # Step 2 — Sizing
    ParamField(key="BET_STRATEGY", label="Bet strategy", type="select",
               default="kelly", options=["kelly", "contrarian", "min_rr"],
               help="kelly = size by Kelly criterion; contrarian = bet opposite; min_rr = risk/reward filter."),
    ParamField(key="MAX_POSITION_PCT", label="Max position size", type="percent",
               default=0.10, min=0.01, max=0.50, step=0.01,
               help="Max fraction of bankroll per trade."),
    ParamField(key="VIRTUAL_BANKROLL", label="Starting bankroll ($)", type="number",
               default=1000.0, min=100.0, max=1_000_000.0, step=100.0,
               help="Virtual starting bankroll for this strategy."),
    # Step 3 — Risk
    ParamField(key="MIN_RR_RATIO", label="Min R:R ratio", type="number",
               default=2.0, min=0.5, max=10.0, step=0.5,
               help="min_rr strategy: skip unless potential gain / cost >= this ratio."),
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

# EXPIRY_WINDOW_HOURS and MIN_LIQUIDITY are enforced by scan_markets() upstream,
# not by StrategyRunner — they are schema fields for the wizard and engine config.
register("prediction", PREDICTION_SCHEMA)


# Ready-made starter strategies users can instantiate from the builder (#112).
PREDICTION_STARTERS = [
    {
        "name": "Safe Favorites",
        "description": "Back strong favorites with a small edge, Kelly-sized.",
        "params": {
            "HIGH_PROB_MIN": 0.85, "HIGH_PROB_MAX": 0.97, "MIN_EDGE_PCT": 0.02,
            "BET_STRATEGY": "kelly", "MAX_POSITION_PCT": 0.05,
        },
    },
    {
        "name": "Value Hunter",
        "description": "Only take trades with a strong risk/reward ratio.",
        "params": {
            "HIGH_PROB_MIN": 0.55, "HIGH_PROB_MAX": 0.90, "MIN_EDGE_PCT": 0.05,
            "BET_STRATEGY": "min_rr", "MIN_RR_RATIO": 2.5, "MAX_POSITION_PCT": 0.08,
        },
    },
    {
        "name": "Contrarian",
        "description": "Bet against the crowd on mispriced markets.",
        "params": {
            "HIGH_PROB_MIN": 0.60, "HIGH_PROB_MAX": 0.95, "MIN_EDGE_PCT": 0.04,
            "BET_STRATEGY": "contrarian", "MAX_POSITION_PCT": 0.05,
        },
    },
]


class StrategyRunner:
    """Apply a saved strategy's params to an already-evaluated candidate pool."""

    def __init__(self, params: dict):
        # Keep a reference to the caller's dict so post-construction mutations are visible.
        self._raw_params = params

    @property
    def params(self) -> dict:
        return PREDICTION_SCHEMA.fill_defaults(self._raw_params)

    def run(
        self,
        candidates: list[MarketCandidate],
        bankroll: float,
        open_market_ids: set[str],
    ) -> list[TradeDecision]:
        if bankroll <= 0:
            return []
        resolved = self.params
        categories = {c.strip() for c in resolved["ENABLED_CATEGORIES"].split(",") if c.strip()}
        high_min = float(resolved["HIGH_PROB_MIN"])
        high_max = float(resolved["HIGH_PROB_MAX"])
        min_edge = float(resolved["MIN_EDGE_PCT"])
        bet_strategy = resolved["BET_STRATEGY"]
        max_pos_pct = float(resolved["MAX_POSITION_PCT"])
        max_positions = int(resolved["MAX_OPEN_POSITIONS"])
        min_rr = float(resolved["MIN_RR_RATIO"])

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

            # Strategies are mutually exclusive; elif order matters — contrarian
            # updates entry_price before min_rr would read it.
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
