"""Tests for strategy CRUD + activate endpoints — issue #105."""
import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from prediction_bot.src.dashboard.strategies_router import make_strategies_router
from strategy_kit.store import StrategyStore


@pytest.fixture
def client(tmp_path):
    store = StrategyStore(str(tmp_path / "test.db"))
    asyncio.run(store.initialize())

    active_ids: set[str] = set()
    router = make_strategies_router(store, active_ids)

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestStrategyCRUD:
    def test_list_empty(self, client):
        r = client.get("/strategies")
        assert r.status_code == 200
        assert r.json() == []

    def test_create_and_list(self, client):
        payload = {
            "name": "My Strategy",
            "description": "test",
            "bot": "prediction",
            "params": {"HIGH_PROB_MIN": 0.85},
        }
        r = client.post("/strategies", json=payload)
        assert r.status_code == 201
        created = r.json()
        assert created["name"] == "My Strategy"
        assert created["params"]["HIGH_PROB_MIN"] == 0.85

        r2 = client.get("/strategies")
        assert len(r2.json()) == 1

    def test_get_by_id(self, client):
        r = client.post("/strategies", json={"name": "S", "bot": "prediction", "params": {}})
        sid = r.json()["id"]
        r2 = client.get(f"/strategies/{sid}")
        assert r2.status_code == 200
        assert r2.json()["id"] == sid

    def test_get_returns_404_for_unknown(self, client):
        r = client.get("/strategies/nonexistent-id")
        assert r.status_code == 404

    def test_update_strategy(self, client):
        r = client.post("/strategies", json={"name": "Old", "bot": "prediction", "params": {}})
        sid = r.json()["id"]
        r2 = client.put(f"/strategies/{sid}", json={"name": "New", "params": {"k": 1}})
        assert r2.status_code == 200
        r3 = client.get(f"/strategies/{sid}")
        assert r3.json()["name"] == "New"
        assert r3.json()["params"]["k"] == 1

    def test_archive_strategy(self, client):
        r = client.post("/strategies", json={"name": "Gone", "bot": "prediction", "params": {}})
        sid = r.json()["id"]
        r2 = client.post(f"/strategies/{sid}/archive")
        assert r2.status_code == 200
        r3 = client.get("/strategies")
        ids = [s["id"] for s in r3.json()]
        assert sid not in ids

    def test_create_ignores_client_bot_override(self, client):
        # The factory's bot wins — a client cannot write into another namespace.
        r = client.post("/strategies", json={"name": "X", "bot": "stock", "params": {}})
        assert r.status_code == 201
        assert r.json()["bot"] == "prediction"


class TestActivateDeactivate:
    def test_activate_adds_to_active_set(self, client):
        r = client.post("/strategies", json={"name": "S", "bot": "prediction", "params": {}})
        sid = r.json()["id"]
        r2 = client.post(f"/strategies/{sid}/activate")
        assert r2.status_code == 200
        assert r2.json()["active"] is True

    def test_deactivate_removes_from_active_set(self, client):
        r = client.post("/strategies", json={"name": "S", "bot": "prediction", "params": {}})
        sid = r.json()["id"]
        client.post(f"/strategies/{sid}/activate")
        r2 = client.post(f"/strategies/{sid}/deactivate")
        assert r2.status_code == 200
        assert r2.json()["active"] is False

    def test_activate_unknown_returns_404(self, client):
        r = client.post("/strategies/nope/activate")
        assert r.status_code == 404


class TestSchemaEndpoint:
    def test_get_schema_returns_param_fields(self, client):
        r = client.get("/strategies/schema")
        assert r.status_code == 200
        data = r.json()
        assert "fields" in data
        keys = {f["key"] for f in data["fields"]}
        assert "BET_STRATEGY" in keys
        assert "HIGH_PROB_MIN" in keys
