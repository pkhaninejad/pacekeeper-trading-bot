"""Tests for Trading212Client behavior."""

import pytest
from unittest.mock import AsyncMock

from src.api.client import Trading212Client


@pytest.mark.asyncio
async def test_get_positions_filters_zero_quantity_rows():
    client = Trading212Client()
    client._get = AsyncMock(return_value=[
        {
            "ticker": "AAPL_US_EQ",
            "quantity": 1.5,
            "averagePrice": 100.0,
            "currentPrice": 101.0,
            "ppl": 1.5,
        },
        {
            "ticker": "FB_US_EQ",
            "quantity": 0.0,
            "averagePrice": 200.0,
            "currentPrice": 199.0,
            "ppl": -1.0,
        },
    ])

    positions = await client.get_positions()

    assert len(positions) == 1
    assert positions[0].ticker == "AAPL_US_EQ"


@pytest.mark.asyncio
async def test_get_positions_uses_max_sell_when_available():
    client = Trading212Client()
    client._get = AsyncMock(return_value=[
        {
            "ticker": "AAPL_US_EQ",
            "quantity": 2.0,
            "maxSell": 0.0,
            "averagePrice": 100.0,
            "currentPrice": 101.0,
            "ppl": 1.5,
        },
        {
            "ticker": "MSFT_US_EQ",
            "quantity": 1.0,
            "maxSell": 1.0,
            "averagePrice": 200.0,
            "currentPrice": 201.0,
            "ppl": 1.0,
        },
    ])

    positions = await client.get_positions()

    assert len(positions) == 1
    assert positions[0].ticker == "MSFT_US_EQ"
