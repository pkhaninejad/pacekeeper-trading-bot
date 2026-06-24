"""Paper trading state machine on top of ResultStore."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from prediction_bot.src.api.models import MarketCandidate, PaperTrade
from prediction_bot.src.bot.strategy_runner import TradeDecision
from prediction_bot.src.config.settings import PredictionBotSettings
from prediction_bot.src.data.result_store import ResultStore

logger = logging.getLogger(__name__)


class PaperTrader:
    def __init__(self, store: ResultStore, settings: PredictionBotSettings):
        self.store = store
        self.settings = settings

    async def initialize(self):
        await self.store.initialize()
        stats = await self.store.get_stats()
        if stats["total_trades"] > 0:
            self._log_summary(stats)

    def _log_summary(self, stats: dict):
        logger.info("=" * 60)
        logger.info("PREVIOUS RESULTS SUMMARY")
        logger.info("  Total trades: %d", stats["total_trades"])
        wr = f"{stats['win_rate']:.1%}" if stats["win_rate"] is not None else "N/A"
        logger.info("  Win rate: %s (%dW / %dL / %dE)", wr, stats["won"], stats["lost"], stats["expired"])
        logger.info("  Total P&L: $%.2f", stats["total_pnl"])
        logger.info("  ROI: %.1f%%", stats["roi"] * 100)
        logger.info("  Current bankroll: $%.2f", stats["bankroll"])
        logger.info("=" * 60)

    async def place_decision(
        self, decision: TradeDecision, strategy_id: str = "default"
    ) -> PaperTrade | None:
        bankroll = await self.store.get_bankroll(strategy_id)
        open_trades = await self.store.get_open_trades(strategy_id)

        if len(open_trades) >= self.settings.MAX_OPEN_POSITIONS:
            return None
        existing_ids = {t.market_id for t in open_trades}
        if decision.candidate.market.id in existing_ids:
            return None

        trade = PaperTrade(
            platform=decision.candidate.market.platform,
            market_id=decision.candidate.market.id,
            market_question=decision.candidate.market.question,
            category=decision.candidate.market.category,
            side=decision.side,
            entry_price=decision.candidate.market_price,
            quantity=float(decision.quantity),
            cost=decision.cost,
            confidence=decision.candidate.llm_confidence or 0.5,
            reasoning=decision.candidate.llm_reasoning,
            created_at=datetime.now(UTC),
            end_date=decision.candidate.market.end_date,
            strategy_id=strategy_id,
        )
        trade_id = await self.store.add_trade(trade, initial_bankroll=bankroll, strategy_id=strategy_id)
        logger.info(
            "[%s] Paper trade: %s '%s' @ $%.2f (qty=%d, cost=$%.2f)",
            strategy_id, trade.side, trade.market_question[:60],
            trade.entry_price, decision.quantity, decision.cost,
        )
        return trade.model_copy(update={"id": trade_id})

    async def place_paper_trade(
        self, candidate: MarketCandidate, strategy_id: str = "default"
    ) -> PaperTrade | None:
        bankroll = await self.store.get_bankroll(strategy_id)
        open_trades = await self.store.get_open_trades(strategy_id)

        if len(open_trades) >= self.settings.MAX_OPEN_POSITIONS:
            logger.debug("Max positions reached, skipping %s", candidate.market.id)
            return None

        existing_ids = {t.market_id for t in open_trades}
        if candidate.market.id in existing_ids:
            logger.debug("Already holding %s, skipping", candidate.market.id)
            return None

        max_allocation = bankroll * self.settings.MAX_POSITION_PCT
        entry_price = candidate.market_price
        if entry_price <= 0:
            return None

        quantity = int(max_allocation / entry_price)
        if quantity < 1:
            logger.debug("Insufficient bankroll for %s", candidate.market.id)
            return None

        cost = entry_price * quantity
        trade = PaperTrade(
            platform=candidate.market.platform,
            market_id=candidate.market.id,
            market_question=candidate.market.question,
            category=candidate.market.category,
            side=candidate.best_side,
            entry_price=entry_price,
            quantity=float(quantity),
            cost=cost,
            confidence=candidate.llm_confidence or 0.5,
            reasoning=candidate.llm_reasoning,
            created_at=datetime.now(UTC),
            end_date=candidate.market.end_date,
            strategy_id=strategy_id,
        )
        trade_id = await self.store.add_trade(trade, initial_bankroll=bankroll, strategy_id=strategy_id)
        logger.info(
            "[%s] Paper trade: %s '%s' @ $%.2f (qty=%d, cost=$%.2f)",
            strategy_id, trade.side, trade.market_question[:60],
            entry_price, quantity, cost,
        )
        return trade.model_copy(update={"id": trade_id})

    async def re_settle_expired_trades(
        self, clients: dict, strategy_id: str = "default"
    ) -> int:
        expired = await self.store._fetch_trades(
            "WHERE status = 'EXPIRED' AND strategy_id = ?", (strategy_id,)
        )
        corrected = 0
        for trade in expired:
            client = clients.get(trade.platform)
            if not client:
                continue
            try:
                status = await client.get_market_status(trade.market_id)
                if status["resolved"] and status["winner"]:
                    won = status["winner"] == trade.side
                    await self.store.re_settle_expired(trade.id, won=won)
                    result = "WON" if won else "LOST"
                    logger.info(
                        "[%s] RE-SETTLED %s: '%s' → %s",
                        strategy_id, trade.market_id, trade.market_question[:50], result,
                    )
                    corrected += 1
            except Exception as e:
                logger.warning("Re-settlement check failed for %s: %s", trade.market_id, e)
        return corrected

    async def settle_open_trades(
        self, clients: dict | None = None, strategy_id: str = "default", **kwargs
    ):
        # Support legacy keyword-arg style: settle_open_trades(polymarket=..., kalshi=...)
        if clients is None:
            clients = {k: v for k, v in kwargs.items() if v is not None}

        open_trades = await self.store.get_open_trades(strategy_id)
        now = datetime.now(UTC)

        for trade in open_trades:
            try:
                client = clients.get(trade.platform)
                if not client:
                    continue

                status = await client.get_market_status(trade.market_id)
                if status["resolved"] and status["winner"]:
                    won = status["winner"] == trade.side
                    await self.store.settle_trade(trade.id, won=won)
                    result = "WON" if won else "LOST"
                    logger.info(
                        "[%s] SETTLED %s: '%s' → %s",
                        strategy_id, trade.market_id, trade.market_question[:50], result,
                    )
                elif trade.end_date and now > trade.end_date + timedelta(hours=24):
                    await self.store.expire_trade(trade.id)
                    logger.info(
                        "[%s] EXPIRED %s: '%s'",
                        strategy_id, trade.market_id, trade.market_question[:50],
                    )
            except Exception as e:
                logger.warning("Settlement check failed for %s: %s", trade.market_id, e)
