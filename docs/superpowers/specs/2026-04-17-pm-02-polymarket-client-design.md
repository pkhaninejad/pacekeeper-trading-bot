# Ticket 2: Polymarket API Client — Design Spec

**Date:** 2026-04-17
**Status:** Draft
**Master Spec:** [prediction-market-bot-design.md](2026-04-17-prediction-market-bot-design.md)
**Depends on:** Ticket 1 (scaffold)

---

## Goal

Async HTTP client for Polymarket's Gamma API (read-only market data). No trading needed for paper trading — we only need to fetch markets, prices, and resolution status.

---

## New File: `prediction_bot/src/api/polymarket_client.py`

### Class: `PolymarketClient`

Async context manager pattern (matches existing `Trading212Client`).

```python
class PolymarketClient:
    BASE_URL = "https://gamma-api.polymarket.com"

    async def get_active_markets(
        self,
        limit: int = 100,
        offset: int = 0,
        order: str = "volume_24hr",
        tag_id: int | None = None,
    ) -> list[PredictionMarket]:
        """Fetch active, non-closed markets from Gamma API."""

    async def get_market_by_slug(self, slug: str) -> PredictionMarket | None:
        """Fetch a single market by slug."""

    async def get_events_by_tag(self, tag_id: int, limit: int = 50) -> list[PredictionMarket]:
        """Fetch events filtered by tag (sports, politics, etc.)."""

    async def get_sports_tags(self) -> list[dict]:
        """Fetch available sports tags and metadata."""

    async def get_all_tags(self) -> list[dict]:
        """Fetch all available category tags."""

    async def get_market_status(self, condition_id: str) -> dict:
        """Check if a market has resolved (for settling paper trades)."""

    async def get_near_expiry_markets(
        self,
        hours: int = 48,
        min_liquidity: float = 1000.0,
        limit: int = 200,
    ) -> list[PredictionMarket]:
        """Scan for markets expiring within N hours with minimum liquidity."""
```

### API Endpoints Used

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/events?active=true&closed=false&limit=N&offset=N` | Fetch all active events |
| GET | `/markets?active=true&closed=false&limit=N` | Fetch active markets |
| GET | `/markets?slug=X` | Fetch by slug |
| GET | `/events?tag_id=N&active=true&closed=false` | Filter by category |
| GET | `/tags` | List all category tags |
| GET | `/sports` | Sports-specific tags |
| GET | `/markets/ID` | Single market details (check resolution) |

### Category Mapping

Map Polymarket tags to our 3 categories:

```python
TAG_CATEGORY_MAP = {
    "crypto": ["crypto", "bitcoin", "ethereum", "defi"],
    "sports": [],          # dynamically from /sports endpoint
    "politics": ["politics", "elections", "congress", "government"],
}
```

Sports tags are loaded dynamically via `get_sports_tags()` on first call and cached.

### Rate Limiting

- Gamma API is public, no auth needed
- Implement 0.5s delay between requests (polite crawling)
- Retry on 429 with exponential backoff (same pattern as `Trading212Client`)

### Price Extraction

From Polymarket response JSON:
```python
outcome_prices = json.loads(market_data["outcomePrices"])
yes_price = float(outcome_prices[0])
no_price = float(outcome_prices[1])
```

### Resolution Detection

A market is resolved when `closed=true` and outcomes have settled. Check:
- `market["closed"]` → True
- `market["outcomePrices"]` → one side is ~1.0, other is ~0.0

---

## Caching

- **Tag list:** Cache indefinitely per process (tags don't change often)
- **Market data:** No cache (prices change rapidly); caller handles cache if needed

---

## Testing

`prediction_bot/tests/test_polymarket_client.py`:

- `test_get_active_markets` — mock HTTP, verify PredictionMarket parsing
- `test_get_near_expiry_markets` — verify time filtering logic
- `test_price_extraction` — verify YES/NO price parsing from raw JSON
- `test_category_mapping` — verify tag → category mapping
- `test_resolution_detection` — verify closed market detection
- `test_rate_limiting` — verify delay between requests
- `test_pagination` — verify offset/limit handling

---

## Acceptance Criteria

- [ ] Can fetch all active markets from Polymarket
- [ ] Can filter by category (crypto, sports, politics)
- [ ] Can filter by expiry window (< N hours)
- [ ] Can detect resolved markets for paper trade settlement
- [ ] Rate-limited and retry-enabled
- [ ] All methods return `PredictionMarket` model objects
