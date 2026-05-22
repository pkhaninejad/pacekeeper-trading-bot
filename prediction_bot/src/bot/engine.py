"""PredictionEngine — orchestrates scan → evaluate-once → per-strategy apply cycle."""
from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from datetime import UTC, datetime, timedelta

from prediction_bot.src.api.kalshi_client import KalshiClient
from prediction_bot.src.api.models import PMBotStatus
from prediction_bot.src.api.polymarket_client import PolymarketClient
from prediction_bot.src.bot.evaluator import evaluate_candidates
from prediction_bot.src.bot.paper_trader import PaperTrader
from prediction_bot.src.bot.scanner import scan_markets
from prediction_bot.src.bot.strategy_runner import PREDICTION_SCHEMA, StrategyRunner
from prediction_bot.src.config.settings import pm_settings
from prediction_bot.src.data.result_store import ResultStore
from strategy_kit import StrategyDefinition
from strategy_kit.portfolio import ShadowPortfolio
from strategy_kit.store import StrategyStore

logger = logging.getLogger(__name__)


def _settings_to_params(s) -> dict:
    return {
        "HIGH_PROB_MIN": s.HIGH_PROB_MIN,
        "HIGH_PROB_MAX": s.HIGH_PROB_MAX,
        "MIN_EDGE_PCT": s.MIN_EDGE_PCT,
        "EXPIRY_WINDOW_HOURS": float(s.EXPIRY_WINDOW_HOURS),
        "BET_STRATEGY": "kelly",
        "MAX_POSITION_PCT": s.MAX_POSITION_PCT,
        "VIRTUAL_BANKROLL": s.VIRTUAL_BANKROLL,
        "MIN_RR_RATIO": 2.0,
        "MAX_OPEN_POSITIONS": float(s.MAX_OPEN_POSITIONS),
        "MIN_LIQUIDITY": s.MIN_LIQUIDITY,
        "ENABLED_CATEGORIES": ",".join(s.ENABLED_CATEGORIES),
    }


