from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ParamField(BaseModel):
    key: str
    label: str
    type: Literal["number", "percent", "select", "bool", "text"]
    default: float | str | bool | None = None
    min: float | None = None
    max: float | None = None
    help: str = ""
    step: int = 1
    options: list[str] | None = None


class ParamSchema(BaseModel):
    fields: list[ParamField]

    def fill_defaults(self, params: dict) -> dict:
        result = {}
        for field in self.fields:
            result[field.key] = params.get(field.key, field.default)
        return result

    def validate_params(self, params: dict) -> None:
        for field in self.fields:
            if field.key not in params:
                continue
            val = params[field.key]
            if field.type in ("number", "percent"):
                if field.min is not None and val < field.min:
                    raise ValueError(f"{field.key}: {val} < min {field.min}")
                if field.max is not None and val > field.max:
                    raise ValueError(f"{field.key}: {val} > max {field.max}")
            if field.type == "select" and field.options and val not in field.options:
                raise ValueError(f"{field.key}: {val!r} not in {field.options}")


class StrategyDefinition(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    bot: Literal["prediction", "stock"]
    params: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    archived: bool = False
