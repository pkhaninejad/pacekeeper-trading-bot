from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel


class PredictionMarket(BaseModel):
    id: str
    platform: str
    question: str
    category: str
    end_date: datetime
    yes_price: float
    no_price: float
    volume_24h: float = 0.0
    liquidity: float = 0.0
    slug: str = ""
    metadata: dict = {}


class MarketCandidate(BaseModel):
    market: PredictionMarket
    best_side: str
    market_price: float
    external_data: dict = {}
    llm_true_prob: float | None = None
    llm_confidence: float | None = None
    llm_reasoning: str | None = None
    edge: float | None = None


class PaperTrade(BaseModel):
    id: int | None = None
    platform: str
    market_id: str
    market_question: str
    category: str
    side: str
    entry_price: float
    quantity: float
    cost: float
    confidence: float
    reasoning: str | None = None
    status: str = "OPEN"
    exit_price: float | None = None
    pnl: float | None = None
    created_at: datetime
    end_date: datetime | None = None
    resolved_at: datetime | None = None
    resolution_source: str | None = None


class BankrollSnapshot(BaseModel):
    id: int | None = None
    balance: float
    timestamp: datetime
    trade_id: int | None = None


class PMBotStatus(BaseModel):
    enabled: bool = False
    platforms: dict = {"polymarket": True, "kalshi": False}
    categories: list[str] = ["crypto", "sports", "politics"]
    open_trades: int = 0
    bankroll: float = 1000.0
    total_pnl: float = 0.0
    win_rate: float | None = None
    last_scan: datetime | None = None
    next_scan: datetime | None = None
