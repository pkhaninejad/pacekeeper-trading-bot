"""
Main trading engine — orchestrates strategy, risk management, and order execution.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Optional

from src.api.client import Trading212Client
from src.api.models import (
    MarketOrderRequest, LimitOrderRequest, StopOrderRequest,
    TradeSignal, BotStatus, Position, TradeOutcome,
)
from src.bot.strategy import ClaudeStrategy
from src.bot.risk_manager import RiskManager
from src.bot.market_hours import is_market_open, next_open
from src.data.earnings_calendar import EarningsCalendar
from src.data.news_feed import NewsFeed
from src.config.settings import settings

logger = logging.getLogger(__name__)


class TradingEngine:
    def __init__(self):
        self.strategy = ClaudeStrategy()
        self.risk = RiskManager()
        self.earnings = EarningsCalendar(
            days_before=settings.EARNINGS_DAYS_BEFORE,
            days_after=settings.EARNINGS_DAYS_AFTER,
            finnhub_api_key=settings.FINNHUB_API_KEY,
        )
        self.news = NewsFeed(
            lookback_days=settings.NEWS_LOOKBACK_DAYS,
            max_headlines=settings.NEWS_MAX_HEADLINES_PER_TICKER,
            cache_ttl=settings.NEWS_CACHE_TTL_SECONDS,
            finnhub_api_key=settings.FINNHUB_API_KEY,
            news_api_key=settings.NEWS_API_KEY,
        )
        self.status = BotStatus(
            enabled=settings.BOT_ENABLED,
            environment=settings.T212_ENV,
        )
        self._running = False
        self._signals_history: list[TradeSignal] = []
        self._trade_log: list[dict] = []
        self._instruments_cache: list = []
        self._pnl_history: list[dict] = []   # [{t, ppl, total, invested}]
        self._outcome_log: list[TradeOutcome] = []
        self._session_date: str = ""          # YYYY-MM-DD; resets history each new day
        # Pre-seeded shortName → T212 ticker map; extended at runtime from instruments API
        self._ticker_map: dict = {
            "AAPL": "AAPL_US_EQ",
            "TSLA": "TSLA_US_EQ",
            "NVDA": "NVDA_US_EQ",
            "MSFT": "MSFT_US_EQ",
            "AMZN": "AMZN_US_EQ",
            "GOOGL": "GOOGL_US_EQ",
            "META": "FB_US_EQ",
            "NFLX": "NFLX_US_EQ",
        }

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
            self.status.next_run = datetime.now(UTC).replace(
                second=0, microsecond=0
            )
            await asyncio.sleep(settings.TRADE_INTERVAL_SECONDS)

    def stop(self):
        self._running = False
        self.status.enabled = False
        logger.info("Trading engine stopped")

    def toggle(self) -> bool:
        self.status.enabled = not self.status.enabled
        return self.status.enabled

    @property
    def signals_history(self) -> list[TradeSignal]:
        return self._signals_history[-100:]

    @property
    def trade_log(self) -> list[dict]:
        return self._trade_log[-200:]

    @property
    def pnl_history(self) -> list[dict]:
        return self._pnl_history

    @property
    def outcome_log(self) -> list[TradeOutcome]:
        return self._outcome_log[-200:]

    async def close_position(self, ticker: str) -> dict:
        """Close a single open position by short ticker (e.g. 'NVDA').

        Resolves ticker to T212 format, places a market order, logs the trade,
        and appends a PnL snapshot. Raises ValueError if no position found.
        """
        async with Trading212Client() as client:
            positions = await client.get_positions()
            pos = next(
                (p for p in positions if p.ticker.split("_")[0] == ticker or p.ticker == ticker),
                None,
            )
            if pos is None:
                raise ValueError(f"No open position for {ticker}")

            t212_ticker = self._ticker_map.get(ticker, pos.ticker)
            quantity = -pos.quantity
            order = await client.place_market_order(
                MarketOrderRequest(ticker=t212_ticker, quantity=quantity)
            )
            now = datetime.now(UTC)
            self._log_trade({
                "action": "MANUAL_CLOSE",
                "ticker": ticker,
                "quantity": quantity,
                "order_id": order.id,
                "timestamp": now.isoformat(),
            })
            self.status.total_trades_today += 1
            cash = await client.get_cash()
            self._pnl_history.append({
                "t": now.isoformat(),
                "ppl": round(cash.ppl, 2),
                "total": round(cash.total, 2),
                "invested": round(cash.invested, 2),
            })
            return {"message": f"Closed {ticker}", "order_id": order.id}

    async def close_all_positions(self) -> list[dict]:
        """Close all open positions. Logs each successful close.
        Appends one PnL snapshot after all closes attempt.
        Per-position errors are captured and returned as error entries.
        """
        async with Trading212Client() as client:
            positions = await client.get_positions()
            results = []
            for pos in positions:
                short_ticker = pos.ticker.split("_")[0]
                try:
                    quantity = -pos.quantity
                    order = await client.place_market_order(
                        MarketOrderRequest(ticker=pos.ticker, quantity=quantity)
                    )
                    now = datetime.now(UTC)
                    self._log_trade({
                        "action": "MANUAL_CLOSE",
                        "ticker": short_ticker,
                        "quantity": quantity,
                        "order_id": order.id,
                        "timestamp": now.isoformat(),
                    })
                    self.status.total_trades_today += 1
                    results.append({"ticker": short_ticker, "order_id": order.id, "status": "closed"})
                except Exception as e:
                    results.append({"ticker": short_ticker, "status": "error", "detail": str(e)})

            if positions:
                try:
                    cash = await client.get_cash()
                    self._pnl_history.append({
                        "t": datetime.now(UTC).isoformat(),
                        "ppl": round(cash.ppl, 2),
                        "total": round(cash.total, 2),
                        "invested": round(cash.invested, 2),
                    })
                except Exception as e:
                    logger.warning("Could not fetch cash after close-all: %s", e)
            return results

    # -------------------------------------------------------------------------
    # Core cycle
    # -------------------------------------------------------------------------

    async def _cycle(self):
        if not self.status.enabled:
            return

        open_now = is_market_open()
        self.status.market_open = open_now
        self.status.next_market_open = None if open_now else next_open()

        if not open_now:
            if settings.SKIP_MARKET_HOURS_CHECK:
                logger.warning("Market closed but SKIP_MARKET_HOURS_CHECK=True — proceeding anyway")
            else:
                nxt = self.status.next_market_open
                logger.info("Market closed — skipping cycle (next open: %s ET)", nxt)
                return

        logger.info("=== Trading cycle started ===")
        self.status.last_run = datetime.now(UTC)

        async with Trading212Client() as client:
            # Fetch market state
            cash = await client.get_cash()
            positions = await client.get_positions()
            if not self._instruments_cache:
                try:
                    self._instruments_cache = await client.get_instruments()
                    for inst in self._instruments_cache:
                        sn = inst.ticker.split("_")[0]
                        if sn not in self._ticker_map or inst.ticker.endswith("_US_EQ"):
                            self._ticker_map[sn] = inst.ticker
                except Exception as e:
                    logger.warning("Could not fetch instruments (%s), using pre-seeded ticker map", e)
            instruments = self._instruments_cache

            self.status.open_positions = len(positions)
            self.status.total_pnl = cash.ppl

            # Snapshot P&L — reset each new trading day
            today = datetime.now(UTC).strftime("%Y-%m-%d")
            if today != self._session_date:
                self._session_date = today
                self._pnl_history = []
            self._pnl_history.append({
                "t": datetime.now(UTC).isoformat(),
                "ppl": round(cash.ppl, 2),
                "total": round(cash.total, 2),
                "invested": round(cash.invested, 2),
            })

            # 1. Check stop-loss / take-profit on existing positions
            await self._manage_exits(client, positions)

            # Refresh positions after exits
            positions = await client.get_positions()

            # Fetch earnings calendar for watchlist
            earnings_info = self.earnings.get_earnings_info(settings.WATCHLIST)

            # Fetch news headlines for watchlist
            news_data = self.news.get_news(settings.WATCHLIST)

            # 2. Generate new signals via Claude
            signals = self.strategy.generate_signals(
                positions, cash, settings.WATCHLIST, instruments, earnings_info, news_data
            )
            self.status.signals_generated += len(signals)
            self._signals_history.extend(signals)

            # 3. Execute approved signals
            for signal in signals:
                approved, reason = self.risk.validate(signal, positions, cash, earnings_info)
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
                        "timestamp": datetime.now(UTC).isoformat(),
                    })
                    self.status.total_trades_today += 1
                    short_ticker = pos.ticker.split("_")[0]
                    outcome_type = "TP_HIT" if exit_reason == "take-profit" else "SL_HIT"
                    self._update_outcome(short_ticker, outcome_type, pnl_pct=pos.pnl_pct)
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
        # Resolve T212 ticker (e.g. NVDA → NVDA_US_EQ)
        t212_ticker = self._ticker_map.get(signal.ticker, signal.ticker)

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
                    MarketOrderRequest(ticker=t212_ticker, quantity=quantity)
                )
            elif signal.order_type == "LIMIT" and signal.suggested_price:
                order = await client.place_limit_order(
                    LimitOrderRequest(
                        ticker=t212_ticker,
                        quantity=quantity,
                        limitPrice=signal.suggested_price,
                    )
                )
            elif signal.order_type == "STOP" and signal.suggested_price:
                order = await client.place_stop_order(
                    StopOrderRequest(
                        ticker=t212_ticker,
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
                    "timestamp": datetime.now(UTC).isoformat(),
                })
                if signal.action in ("BUY", "SELL"):
                    self._outcome_log.append(TradeOutcome(
                        ticker=signal.ticker,
                        action=signal.action,
                        direction=signal.direction,
                        confidence=signal.confidence,
                        opened_at=datetime.now(UTC),
                    ))

        except Exception as e:
            logger.error("Order execution failed for %s: %s", signal.ticker, e)

    def _log_trade(self, entry: dict):
        self._trade_log.append(entry)
        logger.info("Trade logged: %s", entry)

    def _update_outcome(self, ticker: str, outcome: str, pnl_pct: float | None):
        """Find the last OPEN outcome for ticker and close it."""
        for entry in reversed(self._outcome_log):
            if entry.ticker == ticker and entry.outcome == "OPEN":
                entry.outcome = outcome
                entry.pnl_pct = pnl_pct
                entry.closed_at = datetime.now(UTC)
                return
