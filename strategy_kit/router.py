"""Reusable strategy CRUD + activate/deactivate FastAPI router.

Bot-agnostic: parameterised by a ``ParamSchema`` (for the /schema endpoint)
and a ``bot`` key (to scope list/create). Each bot mounts it with a thin
wrapper so the CRUD logic lives in exactly one place.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from strategy_kit.models import ParamSchema, StrategyDefinition
from strategy_kit.store import StrategyStore


class _CreatePayload(BaseModel):
    name: str
    description: str = ""
    # Accepted for forward-compat but ignored — the factory's ``bot`` wins so a
    # client can't write a strategy into another bot's namespace.
    bot: str | None = None
    params: dict = {}


class _UpdatePayload(BaseModel):
    name: str | None = None
    description: str | None = None
    params: dict | None = None


class _ImportPayload(BaseModel):
    # Portable export format (id/timestamps/bot are assigned on import).
    name: str
    description: str = ""
    params: dict = {}


_EXPORT_FORMAT = "strategy-export/v1"


def make_strategies_router(
    store: StrategyStore,
    active_strategy_ids: set[str],
    *,
    schema: ParamSchema,
    bot: str,
) -> APIRouter:
    router = APIRouter(prefix="/strategies", tags=["strategies"])

    # Declared before /{strategy_id} so "schema" is never captured as an id.
    @router.get("/schema")
    async def get_schema():
        return schema.model_dump(mode="json")

    @router.get("")
    async def list_strategies():
        strategies = await store.list(bot)
        return [s.model_dump(mode="json") for s in strategies]

    @router.post("", status_code=201)
    async def create_strategy(payload: _CreatePayload):
        defn = StrategyDefinition(
            name=payload.name,
            description=payload.description,
            bot=bot,
            params=payload.params,
        )
        await store.create(defn)
        return defn.model_dump(mode="json")

    @router.post("/import", status_code=201)
    async def import_strategy(payload: _ImportPayload):
        # Local sharing: import a strategy exported from another machine.
        try:
            schema.validate_params(payload.params)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=f"Invalid strategy params: {e}")
        defn = StrategyDefinition(
            name=payload.name, description=payload.description, bot=bot,
            params=payload.params,
        )
        await store.create(defn)
        return defn.model_dump(mode="json")

    @router.get("/{strategy_id}/export")
    async def export_strategy(strategy_id: str):
        defn = await store.get(strategy_id)
        if defn is None:
            raise HTTPException(status_code=404, detail="Strategy not found")
        return {
            "_format": _EXPORT_FORMAT,
            "name": defn.name,
            "description": defn.description,
            "params": defn.params,
        }

    @router.get("/{strategy_id}")
    async def get_strategy(strategy_id: str):
        defn = await store.get(strategy_id)
        if defn is None:
            raise HTTPException(status_code=404, detail="Strategy not found")
        return defn.model_dump(mode="json")

    @router.put("/{strategy_id}")
    async def update_strategy(strategy_id: str, payload: _UpdatePayload):
        if await store.get(strategy_id) is None:
            raise HTTPException(status_code=404, detail="Strategy not found")
        await store.update(
            strategy_id,
            name=payload.name,
            description=payload.description,
            params=payload.params,
        )
        updated = await store.get(strategy_id)
        return updated.model_dump(mode="json")

    @router.post("/{strategy_id}/archive")
    async def archive_strategy(strategy_id: str):
        if await store.get(strategy_id) is None:
            raise HTTPException(status_code=404, detail="Strategy not found")
        await store.archive(strategy_id)
        active_strategy_ids.discard(strategy_id)
        return {"archived": True}

    @router.post("/{strategy_id}/activate")
    async def activate_strategy(strategy_id: str):
        if await store.get(strategy_id) is None:
            raise HTTPException(status_code=404, detail="Strategy not found")
        await store.activate(strategy_id)
        active_strategy_ids.add(strategy_id)
        return {"active": True}

    @router.post("/{strategy_id}/deactivate")
    async def deactivate_strategy(strategy_id: str):
        if await store.get(strategy_id) is None:
            raise HTTPException(status_code=404, detail="Strategy not found")
        await store.deactivate(strategy_id)
        active_strategy_ids.discard(strategy_id)
        return {"active": False}

    return router
