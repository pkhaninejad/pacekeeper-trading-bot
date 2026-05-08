# Ticket 5: LLM Evaluator — Design Spec

**Date:** 2026-04-17
**Status:** Draft
**Master Spec:** [prediction-market-bot-design.md](2026-04-17-prediction-market-bot-design.md)
**Depends on:** Ticket 1 (scaffold)

---

## Goal

Send market candidates + external enrichment data to Claude and get back a true probability estimate, confidence score, and reasoning. This is the core decision-making module.

---

## New File: `prediction_bot/src/bot/evaluator.py`

### Function: `evaluate_candidates`

```python
async def evaluate_candidates(
    candidates: list[MarketCandidate],
    settings: PredictionBotSettings,
) -> list[MarketCandidate]:
    """
    Send candidates to LLM for probability assessment.
    Updates each candidate's llm_true_prob, llm_confidence, llm_reasoning, and edge.
    Returns only candidates where edge > MIN_EDGE_PCT.
    """
```

### System Prompt

```
You are a prediction market analyst. For each market, assess the TRUE probability
of the specified outcome based on:
1. The market question and resolution criteria
2. The current market price (what the crowd thinks)
3. Any external data provided (prices, scores, news, schedules)
4. Your general knowledge up to your training cutoff

Be calibrated. If the crowd price seems correct, say so. Only flag edge when
you have genuine reasons to believe the true probability differs from market price.

Respond with a JSON array. For each market:
{
  "market_id": "...",
  "true_probability": 0.95,     // your estimate of the true probability
  "confidence": 0.85,           // how confident you are in your estimate (0-1)
  "reasoning": "Short explanation of why you disagree with market price (or agree)",
  "recommended_side": "YES"     // or "NO" or "SKIP"
}
```

### User Prompt Template

```
=== CANDIDATES TO EVALUATE ===

Market 1: "{question}"
  Platform: {platform}
  Category: {category}
  Expires: {end_date} ({hours_remaining}h from now)
  Current YES price: ${yes_price} | NO price: ${no_price}
  Our best side: {best_side} at ${best_price}
  24h Volume: ${volume_24h} | Liquidity: ${liquidity}
  Resolution criteria: {description_snippet}

  External data:
  {enrichment_data}

Market 2: ...
(repeat for up to 10 candidates per batch)

=== INSTRUCTIONS ===
For each market, estimate the TRUE probability of YES.
If true_prob > market YES price → recommend YES.
If (1 - true_prob) > market NO price → recommend NO.
If edge < 2% → recommend SKIP.
Only recommend when you have specific reasoning, not just vibes.
```

### External Data Enrichment

Before calling the LLM, enrich each candidate with category-specific data:

```python
async def enrich_candidate(candidate: MarketCandidate) -> MarketCandidate:
    """Add external data based on category."""

    if candidate.market.category == "crypto":
        # Fetch current price from CoinGecko (free, no auth)
        # If question mentions BTC price target, include current BTC price
        # If question mentions protocol upgrade, include recent news

    elif candidate.market.category == "sports":
        # If live game: fetch current score from ESPN
        # If series: fetch series record
        # If player stat: fetch current game stats

    elif candidate.market.category == "politics":
        # Fetch recent headlines about the topic
        # If bill/vote: check congressional schedule
```

### New File: `prediction_bot/src/data/market_data.py`

```python
async def get_crypto_price(symbol: str) -> dict | None:
    """Fetch current price from CoinGecko API (free tier)."""

async def get_crypto_context(question: str) -> str:
    """Extract crypto-relevant context for a market question."""

async def get_sports_scores(query: str) -> str:
    """Fetch live scores / recent results from ESPN API."""

async def get_news_headlines(query: str, max_results: int = 5) -> str:
    """Fetch recent headlines from news API."""
```

### Batching

- Send up to 10 candidates per LLM call
- If > 10 candidates, split into batches
- Each batch is a separate LLM call (sequential, not parallel — respect rate limits)

### Edge Calculation

After LLM response:
```python
for candidate in candidates:
    if recommended_side == "YES":
        edge = llm_true_prob - market.yes_price
    elif recommended_side == "NO":
        edge = (1.0 - llm_true_prob) - market.no_price
    else:
        edge = 0.0

    # Subtract estimated fees (~1-2% for Polymarket, ~2-3% for Kalshi)
    fee_estimate = 0.02 if candidate.market.platform == "polymarket" else 0.03
    candidate.edge = edge - fee_estimate
```

### LLM Call

Uses LiteLLM (same as existing stock bot) for provider flexibility:
```python
response = await litellm.acompletion(
    model=settings.CLAUDE_MODEL,
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ],
    max_tokens=2048,
    temperature=0.3,  # Lower temp for more calibrated estimates
)
```

---

## Testing

`prediction_bot/tests/test_evaluator.py`:

- `test_parse_llm_response` — verify JSON parsing from LLM output
- `test_edge_calculation_yes_side` — edge = true_prob - yes_price - fees
- `test_edge_calculation_no_side` — edge = (1-true_prob) - no_price - fees
- `test_skip_recommendation` — SKIP when edge < MIN_EDGE_PCT
- `test_batch_splitting` — >10 candidates split into batches
- `test_enrichment_crypto` — crypto market gets price data
- `test_enrichment_sports` — sports market gets score data
- `test_enrichment_politics` — politics market gets headline data
- `test_malformed_llm_response` — graceful handling of bad JSON

---

## Acceptance Criteria

- [ ] Enriches candidates with external data per category
- [ ] Sends batched candidates to Claude with structured prompt
- [ ] Parses LLM response into probability + confidence + reasoning
- [ ] Calculates edge (true_prob - market_price - fees)
- [ ] Filters for edge > MIN_EDGE_PCT
- [ ] Returns updated `MarketCandidate` list
