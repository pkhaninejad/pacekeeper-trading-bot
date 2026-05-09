"""PredictionEngine — orchestrates scan → evaluate → trade cycle."""
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
from prediction_bot.src.config.settings import pm_settings
from prediction_bot.src.data.result_store import ResultStore

logger = logging.getLogger(__name__)


class PredictionEngine:
    def __init__(self):
        self.settings = pm_settings
        store = ResultStore(self.settings.PM_DB_PATH)
        self.paper_trader = PaperTrader(store=store, settings=self.settings)
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
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "message": message,
        }
        self.activity_history.append(event)
        if len(self.activity_history) > 100:
            self.activity_history = self.activity_history[-100:]
        await self._broadcast({"type": "activity", "activity": event})

    async def start(self):
        await self.paper_trader.initialize()

        candidates = []
        if self.settings.POLYMARKET_ENABLED:
            candidates.append(PolymarketClient())
        if self.settings.KALSHI_ENABLED:
            candidates.append(KalshiClient())

        async with AsyncExitStack() as stack:
            for client in candidates:
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
        logger.info("Starting scan cycle...")
        await self._activity("Starting a new market scan.")

        await self.paper_trader.re_settle_expired_trades(self._clients)
        await self.paper_trader.settle_open_trades(self._clients)
        await self._activity("Checked open positions and settled finished markets.")

        candidates = await scan_markets(list(self._clients.values()), self.settings)
        logger.info("Scanner found %d candidates", len(candidates))
        if not candidates:
            await self._activity("No promising markets found right now. Will try again next cycle.")
        else:
            await self._activity(f"Found {len(candidates)} promising market candidates.")

        evaluated = []
        if candidates:
            evaluated = await evaluate_candidates(candidates, self.settings)
            logger.info("Evaluator found %d with edge", len(evaluated))
            if not evaluated:
                await self._activity("Candidates were reviewed, but none had enough edge to trade.")
            else:
                await self._activity(f"{len(evaluated)} opportunities passed quality checks.")

        trades_placed = 0
        for candidate in evaluated:
            trade = await self.paper_trader.place_paper_trade(candidate)
            if trade:
                trades_placed += 1
                await self._broadcast({"type": "trade_placed", "trade": trade.model_dump(mode="json")})
                await self._activity(
                    f"Placed paper trade: {trade.side} on '{trade.market_question[:70]}'."
                )

        stats = await self.paper_trader.store.get_stats()
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
            "trades_placed": trades_placed,
        }
        self.scan_history.append(scan_record)
        if len(self.scan_history) > 50:
            self.scan_history = self.scan_history[-50:]

        if trades_placed == 0:
            await self._activity("Cycle complete: no new trades placed this round.")
        else:
            await self._activity(f"Cycle complete: placed {trades_placed} new trade(s).")

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
            datetime.now(UTC) + timedelta(seconds=seconds)
            if self.status.last_scan else None
        )
        return seconds
