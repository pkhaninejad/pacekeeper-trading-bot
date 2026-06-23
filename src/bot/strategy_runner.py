"""Stock bot StrategyRunner + STOCK_SCHEMA — issue #108.

Mirrors the prediction bot's StrategyRunner: a saved strategy's params are
applied to an already-generated Claude signal set. Rather than reimplementing
risk logic, the runner configures a ``RiskManager`` from the strategy's params
and reuses its proven ``validate`` / ``check_stop_loss`` / ``check_take_profit``.
"""
from __future__ import annotations

from src.api.models import CashInfo, Position, TradeSignal
from src.bot.risk_manager import RiskManager
from strategy_kit import ParamField, ParamSchema, register

# Model ids the wizard offers for the strategy's Claude model.
_MODEL_OPTIONS = [
    "claude-sonnet-4-6",
    "claude-opus-4-8",
    "claude-haiku-4-5-20251001",
]

_G_ENTRY = "Entry filters"
_G_SIZING = "Sizing"
_G_EXITS = "Exits"
_G_UNIVERSE = "AI & universe"

STOCK_SCHEMA = ParamSchema(fields=[
    ParamField(key="MIN_CONFIDENCE", label="Min confidence", type="percent", group=_G_ENTRY,
               default=0.60, min=0.0, max=1.0, step=0.01,
               help="Reject Claude signals below this confidence."),
    ParamField(key="WATCHLIST", label="Watchlist (comma-separated)", type="text", group=_G_ENTRY,
               default="AAPL,TSLA,NVDA,MSFT,AMZN,GOOGL,META,NFLX,AMD,JPM,V,UBER,PLTR",
               help="Tickers the bot may trade."),
    ParamField(key="MAX_POSITION_SIZE_PCT", label="Max position size", type="percent", group=_G_SIZING,
               default=0.05, min=0.01, max=1.0, step=0.01,
               help="Max fraction of portfolio per trade."),
    ParamField(key="MAX_OPEN_POSITIONS", label="Max open positions", type="number", group=_G_SIZING,
               default=10.0, min=1.0, max=100.0, step=1.0,
               help="Maximum number of simultaneously open positions."),
    ParamField(key="VIRTUAL_BANKROLL", label="Shadow bankroll ($)", type="number", group=_G_SIZING,
               default=10_000.0, min=100.0, max=10_000_000.0, step=100.0,
               help="Starting virtual bankroll when this strategy runs as a paper shadow."),
    ParamField(key="STOP_LOSS_PCT", label="Stop loss", type="percent", group=_G_EXITS,
               default=0.02, min=0.005, max=0.50, step=0.005,
               help="Close a position once it falls this far against entry."),
    ParamField(key="TAKE_PROFIT_PCT", label="Take profit", type="percent", group=_G_EXITS,
               default=0.04, min=0.005, max=1.0, step=0.005,
               help="Close a position once it gains this far from entry."),
    ParamField(key="CLAUDE_MODEL", label="Claude model", type="select", group=_G_UNIVERSE,
               default="claude-sonnet-4-6", options=_MODEL_OPTIONS,
               help="Which Claude model generates signals for this strategy."),
    ParamField(key="ENABLE_SCREENER", label="Enable dynamic screener", type="bool", group=_G_UNIVERSE,
               default=False,
               help="Let the bot add screener-discovered tickers beyond the watchlist."),
    ParamField(key="MAX_SCREENER_ADDITIONS", label="Max screener additions", type="number", group=_G_UNIVERSE,
               default=3.0, min=0.0, max=25.0, step=1.0,
               help="Cap on tickers the screener may add per cycle."),
    ParamField(key="BLOCK_NEW_POSITIONS_ON_EARNINGS", label="Block around earnings", type="bool", group=_G_UNIVERSE,
               default=True,
               help="Skip opening positions inside a ticker's earnings window."),
    ParamField(key="BLOCK_NEW_POSITIONS_ON_MACRO", label="Block around macro events", type="bool", group=_G_UNIVERSE,
               default=True,
               help="Skip opening positions near high-impact macro events."),
])

register("stock", STOCK_SCHEMA)


def settings_to_stock_params(s) -> dict:
    """Map the global Settings object to a STOCK_SCHEMA param dict (for the
    auto-created Default strategy)."""
    return {
        "MIN_CONFIDENCE": 0.60,
        "WATCHLIST": ",".join(s.WATCHLIST),
        "MAX_POSITION_SIZE_PCT": s.MAX_POSITION_SIZE_PCT,
        "MAX_OPEN_POSITIONS": float(s.MAX_OPEN_POSITIONS),
        "VIRTUAL_BANKROLL": 10_000.0,
        "STOP_LOSS_PCT": s.STOP_LOSS_PCT,
        "TAKE_PROFIT_PCT": s.TAKE_PROFIT_PCT,
        "CLAUDE_MODEL": s.CLAUDE_MODEL,
        "ENABLE_SCREENER": s.ENABLE_SCREENER,
        "MAX_SCREENER_ADDITIONS": float(s.MAX_SCREENER_ADDITIONS),
        "BLOCK_NEW_POSITIONS_ON_EARNINGS": s.BLOCK_NEW_POSITIONS_ON_EARNINGS,
        "BLOCK_NEW_POSITIONS_ON_MACRO": s.BLOCK_NEW_POSITIONS_ON_MACRO,
    }


class StockStrategyRunner:
    """Apply a saved strategy's params to a Claude-generated signal set."""

    def __init__(self, params: dict):
        # Keep a reference so post-construction mutations are visible.
        self._raw_params = params

    @property
    def params(self) -> dict:
        return STOCK_SCHEMA.fill_defaults(self._raw_params)

    def _risk_manager(self) -> RiskManager:
        p = self.params
        rm = RiskManager()
        rm.max_position_pct = float(p["MAX_POSITION_SIZE_PCT"])
        rm.max_open_positions = int(p["MAX_OPEN_POSITIONS"])
        rm.stop_loss_pct = float(p["STOP_LOSS_PCT"])
        rm.take_profit_pct = float(p["TAKE_PROFIT_PCT"])
        rm.min_confidence = float(p["MIN_CONFIDENCE"])
        return rm

    def run(
        self,
        signals: list[TradeSignal],
        positions: list[Position],
        cash: CashInfo,
    ) -> list[TradeSignal]:
        """Return the subset of signals this strategy approves (sized in place)."""
        rm = self._risk_manager()
        watchlist = {t.strip().upper() for t in str(self.params["WATCHLIST"]).split(",") if t.strip()}

        working = list(positions)
        approved: list[TradeSignal] = []
        for sig in signals:
            is_open = sig.direction != "CLOSE"
            if is_open and watchlist and rm._normalize_ticker(sig.ticker) not in watchlist:
                continue
            ok, _reason = rm.validate(sig, working, cash)
            if not ok:
                continue
            approved.append(sig)
            # Reflect a new open so batch max-positions / dedupe stay correct.
            if is_open and sig.action == "BUY" and sig.suggested_quantity and sig.suggested_price:
                working.append(Position(
                    ticker=sig.ticker,
                    quantity=sig.suggested_quantity,
                    averagePrice=sig.suggested_price,
                    currentPrice=sig.suggested_price,
                    ppl=0.0,
                ))
        return approved

    def manage_exits(self, positions: list[Position]) -> list[Position]:
        """Return positions this strategy would close on stop-loss / take-profit."""
        rm = self._risk_manager()
        return [p for p in positions if rm.check_stop_loss(p) or rm.check_take_profit(p)]
