"""Tests for live positions behavior in dashboard API."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.models import Position
from src.dashboard import app as dashboard_app


def make_position(**kwargs) -> Position:
    defaults = dict(
        ticker="AAPL_US_EQ",
        quantity=1.0,
        averagePrice=100.0,
        currentPrice=101.0,
        ppl=1.0,
    )
    defaults.update(kwargs)
    return Position(**defaults)


def make_mock_client(positions):
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.get_positions = AsyncMock(return_value=positions)
    return client


@pytest.mark.asyncio
async def test_get_positions_ignores_positions_cache():
    dashboard_app._cache["positions"] = {
        "data": [{"ticker": "STALE_US_EQ"}],
        "ts": dashboard_app.datetime.utcnow(),
    }
    dashboard_app._recently_closed.clear()

    mock_client = make_mock_client([make_position(ticker="AAPL_US_EQ")])
    with patch("src.dashboard.app.Trading212Client", return_value=mock_client):
        data = await dashboard_app.get_positions()

    assert len(data) == 1
    assert data[0]["ticker"] == "AAPL_US_EQ"


@pytest.mark.asyncio
async def test_get_positions_hides_recently_closed_ticker():
    dashboard_app._cache.clear()
    dashboard_app._recently_closed.clear()
    dashboard_app._mark_recently_closed("AAPL")

    positions = [
        make_position(ticker="AAPL_US_EQ"),
        make_position(ticker="MSFT_US_EQ"),
    ]
    mock_client = make_mock_client(positions)
    with patch("src.dashboard.app.Trading212Client", return_value=mock_client):
        data = await dashboard_app.get_positions()

    assert len(data) == 1
    assert data[0]["ticker"] == "MSFT_US_EQ"
