"""Prediction-bot strategy CRUD + activate API — issue #105.

Thin wrapper over the shared ``strategy_kit.router`` factory; the prediction
bot supplies its own schema and bot key. The stock bot mounts the same factory
with ``STOCK_SCHEMA`` / ``bot="stock"`` (#110).
"""
from __future__ import annotations

from fastapi import APIRouter

from prediction_bot.src.bot.strategy_runner import PREDICTION_SCHEMA
from strategy_kit.router import make_strategies_router as _make_router
from strategy_kit.store import StrategyStore


def make_strategies_router(
    store: StrategyStore,
    active_strategy_ids: set[str],
) -> APIRouter:
    return _make_router(
        store,
        active_strategy_ids,
        schema=PREDICTION_SCHEMA,
        bot="prediction",
    )
