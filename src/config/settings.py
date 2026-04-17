import os
from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    # Trading212 API
    T212_API_KEY: str = ""
    T212_API_SECRET: str = ""
    T212_ENV: Literal["demo", "live"] = "demo"
    T212_ACCOUNT_TYPE: Literal["invest", "cfd"] = "invest"

    # Anthropic (default provider)
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-sonnet-4-6"

    # Additional LLM provider keys (used as fallback if credentials.json absent)
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""
    QWEN_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # Bot behaviour
    BOT_ENABLED: bool = True
    SKIP_MARKET_HOURS_CHECK: bool = False   # Set True to trade outside NYSE hours (testing)
    TRADE_INTERVAL_SECONDS: int = 300       # How often the bot evaluates (5 min)
    MAX_POSITION_SIZE_PCT: float = 0.05     # Max 5% of portfolio per trade
    MAX_OPEN_POSITIONS: int = 10
    STOP_LOSS_PCT: float = 0.02             # 2% stop-loss
    TAKE_PROFIT_PCT: float = 0.04           # 4% take-profit
    WATCHLIST: list[str] = [
        "AAPL", "TSLA", "NVDA", "MSFT", "AMZN", "GOOGL", "META", "NFLX",
        "AMD", "JPM", "V", "UBER", "PLTR"
    ]

    # Earnings calendar
    EARNINGS_DAYS_BEFORE: int = 2           # days before earnings to block new positions
    EARNINGS_DAYS_AFTER: int = 1            # days after earnings to stop blocking
    BLOCK_NEW_POSITIONS_ON_EARNINGS: bool = True
    FINNHUB_API_KEY: str = ""               # optional; enables Finnhub fallback

    # Macro economic calendar
    MACRO_BLOCK_HOURS: int = 12             # block new positions within N hours of HIGH-impact event
    BLOCK_NEW_POSITIONS_ON_MACRO: bool = True

    # News feed
    NEWS_API_KEY: str = ""                  # optional NewsAPI.org fallback
    NEWS_LOOKBACK_DAYS: int = 3             # filter headlines older than N days
    NEWS_MAX_HEADLINES_PER_TICKER: int = 5  # cap per ticker per cycle
    NEWS_CACHE_TTL_SECONDS: int = 900       # 15-minute default

    # Prediction markets
    KALSHI_API_KEY: str = ""               # required for Kalshi fetches; skip silently if absent
    PREDICTION_MARKETS_CACHE_TTL: int = 900  # seconds; shared for Polymarket + Kalshi

    # Dashboard
    DASHBOARD_HOST: str = "0.0.0.0"
    DASHBOARD_PORT: int = 4000
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

    @property
    def account_path_prefix(self) -> str:
        # Trading212's public API v0 only exposes Invest/ISA endpoints under /equity.
        # CFD accounts are not supported by the official REST API.
        return "/equity"


settings = Settings()
