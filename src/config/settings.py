import os
from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    # Trading212 API
    T212_API_KEY: str = ""
    T212_API_SECRET: str = ""
    T212_ENV: Literal["demo", "live"] = "demo"

    # Anthropic
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-sonnet-4-6"

    # Bot behaviour
    BOT_ENABLED: bool = True
    TRADE_INTERVAL_SECONDS: int = 300       # How often the bot evaluates (5 min)
    MAX_POSITION_SIZE_PCT: float = 0.05     # Max 5% of portfolio per trade
    MAX_OPEN_POSITIONS: int = 10
    STOP_LOSS_PCT: float = 0.02             # 2% stop-loss
    TAKE_PROFIT_PCT: float = 0.04           # 4% take-profit
    WATCHLIST: list[str] = [
        "AAPL", "TSLA", "NVDA", "MSFT", "AMZN", "GOOGL", "META", "NFLX"
    ]

    # Dashboard
    DASHBOARD_HOST: str = "0.0.0.0"
    DASHBOARD_PORT: int = 8080
    SECRET_KEY: str = "change-me-in-production"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def t212_base_url(self) -> str:
        return (
            "https://demo.trading212.com/api/v0"
            if self.T212_ENV == "demo"
            else "https://live.trading212.com/api/v0"
        )


settings = Settings()
