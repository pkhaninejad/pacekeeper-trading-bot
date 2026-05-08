"""Load and resolve the active LLM provider from prediction_bot/config/llm_providers.json."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import litellm
import openai
from openai import AzureOpenAI

_CONFIG_PATH = Path(__file__).parents[2] / "config" / "llm_providers.json"


@dataclass
class LLMProvider:
    name: str
    litellm_model: str
    api_key: str
    temperature: float
    max_tokens: int
    api_base: str | None = None
    api_version: str | None = None
    provider_type: str | None = None
    # deployment name used with openai SDK (strips provider prefix like "azure/", "openai/")
    deployment: str = field(init=False)

    def __post_init__(self) -> None:
        self.deployment = self.litellm_model.split("/", 1)[-1]

    def complete(self, messages: list[dict]) -> str:
        """Call the model and return the response text."""
        if self.provider_type == "azure_openai":
            return self._complete_azure_openai(messages)
        if self.api_version and self.api_base:
            return self._complete_openai_sdk(messages)
        return self._complete_litellm(messages)

    def _complete_azure_openai(self, messages: list[dict]) -> str:
        """Use AzureOpenAI SDK for classic Azure OpenAI endpoints."""
        client = AzureOpenAI(
            api_key=self.api_key,
            azure_endpoint=self.api_base,
            api_version=self.api_version,
        )
        resp = client.chat.completions.create(
            model=self.deployment,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return resp.choices[0].message.content

    def _complete_openai_sdk(self, messages: list[dict]) -> str:
        """Use openai SDK with default_query for endpoints that require api-version."""
        client = openai.OpenAI(
            api_key=self.api_key,
            base_url=self.api_base,
            default_query={"api-version": self.api_version},
        )
        resp = client.chat.completions.create(
            model=self.deployment,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return resp.choices[0].message.content

    def _complete_litellm(self, messages: list[dict]) -> str:
        kwargs: dict[str, Any] = {
            "model": self.litellm_model,
            "api_key": self.api_key,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if self.api_base:
            kwargs["api_base"] = self.api_base
        resp = litellm.completion(**kwargs)
        return resp.choices[0].message.content


def _resolve(value: str) -> str:
    if isinstance(value, str) and value.startswith("$"):
        return os.environ.get(value[1:], "")
    return value


def load_active_provider() -> LLMProvider:
    with open(_CONFIG_PATH) as f:
        cfg = json.load(f)

    active_name = cfg.get("active", "")
    providers = cfg.get("providers", {})

    if active_name not in providers:
        available = list(providers.keys())
        raise ValueError(f"Active provider '{active_name}' not found. Available: {available}")

    p = providers[active_name]
    return LLMProvider(
        name=active_name,
        litellm_model=p["litellm_model"],
        api_key=_resolve(p.get("api_key", "")),
        temperature=p.get("temperature", 0.3),
        max_tokens=p.get("max_tokens", 2048),
        api_base=p.get("api_base"),
        api_version=p.get("api_version"),
        provider_type=p.get("provider_type"),
    )
