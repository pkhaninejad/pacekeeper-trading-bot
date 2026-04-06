"""
Risk management: validates signals before execution, enforces limits.
"""

import logging
from src.config.settings import settings
from src.api.models import TradeSignal, Position, CashInfo
from src.data.earnings_calendar import EarningsInfo

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
    ) -> tuple[bool, str]:
        """
        Returns (approved, reason).
        """
        # Confidence gate
        if signal.confidence < self.min_confidence:
            return False, f"Confidence {signal.confidence:.2f} below threshold {self.min_confidence}"

        # Earnings window gate (only blocks new position opens, not CLOSE)
        is_close = signal.direction == "CLOSE"
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

        # Max open positions gate (only for new positions)
        position_tickers = {p.ticker for p in positions}
        is_new = signal.ticker not in position_tickers

        if is_new and not is_close and len(positions) >= self.max_open_positions:
            return False, f"Max open positions ({self.max_open_positions}) reached"

        # Cash availability (for buys / shorts)
        if signal.action == "BUY" and signal.suggested_quantity and signal.suggested_price:
            required = signal.suggested_quantity * signal.suggested_price
            if required > cash.free:
                return False, f"Insufficient cash: need {required:.2f}, have {cash.free:.2f}"

        # Position size limit
        if signal.suggested_quantity and signal.suggested_price:
            trade_value = abs(signal.suggested_quantity) * signal.suggested_price
            max_allowed = cash.total * self.max_position_pct
            if trade_value > max_allowed:
                # Auto-scale down
                signal.suggested_quantity = (max_allowed / signal.suggested_price) * (
                    1 if signal.suggested_quantity > 0 else -1
                )
                logger.info(
                    "Scaled position size for %s to %.4f (max %.2f)",
                    signal.ticker, signal.suggested_quantity, max_allowed,
                )

        # Don't double up same direction
        existing = next((p for p in positions if p.ticker == signal.ticker), None)
        if existing and not is_close:
            if signal.direction == "LONG" and existing.is_long:
                return False, f"Already long {signal.ticker}"
            if signal.direction == "SHORT" and existing.is_short:
                return False, f"Already short {signal.ticker}"

        return True, "Approved"

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
