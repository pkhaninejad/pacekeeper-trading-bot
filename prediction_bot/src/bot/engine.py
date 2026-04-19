"""PredictionEngine — orchestrates scan → evaluate → trade cycle."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
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


@asynccontextmanager
async def _noop_ctx():
    yield None


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
        self._sse_queues: list[asyncio.Queue] = []
        self._poly_client = None
        self._kalshi_client = None

    async def start(self):
        await self.paper_trader.initialize()

        poly_ctx = PolymarketClient().__aenter__ if self.settings.POLYMARKET_ENABLED else None
        kalshi_ctx = KalshiClient().__aenter__ if self.settings.KALSHI_ENABLED else None

        poly_cm = PolymarketClient() if self.settings.POLYMARKET_ENABLED else _noop_ctx()
        kalshi_cm = KalshiClient() if self.settings.KALSHI_ENABLED else _noop_ctx()

        async with poly_cm as poly, kalshi_cm as kalshi:
            self._poly_client = poly
            self._kalshi_client = kalshi
            self._running = True
            logger.info(
                "Prediction Market Bot started — Polymarket=%s Kalshi=%s",
                self.settings.POLYMARKET_ENABLED, self.settings.KALSHI_ENABLED,
            )
            while self._running:
                if self.status.enabled:
                    try:
                        await self._cycle()
                    except Exception as e:
                        logger.error("Cycle error: %s", e, exc_info=True)
                await asyncio.sleep(self.settings.SCAN_INTERVAL_SECONDS)

    async def _cycle(self):
        logger.info("Starting scan cycle...")

        await self.paper_trader.settle_open_trades(self._poly_client, self._kalshi_client)

        candidates = await scan_markets(self._poly_client, self._kalshi_client, self.settings)
        logger.info("Scanner found %d candidates", len(candidates))

        evaluated = []
        if candidates:
            evaluated = await evaluate_candidates(candidates, self.settings)
            logger.info("Evaluator found %d with edge", len(evaluated))

        trades_placed = 0
        for candidate in evaluated:
            trade = await self.paper_trader.place_paper_trade(candidate)
            if trade:
                trades_placed += 1
                await self._broadcast({"type": "trade_placed", "trade": trade.model_dump(mode="json")})

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
        return self.status.enabled
