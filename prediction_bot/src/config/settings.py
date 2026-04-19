from pydantic_settings import BaseSettings, SettingsConfigDict


class PredictionBotSettings(BaseSettings):
    POLYMARKET_ENABLED: bool = True
    KALSHI_ENABLED: bool = True
    KALSHI_API_KEY: str = ""
    KALSHI_API_SECRET: str = ""
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-sonnet-4-6"
    SCAN_INTERVAL_SECONDS: int = 120
    EXPIRY_WINDOW_HOURS: int = 48
    HIGH_PROB_MIN: float = 0.80
    HIGH_PROB_MAX: float = 0.97
    MIN_LIQUIDITY: float = 1000.0
    MIN_EDGE_PCT: float = 0.02
    ENABLED_CATEGORIES: list[str] = ["crypto", "sports", "politics"]
    VIRTUAL_BANKROLL: float = 1000.0
    MAX_POSITION_PCT: float = 0.10
    MAX_OPEN_POSITIONS: int = 20
    PM_DB_PATH: str = "prediction_bot/data/paper_trades.db"
    PM_DASHBOARD_PORT: int = 4001

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


pm_settings = PredictionBotSettings()
