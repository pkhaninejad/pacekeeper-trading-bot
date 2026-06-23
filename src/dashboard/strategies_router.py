"""Stock-bot strategy CRUD + activate API — issue #110.

Thin wrapper over the shared ``strategy_kit.router`` factory (same one the
prediction bot mounts), supplying the stock schema and bot key. LIVE-designation
endpoints are stock-specific and wired in ``app.py`` where the engine lives.
"""
from __future__ import annotations

from fastapi import APIRouter

from src.bot.strategy_runner import STOCK_SCHEMA, STOCK_STARTERS
from strategy_kit.router import make_strategies_router as _make_router
from strategy_kit.store import StrategyStore


def make_strategies_router(
    store: StrategyStore,
    active_strategy_ids: set[str],
) -> APIRouter:
    return _make_router(
        store,
        active_strategy_ids,
        schema=STOCK_SCHEMA,
        bot="stock",
        starters=STOCK_STARTERS,
    )
