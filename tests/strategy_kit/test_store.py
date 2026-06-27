"""Tests for StrategyStore CRUD."""
import pytest
from strategy_kit.models import StrategyDefinition
from strategy_kit.store import StrategyStore


@pytest.fixture
async def store(tmp_path):
    s = StrategyStore(str(tmp_path / "strategies.db"))
    await s.initialize()
    return s


def _defn(**kwargs) -> StrategyDefinition:
    defaults = dict(name="My Strategy", bot="prediction", description="test")
    defaults.update(kwargs)
    return StrategyDefinition(**defaults)


class TestStrategyStore:
    async def test_initialize_is_idempotent(self, tmp_path):
        """initialize() can be called twice without error."""
        s = StrategyStore(str(tmp_path / "strategies.db"))
        await s.initialize()
        await s.initialize()  # must not raise

    async def test_create_and_get_round_trip(self, store):
        """create() + get() returns the same definition."""
        defn = _defn(name="Alpha", params={"threshold": 0.7})
        sid = await store.create(defn)
        result = await store.get(sid)
        assert result is not None
        assert result.name == "Alpha"
        assert result.params == {"threshold": 0.7}
        assert result.bot == "prediction"
        assert result.archived is False

    async def test_get_returns_none_for_unknown(self, store):
        """get() returns None if id doesn't exist."""
        result = await store.get("nonexistent-id")
        assert result is None

    async def test_list_filters_by_bot(self, store):
        """list(bot=) returns only strategies for that bot."""
        await store.create(_defn(name="P1", bot="prediction"))
        await store.create(_defn(name="S1", bot="stock"))
        await store.create(_defn(name="P2", bot="prediction"))

        prediction = await store.list("prediction")
        stock = await store.list("stock")

        assert len(prediction) == 2
        assert all(d.bot == "prediction" for d in prediction)
        assert len(stock) == 1

    async def test_list_excludes_archived_by_default(self, store):
        """list() hides archived strategies unless include_archived=True."""
        defn = _defn(name="Active", bot="prediction")
        defn2 = _defn(name="Archived", bot="prediction")
        id1 = await store.create(defn)
        id2 = await store.create(defn2)
        await store.archive(id2)

        visible = await store.list("prediction")
        all_strategies = await store.list("prediction", include_archived=True)

        assert len(visible) == 1
        assert visible[0].id == id1
        assert len(all_strategies) == 2

    async def test_update_name_and_params(self, store):
        """update() persists new name and params."""
        defn = _defn(name="Old Name", params={"k": 1})
        sid = await store.create(defn)
        await store.update(sid, name="New Name", params={"k": 2, "j": 3})
        result = await store.get(sid)
        assert result.name == "New Name"
        assert result.params == {"k": 2, "j": 3}

    async def test_update_noop_when_no_fields(self, store):
        """update() with no kwargs doesn't error or change the record."""
        defn = _defn(name="Unchanged")
        sid = await store.create(defn)
        await store.update(sid)  # no-op, must not raise
        result = await store.get(sid)
        assert result.name == "Unchanged"

    async def test_archive_sets_archived_flag(self, store):
        """archive() sets archived=True and get() reflects it."""
        sid = await store.create(_defn(name="Soon Gone", bot="prediction"))
        await store.archive(sid)
        result = await store.get(sid)
        assert result.archived is True

    async def test_params_json_survives_round_trip(self, store):
        """Nested dict params are serialized/deserialized correctly."""
        params = {"nested": {"a": 1, "b": [1, 2, 3]}, "flag": True}
        sid = await store.create(_defn(params=params))
        result = await store.get(sid)
        assert result.params == params

    async def test_update_nonexistent_id_is_silent_noop(self, store):
        """update() on a missing id silently does nothing."""
        await store.update("nonexistent-id", name="Ghost")  # must not raise

    async def test_archive_nonexistent_id_is_silent_noop(self, store):
        """archive() on a missing id silently does nothing."""
        await store.archive("nonexistent-id")  # must not raise