class PredictionEngine:
    def __init__(self):
        self.settings = pm_settings
        store = ResultStore(self.settings.PM_DB_PATH)
        self.paper_trader = PaperTrader(store=store, settings=self.settings)
        self._strategy_store = StrategyStore(self.settings.PM_DB_PATH)
        self._portfolio = ShadowPortfolio(self.settings.PM_DB_PATH)
        self._active_strategies: list[StrategyDefinition] = []
        self._shadow_map: dict[str, dict[str, int]] = {}  # strategy_id → {market_id → shadow_trade_id}
        self.status = PMBotStatus(
            platforms={
                "polymarket": self.settings.POLYMARKET_ENABLED,
                "kalshi": self.settings.KALSHI_ENABLED,
            },
            categories=self.settings.ENABLED_CATEGORIES,
            bankroll=self.settings.VIRTUAL_BANKROLL,
        )
        self._running = False
        self.scan_history: list[dict] = []
        self.activity_history: list[dict] = []
        self._sse_queues: list[asyncio.Queue] = []
        self._clients: dict = {}

    async def _activity(self, message: str):
        event = {"timestamp": datetime.now(UTC).isoformat(), "message": message}
        self.activity_history.append(event)
        if len(self.activity_history) > 100:
            self.activity_history = self.activity_history[-100:]
        await self._broadcast({"type": "activity", "activity": event})

    async def start(self):
        await self.paper_trader.initialize()
        await self._strategy_store.initialize()
        await self._portfolio.initialize()

        # Load active strategies; create default if none exist
        strategies = await self._strategy_store.list("prediction", active_only=True)
        if not strategies:
            default = StrategyDefinition(
                name="Default",
                description="Auto-created from current settings",
                bot="prediction",
                params=_settings_to_params(self.settings),
            )
            await self._strategy_store.create(default)
            strategies = [default]
        self._active_strategies = strategies

        # Seed ShadowPortfolio bankroll for each strategy (once)
        for strategy in self._active_strategies:
            curve = await self._portfolio.equity_curve(strategy.id)
            if not curve:
                vb = float(strategy.params.get("VIRTUAL_BANKROLL", self.settings.VIRTUAL_BANKROLL))
                await self._portfolio.seed_bankroll(strategy.id, vb)

        clients_pending = []
        if self.settings.POLYMARKET_ENABLED:
            clients_pending.append(PolymarketClient())
        if self.settings.KALSHI_ENABLED:
            clients_pending.append(KalshiClient())

        async with AsyncExitStack() as stack:
            for client in clients_pending:
                active = await stack.enter_async_context(client)
                self._clients[client.platform] = active

            enabled = list(self._clients.keys())
            logger.info("Prediction Market Bot started — platforms: %s", enabled)
            await self._activity(
                f"Bot is online. Watching {', '.join(enabled) if enabled else 'no platforms'}."
            )

            self._running = True
            while self._running:
                if self.status.enabled:
                    try:
                        await self._cycle()
                    except Exception as e:
                        logger.error("Cycle error: %s", e, exc_info=True)
                await asyncio.sleep(self.settings.SCAN_INTERVAL_SECONDS)

    async def _cycle(self):
        logger.info("Starting scan cycle (%d strategies)...", len(self._active_strategies))
        await self._activity("Starting a new market scan.")

        # Settle/expire per strategy
        for strategy in self._active_strategies:
            await self.paper_trader.re_settle_expired_trades(self._clients, strategy.id)
            await self.paper_trader.settle_open_trades(self._clients, strategy.id)
        await self._activity("Checked open positions and settled finished markets.")

        # Evaluate ONCE
        candidates = await scan_markets(list(self._clients.values()), self.settings)
        logger.info("Scanner found %d candidates", len(candidates))
        evaluated = []
        if candidates:
            evaluated = await evaluate_candidates(candidates, self.settings)
            logger.info("Evaluator found %d with edge", len(evaluated))

        if not evaluated:
            await self._activity("No opportunities with edge found this cycle.")
        else:
            await self._activity(f"{len(evaluated)} opportunities passed quality checks.")

        total_placed = 0
        # Apply per strategy
        for strategy in self._active_strategies:
            bankroll = await self.paper_trader.store.get_bankroll(strategy.id)
            open_trades = await self.paper_trader.store.get_open_trades(strategy.id)
            open_ids = {t.market_id for t in open_trades}

            runner = StrategyRunner(strategy.params)
            decisions = runner.run(evaluated, bankroll, open_ids)

            for decision in decisions:
                trade = await self.paper_trader.place_decision(decision, strategy_id=strategy.id)
                if trade:
                    total_placed += 1
                    await self._broadcast({"type": "trade_placed", "trade": trade.model_dump(mode="json")})
                    # Track in ShadowPortfolio
                    shadow_tid = await self._portfolio.open_trade(
                        strategy.id, trade.market_id,
                        entry_price=trade.entry_price,
                        quantity=trade.quantity,
                    )
                    self._shadow_map.setdefault(strategy.id, {})[trade.market_id] = shadow_tid

        # Update status from first strategy (backward compat)
        if self._active_strategies:
            first_id = self._active_strategies[0].id
            stats = await self.paper_trader.store.get_stats(first_id)
            self.status.open_trades = stats["open_trades"]
            self.status.bankroll = stats["bankroll"]
            self.status.total_pnl = stats["total_pnl"]
            self.status.win_rate = stats["win_rate"]

        self.status.last_scan = datetime.now(UTC)
        self.status.next_scan = datetime.now(UTC) + timedelta(seconds=self.settings.SCAN_INTERVAL_SECONDS)

        scan_record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "candidates_found": len(candidates),
            "edges_found": len(evaluated),
            "trades_placed": total_placed,
        }
        self.scan_history.append(scan_record)
        if len(self.scan_history) > 50:
            self.scan_history = self.scan_history[-50:]

        msg = "Cycle complete: no new trades placed." if total_placed == 0 else f"Cycle complete: placed {total_placed} trade(s)."
        await self._activity(msg)
        await self._broadcast({"type": "cycle_complete", "status": self.status.model_dump(mode="json")})

    async def _broadcast(self, event: dict):
        for q in list(self._sse_queues):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def stop(self):
        self._running = False

    def toggle(self) -> bool:
        self.status.enabled = not self.status.enabled
        state = "enabled" if self.status.enabled else "paused"
        self.activity_history.append(
            {"timestamp": datetime.now(UTC).isoformat(), "message": f"Bot {state} by user."}
        )
        return self.status.enabled

    def set_interval(self, seconds: int) -> int:
        self.settings.SCAN_INTERVAL_SECONDS = seconds
        self.status.next_scan = (
            datetime.now(UTC) + timedelta(seconds=seconds) if self.status.last_scan else None
        )
        return seconds
