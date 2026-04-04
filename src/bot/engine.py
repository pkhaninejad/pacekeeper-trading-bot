"""
Main trading engine — orchestrates strategy, risk management, and order execution.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from src.api.client import Trading212Client
from src.api.models import (
    MarketOrderRequest, LimitOrderRequest, StopOrderRequest,
    TradeSignal, BotStatus, Position,
)
from src.bot.strategy import ClaudeStrategy
from src.bot.risk_manager import RiskManager
from src.config.settings import settings

logger = logging.getLogger(__name__)


class TradingEngine:
    def __init__(self):
        self.strategy = ClaudeStrategy()
        self.risk = RiskManager()
        self.status = BotStatus(
            enabled=settings.BOT_ENABLED,
            environment=settings.T212_ENV,
        )
        self._running = False
        self._signals_history: list[TradeSignal] = []
        self._trade_log: list[dict] = []

    # -------------------------------------------------------------------------
    # Public controls
    # -------------------------------------------------------------------------

    async def start(self):
        """Start the bot loop."""
        self._running = True
        logger.info("Trading engine started (env=%s)", settings.T212_ENV)
        while self._running:
            try:
                await self._cycle()
            except Exception as e:
                logger.error("Engine cycle error: %s", e, exc_info=True)
            self.status.next_run = datetime.utcnow().replace(
                second=0, microsecond=0
            )
            await asyncio.sleep(settings.TRADE_INTERVAL_SECONDS)

    def stop(self):
        self._running = False
        self.status.enabled = False
        logger.info("Trading engine stopped")

    def toggle(self) -> bool:
        self.status.enabled = not self.status.enabled
        if not self.status.enabled:
            self.stop()
        return self.status.enabled

    @property
    def signals_history(self) -> list[TradeSignal]:
        return self._signals_history[-100:]

    @property
    def trade_log(self) -> list[dict]:
        return self._trade_log[-200:]

    # -------------------------------------------------------------------------
    # Core cycle
    # -------------------------------------------------------------------------

    async def _cycle(self):
        if not self.status.enabled:
            return

        logger.info("=== Trading cycle started ===")
        self.status.last_run = datetime.utcnow()

        async with Trading212Client() as client:
            # Fetch market state
            cash = await client.get_cash()
            positions = await client.get_positions()
            instruments = await client.get_instruments()

            self.status.open_positions = len(positions)
            self.status.total_pnl = cash.ppl

            # 1. Check stop-loss / take-profit on existing positions
            await self._manage_exits(client, positions)

            # Refresh positions after exits
            positions = await client.get_positions()

            # 2. Generate new signals via Claude
            signals = self.strategy.generate_signals(
                positions, cash, settings.WATCHLIST, instruments
            )
            self.status.signals_generated += len(signals)
            self._signals_history.extend(signals)

            # 3. Execute approved signals
            for signal in signals:
                approved, reason = self.risk.validate(signal, positions, cash)
                if not approved:
                    logger.info("Signal rejected [%s]: %s", signal.ticker, reason)
                    continue
                await self._execute_signal(client, signal, cash, positions)

        logger.info("=== Trading cycle complete ===")

    async def _manage_exits(self, client: Trading212Client, positions: list[Position]):
        """Auto-close positions that hit stop-loss or take-profit."""
        for pos in positions:
            should_exit = False
            exit_reason = ""

            if self.risk.check_stop_loss(pos):
                should_exit = True
                exit_reason = "stop-loss"
            elif self.risk.check_take_profit(pos):
                should_exit = True
                exit_reason = "take-profit"

            if should_exit:
                logger.info("Closing %s position in %s: %s",
                           "LONG" if pos.is_long else "SHORT", pos.ticker, exit_reason)
                close_qty = -pos.quantity  # opposite to close
                req = MarketOrderRequest(ticker=pos.ticker, quantity=close_qty)
                try:
                    order = await client.place_market_order(req)
                    self._log_trade({
                        "action": "CLOSE",
                        "ticker": pos.ticker,
                        "quantity": close_qty,
                        "reason": exit_reason,
                        "order_id": order.id,
                        "timestamp": datetime.utcnow().isoformat(),
                    })
                    self.status.total_trades_today += 1
                except Exception as e:
                    logger.error("Failed to close %s: %s", pos.ticker, e)

    async def _execute_signal(
        self,
        client: Trading212Client,
        signal: TradeSignal,
        cash,
        positions: list[Position],
    ):
        """Place order based on signal."""
        # Determine quantity
        if signal.direction == "CLOSE":
            existing = next((p for p in positions if p.ticker == signal.ticker), None)
            if not existing:
                return
            quantity = -existing.quantity
        elif signal.suggested_quantity:
            quantity = signal.suggested_quantity
        else:
            price = signal.suggested_price or 100.0  # fallback
            quantity = self.risk.compute_quantity(signal, cash, price)

        logger.info(
            "Executing %s %s %s qty=%.4f confidence=%.2f",
            signal.order_type, signal.action, signal.ticker, quantity, signal.confidence,
        )

        try:
            order = None
            if signal.order_type == "MARKET":
                order = await client.place_market_order(
                    MarketOrderRequest(ticker=signal.ticker, quantity=quantity)
                )
            elif signal.order_type == "LIMIT" and signal.suggested_price:
                order = await client.place_limit_order(
                    LimitOrderRequest(
                        ticker=signal.ticker,
                        quantity=quantity,
                        limitPrice=signal.suggested_price,
                    )
                )
            elif signal.order_type == "STOP" and signal.suggested_price:
                order = await client.place_stop_order(
                    StopOrderRequest(
                        ticker=signal.ticker,
                        quantity=quantity,
                        stopPrice=signal.suggested_price,
                    )
                )

            if order:
                self.status.total_trades_today += 1
                self._log_trade({
                    "action": signal.action,
                    "direction": signal.direction,
                    "ticker": signal.ticker,
                    "quantity": quantity,
                    "order_type": signal.order_type,
                    "confidence": signal.confidence,
                    "reasoning": signal.reasoning,
                    "order_id": order.id,
                    "timestamp": datetime.utcnow().isoformat(),
                })

        except Exception as e:
            logger.error("Order execution failed for %s: %s", signal.ticker, e)

    def _log_trade(self, entry: dict):
        self._trade_log.append(entry)
        logger.info("Trade logged: %s", entry)
