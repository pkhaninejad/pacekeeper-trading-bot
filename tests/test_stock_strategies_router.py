"""Tests for stock strategy CRUD + LIVE-designation API — issue #110."""
import asyncio

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import src.dashboard.app as app_module
from src.bot.live_designation import LiveDesignation
from src.dashboard.strategies_router import make_strategies_router
from strategy_kit.models import StrategyDefinition
from strategy_kit.store import StrategyStore


# ── Shared CRUD router (reuses the #105 factory with the stock schema) ──────────

@pytest.fixture
def client(tmp_path):
    store = StrategyStore(str(tmp_path / "t.db"))
    asyncio.run(store.initialize())
    app = FastAPI()
    app.include_router(make_strategies_router(store, set()))
    return TestClient(app)


def test_schema_exposes_stock_keys(client):
    r = client.get("/strategies/schema")
    assert r.status_code == 200
    keys = {f["key"] for f in r.json()["fields"]}
    assert {"STOP_LOSS_PCT", "TAKE_PROFIT_PCT", "MAX_POSITION_SIZE_PCT"} <= keys


def test_create_is_scoped_to_stock_bot(client):
    r = client.post("/strategies", json={"name": "S", "params": {"STOP_LOSS_PCT": 0.03}})
    assert r.status_code == 201
    assert r.json()["bot"] == "stock"
    assert r.json()["params"]["STOP_LOSS_PCT"] == 0.03


# ── LIVE-designation endpoints (call handlers directly with a stub engine) ──────

class _StubEngine:
    def __init__(self, store, designation, live_confirmed):
        self._strategy_store = store
        self._live_designation = designation
        self._live_confirmed = live_confirmed


@pytest.fixture
async def stub(tmp_path, monkeypatch):
    store = StrategyStore(str(tmp_path / "s.db"))
    await store.initialize()
    eng = _StubEngine(store, LiveDesignation(tmp_path / "live.json"), live_confirmed=False)
    monkeypatch.setattr(app_module, "engine", eng)
    monkeypatch.setattr(app_module.settings, "T212_ENV", "demo")
    return eng, store


async def test_designate_live_in_demo(stub):
    _eng, store = stub
    defn = StrategyDefinition(name="S", bot="stock", params={})
    await store.create(defn)
    res = await app_module.designate_live_strategy(defn.id)
    assert res["live_strategy_id"] == defn.id
    assert (await app_module.get_live_strategy())["live_strategy_id"] == defn.id


async def test_designate_unknown_returns_404(stub):
    with pytest.raises(HTTPException) as ei:
        await app_module.designate_live_strategy("nope")
    assert ei.value.status_code == 404


async def test_designate_live_mode_requires_confirmation(stub, monkeypatch):
    _eng, store = stub
    monkeypatch.setattr(app_module.settings, "T212_ENV", "live")
    defn = StrategyDefinition(name="S", bot="stock", params={})
    await store.create(defn)
    with pytest.raises(HTTPException) as ei:
        await app_module.designate_live_strategy(defn.id)
    assert ei.value.status_code == 409  # must confirm live first
