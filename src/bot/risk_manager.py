"""
Risk management: validates signals before execution, enforces limits.
"""

import logging
from src.config.settings import settings
from src.api.models import TradeSignal, Position, CashInfo, RegimeResult
from src.data.earnings_calendar import EarningsInfo
from src.data.macro_calendar import MacroEvent

logger = logging.getLogger(__name__)


class RiskManager:
    def __init__(self):
        self.max_position_pct = settings.MAX_POSITION_SIZE_PCT
        self.max_open_positions = settings.MAX_OPEN_POSITIONS
        self.stop_loss_pct = settings.STOP_LOSS_PCT
        self.take_profit_pct = settings.TAKE_PROFIT_PCT
        self.min_confidence = 0.6

    def validate(
        self,
        signal: TradeSignal,
        positions: list[Position],
        cash: CashInfo,
        earnings_info: dict[str, "EarningsInfo"] | None = None,
        macro_events: list["MacroEvent"] | None = None,
        regime: "RegimeResult | None" = None,
    ) -> tuple[bool, str]:
        """
        Returns (approved, reason).
        """
        normalized_ticker = self._normalize_ticker(signal.ticker)

        # Confidence gate
        if signal.confidence < self.min_confidence:
            return False, f"Confidence {signal.confidence:.2f} below threshold {self.min_confidence}"

        is_close = signal.direction == "CLOSE"

        # Macro calendar gate (only blocks new position opens, not CLOSE)
        if (
            not is_close
            and settings.BLOCK_NEW_POSITIONS_ON_MACRO
            and macro_events
        ):
            blocking = [e for e in macro_events if e.hours_until <= settings.MACRO_BLOCK_HOURS]
            if blocking:
                names = ", ".join(e.event for e in blocking[:3])
                return False, f"Macro event block: {names} within {settings.MACRO_BLOCK_HOURS}h — no new positions"

        # Earnings window gate (only blocks new position opens, not CLOSE)
        if (
            not is_close
            and settings.BLOCK_NEW_POSITIONS_ON_EARNINGS
            and earnings_info is not None
        ):
            info = earnings_info.get(signal.ticker)
            if info is not None and info.in_window:
                days = info.days_until
                direction = "in" if days is not None and days >= 0 else "ago"
                count = abs(days) if days is not None else "?"
                return False, (
                    f"Earnings window blocked: {signal.ticker} earnings "
                    f"{count} day(s) {direction} — no new positions allowed"
                )

        # EXTREME_FEAR gate — block all new positions (multiplier=0.0)
        if regime and regime.position_size_multiplier == 0.0 and not is_close:
            return False, f"EXTREME_FEAR regime (VIX={regime.vix:.1f}) — no new positions allowed"

        # Equity accounts on Trading212 do not support opening short positions.
        if signal.direction == "SHORT":
            return False, f"Short selling is not supported for {normalized_ticker}"

        # Max open positions gate (only for new positions)
        existing = self._find_position(positions, signal.ticker)
        is_new = existing is None

        if is_new and not is_close and len(positions) >= self.max_open_positions:
            return False, f"Max open positions ({self.max_open_positions}) reached"

        # Cash availability (for buys / shorts)
        if signal.action == "BUY" and signal.suggested_quantity and signal.suggested_price:
            required = signal.suggested_quantity * signal.suggested_price
            if required > cash.free:
                return False, f"Insufficient cash: need {required:.2f}, have {cash.free:.2f}"

        # Position size limit (regime multiplier applied here)
        if signal.suggested_quantity and signal.suggested_price:
            trade_value = abs(signal.suggested_quantity) * signal.suggested_price
            multiplier = regime.position_size_multiplier if (regime and not is_close) else 1.0
            max_allowed = cash.total * self.max_position_pct * multiplier
            if trade_value > max_allowed:
                signal.suggested_quantity = (max_allowed / signal.suggested_price) * (
                    1 if signal.suggested_quantity > 0 else -1
                )
                logger.info(
                    "Scaled position size for %s to %.4f (max %.2f, regime=%s)",
                    signal.ticker, signal.suggested_quantity, max_allowed,
                    regime.regime if regime else "none",
                )

        # Don't double up same direction; also block SELL with no position
        if signal.action == "SELL" and existing is None and not is_close:
            return False, f"No open position to sell for {signal.ticker}"

        if existing and not is_close:
            if signal.direction == "LONG" and existing.is_long:
                return False, f"Already long {signal.ticker}"
            if signal.direction == "SHORT" and existing.is_short:
                return False, f"Already short {signal.ticker}"

        return True, "Approved"

    @staticmethod
    def _normalize_ticker(ticker: str) -> str:
        return ticker.split("_")[0]

    def _find_position(self, positions: list[Position], ticker: str) -> Position | None:
        normalized = self._normalize_ticker(ticker)
        return next(
            (p for p in positions if p.ticker == ticker or self._normalize_ticker(p.ticker) == normalized),
            None,
        )

    def compute_quantity(
        self,
        signal: TradeSignal,
        cash: CashInfo,
        current_price: float,
    ) -> float:
        """Compute a safe position size based on portfolio percentage."""
        max_value = cash.total * self.max_position_pct
        qty = max_value / current_price
        if signal.direction == "SHORT":
            qty = -qty
        return round(qty, 4)

    def check_stop_loss(self, position: Position) -> bool:
        """Returns True if position should be closed due to stop-loss."""
        if position.is_long:
            loss_pct = (position.averagePrice - position.currentPrice) / position.averagePrice
        else:
            loss_pct = (position.currentPrice - position.averagePrice) / position.averagePrice
        return loss_pct >= self.stop_loss_pct

    def check_take_profit(self, position: Position) -> bool:
        """Returns True if position should be closed due to take-profit."""
        if position.is_long:
            gain_pct = (position.currentPrice - position.averagePrice) / position.averagePrice
        else:
            gain_pct = (position.averagePrice - position.currentPrice) / position.averagePrice
        return gain_pct >= self.take_profit_pct
