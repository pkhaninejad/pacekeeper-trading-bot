from pydantic import AliasChoices, BaseModel, Field
from typing import Optional, Literal, Union
from datetime import datetime


class AccountInfo(BaseModel):
    id: Union[str, int]
    currencyCode: str
    type: Optional[str] = None


class CashInfo(BaseModel):
    free: float
    total: float
    ppl: float
    result: float
    invested: float
    pieCash: float


class Position(BaseModel):
    ticker: str
    quantity: float
    averagePrice: float
    currentPrice: float
    ppl: float
    fxPpl: Optional[float] = None
    initialFillDate: Optional[str] = None
    frontend: Optional[str] = None
    maxBuy: Optional[float] = None
    maxSell: Optional[float] = None
    pieQuantity: Optional[float] = None

    @property
    def pnl_pct(self) -> float:
        if self.averagePrice == 0:
            return 0.0
        return ((self.currentPrice - self.averagePrice) / self.averagePrice) * 100

    @property
    def is_long(self) -> bool:
        return self.quantity > 0

    @property
    def is_short(self) -> bool:
        return self.quantity < 0

    @property
    def market_value(self) -> float:
        return abs(self.quantity) * self.currentPrice


class Order(BaseModel):
    id: int
    creationTime: Optional[str] = None
    modifiedTime: Optional[str] = None
    executor: Optional[str] = None
    orderedQuantity: float = Field(validation_alias=AliasChoices("orderedQuantity", "quantity"))
    filledQuantity: Optional[float] = None
    ticker: str
    limitPrice: Optional[float] = None
    stopPrice: Optional[float] = None
    status: Optional[str] = None
    type: Optional[str] = None
    timeValidity: Optional[str] = None


class Instrument(BaseModel):
    ticker: str
    name: str
    type: Optional[str] = None
    currencyCode: Optional[str] = None
    isin: Optional[str] = None
    minTradeQuantity: Optional[float] = None
    maxOpenQuantity: Optional[float] = None


class MarketOrderRequest(BaseModel):
    ticker: str
    quantity: float


class LimitOrderRequest(BaseModel):
    ticker: str
    quantity: float
    limitPrice: float
    timeValidity: Literal["DAY", "GOOD_TILL_CANCEL"] = "DAY"


class StopOrderRequest(BaseModel):
    ticker: str
    quantity: float
    stopPrice: float
    timeValidity: Literal["DAY", "GOOD_TILL_CANCEL"] = "DAY"


class TradeSignal(BaseModel):
    ticker: str
    action: Literal["BUY", "SELL", "HOLD"]
    direction: Literal["LONG", "SHORT", "CLOSE"]
    confidence: float          # 0.0 – 1.0
    reasoning: str
    suggested_quantity: Optional[float] = None
    suggested_price: Optional[float] = None
    order_type: Literal["MARKET", "LIMIT", "STOP"] = "MARKET"
    timestamp: datetime = None

    def model_post_init(self, __context):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class BotStatus(BaseModel):
    enabled: bool
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    total_trades_today: int = 0
    total_pnl: float = 0.0
    open_positions: int = 0
    signals_generated: int = 0
    environment: str = "demo"
    market_open: bool = False
    next_market_open: Optional[datetime] = None
    market_regime: Optional[str] = None
    vix: Optional[float] = None


class TradeOutcome(BaseModel):
    ticker: str
    action: str                    # "BUY" or "SELL"
    direction: str                 # "LONG" or "SHORT"
    confidence: float
    outcome: Literal["TP_HIT", "SL_HIT", "MANUAL_CLOSE", "OPEN"] = "OPEN"
    pnl_pct: Optional[float] = None
    opened_at: datetime
    closed_at: Optional[datetime] = None
