"""Tests for strategy_kit models and registry."""
import pytest
from strategy_kit import ParamField, ParamSchema, StrategyDefinition, get_schema, register


class TestParamSchema:
    def test_fill_defaults_fills_missing_keys(self):
        schema = ParamSchema(fields=[
            ParamField(key="threshold", label="Threshold", type="number", default=0.6),
            ParamField(key="side", label="Side", type="select", default="YES",
                       options=["YES", "NO"]),
        ])
        result = schema.fill_defaults({"threshold": 0.8})
        assert result == {"threshold": 0.8, "side": "YES"}

    def test_fill_defaults_empty_params(self):
        schema = ParamSchema(fields=[
            ParamField(key="k", label="K", type="number", default=1.5),
        ])
        result = schema.fill_defaults({})
        assert result == {"k": 1.5}

    def test_validate_params_rejects_below_min(self):
        schema = ParamSchema(fields=[
            ParamField(key="conf", label="Confidence", type="percent", default=0.6,
                       min=0.0, max=1.0),
        ])
        with pytest.raises(ValueError, match="conf"):
            schema.validate_params({"conf": -0.1})

    def test_validate_params_rejects_above_max(self):
        schema = ParamSchema(fields=[
            ParamField(key="conf", label="Confidence", type="percent", default=0.6,
                       min=0.0, max=1.0),
        ])
        with pytest.raises(ValueError, match="conf"):
            schema.validate_params({"conf": 1.5})

    def test_validate_params_rejects_invalid_select(self):
        schema = ParamSchema(fields=[
            ParamField(key="mode", label="Mode", type="select", default="a",
                       options=["a", "b"]),
        ])
        with pytest.raises(ValueError, match="mode"):
            schema.validate_params({"mode": "c"})

    def test_validate_params_accepts_valid_params(self):
        schema = ParamSchema(fields=[
            ParamField(key="n", label="N", type="number", default=5, min=1, max=10),
        ])
        schema.validate_params({"n": 7})  # must not raise

    def test_validate_params_skips_missing_keys(self):
        schema = ParamSchema(fields=[
            ParamField(key="n", label="N", type="number", default=5, min=1, max=10),
        ])
        schema.validate_params({})  # must not raise


class TestStrategyDefinition:
    def test_defaults_are_set(self):
        defn = StrategyDefinition(name="My Strategy", bot="prediction")
        assert defn.id != ""
        assert defn.archived is False
        assert defn.params == {}
        assert defn.created_at is not None

    def test_bot_must_be_valid_literal(self):
        with pytest.raises(Exception):
            StrategyDefinition(name="x", bot="invalid_bot")

    def test_accepts_stock_bot(self):
        defn = StrategyDefinition(name="x", bot="stock")
        assert defn.bot == "stock"


class TestRegistry:
    def test_register_and_get_schema(self):
        schema = ParamSchema(fields=[
            ParamField(key="x", label="X", type="number", default=1),
        ])
        register("test_bot", schema)
        retrieved = get_schema("test_bot")
        assert retrieved is schema

    def test_get_schema_raises_for_unknown_bot(self):
        with pytest.raises(KeyError, match="no_such_bot"):
            get_schema("no_such_bot")
