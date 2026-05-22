from __future__ import annotations

from strategy_kit.models import ParamSchema

_registry: dict[str, ParamSchema] = {}


def register(bot: str, schema: ParamSchema) -> None:
    _registry[bot] = schema


def get_schema(bot: str) -> ParamSchema:
    if bot not in _registry:
        raise KeyError(f"No schema registered for bot: {bot!r}")
    return _registry[bot]
