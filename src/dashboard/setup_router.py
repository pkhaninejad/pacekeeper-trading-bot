"""First-run setup + license activation API.

Backs the in-dashboard onboarding flow: validate a license against the
WordPress/WooCommerce license server (same contract as the desktop app and
service-map), choose an LLM provider (shared config), and persist the user's
broker/risk choices locally.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from src.bot.llm_config import (
    PROVIDER_DEFAULTS,
    SUPPORTED_PROVIDERS,
    ProviderConfig,
    save_provider_config,
)

LICENSE_SERVER_URL = os.environ.get(
    "LICENSE_SERVER_URL", "https://wallstrdev.com/wp-json/wds-license/v1/validate"
)
PRODUCT_DOMAIN = "pacekeeper-desktop"
SETUP_FILE = Path("data/setup.json")
LICENSE_CACHE = Path("data/license_cache.json")


class LicensePayload(BaseModel):
    key: str


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


async def _validate_remote(key: str) -> dict | None:
    """POST {key, domain} to the license server. None on network/parse failure."""
    if not key:
        return {"valid": False, "reason": "Enter your license key."}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                LICENSE_SERVER_URL, json={"key": key, "domain": PRODUCT_DOMAIN}
            )
            body = r.json()
        if not isinstance(body, dict):
            return None
        return {
            "valid": bool(body.get("valid")),
            "tier": body.get("tier", "free"),
            "expires": body.get("expires"),
            "reason": body.get("reason"),
        }
    except Exception:
        return None


def _read_license() -> dict:
    try:
        return json.loads(LICENSE_CACHE.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"valid": False}


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
        return {"complete": SETUP_FILE.exists(), "licensed": _read_license().get("valid", False)}

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

    @router.post("/license/activate")
    async def activate_license(payload: LicensePayload):
        result = await _validate_remote(payload.key.strip())
        if result is None:
            return {"valid": False, "reason": "Could not reach the license server. Check your connection."}
        LICENSE_CACHE.parent.mkdir(parents=True, exist_ok=True)
        LICENSE_CACHE.write_text(json.dumps({**result, "key": payload.key.strip()}))
        return result

    @router.get("/license/status")
    async def license_status():
        return _read_license()

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
