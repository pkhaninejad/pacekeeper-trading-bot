"""Abstract base class for prediction market platform clients."""
from __future__ import annotations

from abc import ABC, abstractmethod

from prediction_bot.src.api.models import PredictionMarket


class PredictionMarketClient(ABC):
    platform: str

    @abstractmethod
    async def get_near_expiry_markets(
        self,
        hours: int = 48,
        min_liquidity: float = 1000.0,
        limit: int = 500,
    ) -> list[PredictionMarket]: ...

    @abstractmethod
    async def get_market_status(self, market_id: str) -> dict: ...

    @abstractmethod
    async def __aenter__(self) -> "PredictionMarketClient": ...

    @abstractmethod
    async def __aexit__(self, *_) -> None: ...
