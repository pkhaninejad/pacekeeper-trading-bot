# Ticket 3: Kalshi API Client — Design Spec

**Date:** 2026-04-17
**Status:** Draft
**Master Spec:** [prediction-market-bot-design.md](2026-04-17-prediction-market-bot-design.md)
**Depends on:** Ticket 1 (scaffold)

---

## Goal

Async HTTP client for Kalshi's Exchange API. Kalshi requires authentication for market data beyond basics. For paper trading we need: market listing, price data, and resolution status.

---

## New File: `prediction_bot/src/api/kalshi_client.py`

### Class: `KalshiClient`

```python
class KalshiClient:
    BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
    # Note: Kalshi has migrated APIs; v2 is current

    async def login(self) -> str:
        """Authenticate with API key + secret, return session token."""

    async def get_events(
        self,
        status: str = "open",
        series_ticker: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> tuple[list[dict], str | None]:
        """Fetch events. Returns (events, next_cursor)."""

    async def get_markets(
        self,
        event_ticker: str | None = None,
        status: str = "open",
        limit: int = 100,
        cursor: str | None = None,
    ) -> tuple[list[PredictionMarket], str | None]:
        """Fetch markets, optionally filtered by event."""

    async def get_market(self, ticker: str) -> PredictionMarket:
        """Fetch single market by ticker."""

    async def get_market_orderbook(self, ticker: str) -> dict:
        """Fetch orderbook for a market (bid/ask depth)."""

    async def get_near_expiry_markets(
        self,
        hours: int = 48,
        min_volume: float = 1000.0,
        limit: int = 200,
    ) -> list[PredictionMarket]:
        """Scan for markets expiring within N hours."""
```

### API Endpoints Used

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/log-in` | Get session token (API key + secret) |
| GET | `/events` | List events (filterable by status, series) |
| GET | `/events/{event_ticker}` | Single event details |
| GET | `/markets` | List markets (filterable by event, status) |
| GET | `/markets/{ticker}` | Single market details + resolution |
| GET | `/markets/{ticker}/orderbook` | Bid/ask depth |

### Authentication

Kalshi uses API key authentication:
```python
headers = {
    "Authorization": f"Bearer {session_token}",
    "Content-Type": "application/json",
}
```

Login: POST `/log-in` with `{"email": key, "password": secret}` → returns token.
Token cached for session lifetime, refresh on 401.

### Category Mapping

Kalshi organizes by "series" (event groups):

```python
SERIES_CATEGORY_MAP = {
    "crypto": ["BITCOIN", "ETHEREUM", "CRYPTO"],
    "sports": ["NFL", "NBA", "MLB", "NHL", "SOCCER", "TENNIS"],
    "politics": ["CONGRESS", "PRESIDENT", "SCOTUS", "ELECTIONS", "GOVERNMENT"],
}
```

Map series tickers to categories by prefix matching.

### Price Extraction

Kalshi markets have `yes_bid`, `yes_ask`, `no_bid`, `no_ask`:
```python
yes_price = (market["yes_bid"] + market["yes_ask"]) / 2 / 100  # Kalshi uses cents
no_price = (market["no_bid"] + market["no_ask"]) / 2 / 100
```

### Resolution Detection

```python
# Market is settled when:
market["status"] == "settled"  # or "finalized"
market["result"] == "yes"  # or "no"
```

### Rate Limiting

- Kalshi rate limits: 10 req/sec for authenticated endpoints
- Implement 0.2s delay between requests
- Retry on 429 with exponential backoff

---

## Graceful Degradation

If `KALSHI_ENABLED=false` or credentials are missing, `KalshiClient` methods return empty lists. The scanner treats Kalshi as optional.

---

## Testing

`prediction_bot/tests/test_kalshi_client.py`:

- `test_login` — mock auth, verify token caching
- `test_get_markets` — mock response, verify PredictionMarket parsing
- `test_get_near_expiry_markets` — verify time + volume filtering
- `test_price_extraction_cents` — verify cent-to-dollar conversion
- `test_resolution_detection` — verify settled market detection
- `test_disabled_returns_empty` — when disabled, returns []
- `test_pagination_cursor` — verify cursor-based pagination

---

## Acceptance Criteria

- [ ] Authenticates with Kalshi API
- [ ] Can fetch markets filtered by category and expiry
- [ ] Can detect resolved markets for settlement
- [ ] Gracefully disabled when credentials missing
- [ ] Returns same `PredictionMarket` model as Polymarket client
