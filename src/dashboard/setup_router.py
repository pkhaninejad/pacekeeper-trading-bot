"""First-run setup + license activation API.

Backs the in-dashboard onboarding flow: validate a license against the
WordPress/WooCommerce license server (same contract as the desktop app and
service-map), and persist the user's broker/AI/risk choices locally.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

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
    anthropic_key: str = ""
    risk_profile: str = "balanced"


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


def make_setup_router() -> APIRouter:
    router = APIRouter(tags=["setup"])

    @router.get("/setup/status")
    async def setup_status():
        return {"complete": SETUP_FILE.exists(), "licensed": _read_license().get("valid", False)}

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
        return {"saved": True}

    return router
