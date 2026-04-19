# Ticket 4: Market Scanner — Design Spec

**Date:** 2026-04-17
**Status:** Draft
**Master Spec:** [prediction-market-bot-design.md](2026-04-17-prediction-market-bot-design.md)
**Depends on:** Ticket 2 (Polymarket client), Ticket 3 (Kalshi client)

---

## Goal

Scan both platforms for near-expiry, high-probability markets across the 3 enabled categories. Produce a ranked list of `MarketCandidate` objects ready for LLM evaluation.

---

## New File: `prediction_bot/src/bot/scanner.py`

### Function: `scan_markets`

```python
async def scan_markets(
    polymarket: PolymarketClient | None,
    kalshi: KalshiClient | None,
    settings: PredictionBotSettings,
) -> list[MarketCandidate]:
    """
    Scan both platforms for high-probability near-expiry markets.

    Filters applied in order:
    1. Active + not closed
    2. Expiring within EXPIRY_WINDOW_HOURS
    3. Category in ENABLED_CATEGORIES
    4. Liquidity >= MIN_LIQUIDITY
    5. Best side (YES or NO) price in [HIGH_PROB_MIN, HIGH_PROB_MAX]
    6. Rank by: edge_potential = (1.0 - best_price) * liquidity_score

    Returns sorted list of MarketCandidate (best first), capped at 50.
    """
```

### Filtering Pipeline

```
All active markets (both platforms)
  → Filter: end_date within EXPIRY_WINDOW_HOURS from now
  → Filter: category matches ENABLED_CATEGORIES
  → Filter: liquidity >= MIN_LIQUIDITY
  → For each market:
      best_side = "YES" if yes_price >= no_price else "NO"
      best_price = max(yes_price, no_price)
  → Filter: HIGH_PROB_MIN <= best_price <= HIGH_PROB_MAX
  → Score: edge_potential = (1.0 - best_price) * log(liquidity + 1)
  → Sort by edge_potential descending
  → Return top 50
```

### Category Detection

```python
def classify_market(market: PredictionMarket) -> str | None:
    """Classify a market into crypto/sports/politics based on platform metadata + keyword matching."""

    # 1. Platform-provided tags (Polymarket tags, Kalshi series)
    if market.metadata.get("tags"):
        for tag in market.metadata["tags"]:
            if matches_category(tag):
                return category

    # 2. Keyword matching on question text (fallback)
    question = market.question.lower()
    CRYPTO_KEYWORDS = ["bitcoin", "btc", "ethereum", "eth", "crypto", "token", "defi", "binance"]
    SPORTS_KEYWORDS = ["win", "score", "game", "match", "nfl", "nba", "mlb", "championship", "series"]
    POLITICS_KEYWORDS = ["president", "congress", "senate", "election", "vote", "bill", "law", "supreme court"]

    # Score by keyword matches; return category with most matches; None if no matches
```

### Deduplication

Same event may appear on both platforms. Deduplicate by question similarity:
- Normalize question text (lowercase, strip punctuation)
- If two markets from different platforms have >80% token overlap, keep the one with higher liquidity

### Caching

- **5-minute cache** on scan results (keyed by settings hash)
- Prevents redundant API calls within a cycle

---

## Data Flow

```
scanner.scan_markets()
  → polymarket.get_near_expiry_markets(hours, min_liquidity)
  → kalshi.get_near_expiry_markets(hours, min_volume)
  → combine results
  → classify_market() for each
  → filter by category, price range
  → deduplicate cross-platform
  → score and rank
  → return top 50 MarketCandidate
```

---

## Testing

`prediction_bot/tests/test_scanner.py`:

- `test_filters_by_expiry` — markets outside window excluded
- `test_filters_by_liquidity` — low-liquidity markets excluded
- `test_filters_by_price_range` — too cheap or too expensive excluded
- `test_best_side_selection` — picks YES or NO correctly
- `test_category_classification` — crypto/sports/politics detected
- `test_category_filter` — only enabled categories pass
- `test_cross_platform_dedup` — same event from both platforms deduped
- `test_ranking` — higher edge_potential ranked first
- `test_single_platform` — works with only Polymarket (Kalshi disabled)
- `test_empty_results` — no markets match → empty list

---

## Acceptance Criteria

- [ ] Scans both platforms (gracefully handles one being disabled)
- [ ] Filters by expiry, liquidity, price range, and category
- [ ] Classifies markets into crypto/sports/politics
- [ ] Deduplicates cross-platform
- [ ] Returns ranked `MarketCandidate` list
- [ ] 5-minute cache prevents redundant API calls
