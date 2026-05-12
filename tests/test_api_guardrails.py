"""Tests for /api/bot/emergency-stop and /api/mode/live/confirm endpoints."""
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.dashboard import app as dashboard_app


# ---------------------------------------------------------------------------
# /api/bot/emergency-stop
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_emergency_stop_endpoint_halts_engine():
    dashboard_app.engine.status.enabled = True
    dashboard_app.engine.status.halted_reason = None

    async def fake_emergency_stop():
        dashboard_app.engine.status.enabled = False
        dashboard_app.engine.status.halted_reason = "emergency_stop"
        return {"halted": True, "positions_closed": 0}

    with patch.object(dashboard_app.engine, "emergency_stop", side_effect=fake_emergency_stop):
        result = await dashboard_app.emergency_stop_bot()

    assert result["halted"] is True
    assert dashboard_app.engine.status.enabled is False


# ---------------------------------------------------------------------------
# /api/mode/live/confirm
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_confirm_live_mode_writes_file(tmp_path):
    from src.dashboard.app import LiveConfirmRequest

    req = LiveConfirmRequest(checks=[True, True, True, True, True])

    with patch("src.dashboard.app.CONFIRMED_FILE", tmp_path / "live_confirmed.json"):
        result = await dashboard_app.confirm_live_mode(req)

    assert result["confirmed"] is True
    saved = json.loads((tmp_path / "live_confirmed.json").read_text())
    assert saved["confirmed"] is True
    assert "confirmed_at" in saved


@pytest.mark.asyncio
async def test_confirm_live_mode_rejects_incomplete_checks():
    from src.dashboard.app import LiveConfirmRequest
    from fastapi import HTTPException

    req = LiveConfirmRequest(checks=[True, True, False, True, True])

    with pytest.raises(HTTPException) as exc_info:
        await dashboard_app.confirm_live_mode(req)

    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_confirm_live_mode_rejects_wrong_count():
    from src.dashboard.app import LiveConfirmRequest
    from fastapi import HTTPException

    req = LiveConfirmRequest(checks=[True, True, True])

    with pytest.raises(HTTPException) as exc_info:
        await dashboard_app.confirm_live_mode(req)

    assert exc_info.value.status_code == 422
