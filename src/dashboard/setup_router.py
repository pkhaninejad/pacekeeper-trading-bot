"""First-run setup API.

Backs the in-dashboard onboarding flow: choose an LLM provider (shared config)
and persist the user's broker/risk choices locally. Pacekeeper is free, so there
is no license check.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from src.bot.llm_config import (
    PROVIDER_DEFAULTS,
    SUPPORTED_PROVIDERS,
    ProviderConfig,
    save_provider_config,
)

SETUP_FILE = Path("data/setup.json")


class SetupPayload(BaseModel):
    t212_key: str = ""
    t212_secret: str = ""
    t212_env: str = "demo"
    risk_profile: str = "balanced"
    # Shared LLM provider config (replaces the per-bot LLM setting).
    llm_provider: str = "anthropic"
    llm_model: str = ""
    llm_api_key: str = ""
    llm_base_url: str = ""


def _save_llm(payload: SetupPayload) -> None:
    """Persist the chosen LLM provider to the shared credentials.json so both
    bots pick it up (no separate per-bot LLM setting needed)."""
    provider = payload.llm_provider
    if provider not in SUPPORTED_PROVIDERS:
        return
    defaults = PROVIDER_DEFAULTS.get(provider, {})
    model = payload.llm_model.strip() or defaults.get("model", "")
    base_url = payload.llm_base_url.strip() or defaults.get("base_url", "")
    # Ollama needs no key; everyone else does — but don't block saving if blank.
    config = ProviderConfig(
        provider=provider, model=model, api_key=payload.llm_api_key.strip(), base_url=base_url
    )
    save_provider_config(config)


def make_setup_router() -> APIRouter:
    router = APIRouter(tags=["setup"])

    @router.get("/setup/status")
    async def setup_status():
        return {"complete": SETUP_FILE.exists()}

    @router.get("/setup/llm-providers")
    async def llm_providers():
        return {
            "providers": [
                {
                    "id": name,
                    "label": name.capitalize(),
                    "model": PROVIDER_DEFAULTS[name].get("model", ""),
                    "base_url": PROVIDER_DEFAULTS[name].get("base_url", ""),
                    "needs_key": name != "ollama",
                }
                for name in SUPPORTED_PROVIDERS
            ]
        }

    @router.post("/setup/save")
    async def save_setup(payload: SetupPayload):
        SETUP_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETUP_FILE.write_text(payload.model_dump_json(indent=2))
        try:
            _save_llm(payload)
        except Exception:
            pass  # bad provider combo shouldn't block completing setup
        return {"saved": True}

    return router
