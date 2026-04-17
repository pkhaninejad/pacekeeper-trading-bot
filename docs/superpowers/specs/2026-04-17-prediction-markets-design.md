# Prediction Markets Signal Context

**Date:** 2026-04-17
**Status:** Approved

## Overview

Inject prediction market probabilities from Polymarket (macro events) and Kalshi (ticker-specific events) as a new `=== PREDICTION MARKETS ===` context section in the LLM prompt. Claude reasons over the probabilities alongside existing signals (news, macro calendar, price feed). No hard-wired thresholds — the LLM decides how much weight to give them.

## Data Layer

### New file: `src/data/prediction_markets.py`

Shared dataclass:

```python
@dataclass
class MarketProb:
    source: str        # "polymarket" | "kalshi"
    event: str         # human-readable label
    ticker: str | None # None for macro events
    yes_prob: float    # 0.0–1.0
    volume_usd: int    # liquidity indicator
    url: str           # traceability only, not injected into prompt
    fetched_at: datetime
```

Two private fetchers:
- `_fetch_polymarket_macro()` — queries Polymarket public REST API (no auth) using slugs from config
- `_fetch_kalshi_ticker(ticker)` — queries Kalshi REST API (API key required) using series from config; falls back to keyword search for auto-discovery

Public function:
```python
def get_prediction_market_context(watchlist: list[str]) -> dict[str, list[MarketProb]]:
    ...
```
Returns `{"macro": [...], "NVDA": [...], "TSLA": [...], ...}`. Results cached for `PREDICTION_MARKETS_CACHE_TTL` seconds (default 900s). Both fetchers fail silently — log warning and return empty list.

### Mapping config: `src/data/prediction_markets_config.yaml`

```yaml
macro:
  - label: "Fed cuts 25bps May 2025"
    polymarket_slug: "fed-cuts-25bps-may-2025"
    kalshi_series: "FED-2025-MAY"
  - label: "CPI above 3.5% April 2025"
    polymarket_slug: "cpi-above-3-5-april-2025"
    kalshi_series: null

tickers:
  NVDA:
    - label: "NVDA earnings beat Q1 2025"
      kalshi_series: "NVDA-EARN-Q1-2025"
      discovery_keywords: ["nvidia", "earnings"]
  TSLA:
    - label: "TSLA earnings beat Q1 2025"
      kalshi_series: "TSLA-EARN-Q1-2025"
      discovery_keywords: ["tesla", "earnings"]
  # ... extend per watchlist ticker
```

Curated entries are used first. If a `kalshi_series` is absent, the module runs a keyword search against Kalshi's market discovery endpoint to find matching markets.

## Strategy Integration

### `strategy.py`

New helper:
```python
def _build_prediction_markets_section(data: dict[str, list[MarketProb]]) -> str:
```

Example prompt output:
```
=== PREDICTION MARKETS ===
MACRO:
  Fed cuts 25bps May 2025: 72% yes  (Polymarket, $2.1M vol)
  CPI above 3.5% April:    31% yes  (Polymarket, $890K vol)

NVDA:
  NVDA earnings beat Q1:   61% yes  (Kalshi, $45K vol)

TSLA:
  TSLA earnings beat Q1:   44% yes  (Kalshi, $12K vol — low liquidity)
```

Markets with volume < $10K are flagged as "low liquidity" so Claude can discount them. If no data is available the section is omitted entirely.

`_build_market_context()` gets a new `prediction_markets: dict | None = None` parameter. The section is appended after `=== MACRO RISK ===`.

`AIStrategy.generate_signals()` gets a matching `prediction_markets` parameter passed through from the engine.

### `engine.py`

`TradingEngine._cycle()` calls `get_prediction_market_context(watchlist)` alongside existing data fetches and passes the result into `generate_signals()`.

## Config & Settings

Two new optional keys in `settings.py` / `.env`:

| Key | Default | Notes |
|-----|---------|-------|
| `KALSHI_API_KEY` | `""` | Required for Kalshi fetches; if absent, Kalshi is skipped silently |
| `PREDICTION_MARKETS_CACHE_TTL` | `900` | Seconds; shared between Polymarket and Kalshi |

`.env.example` updated with both keys (commented out).

## Error Handling

- Missing API key → skip fetcher, log info
- HTTP error / timeout → log warning, return `[]`
- Unknown market slug → log warning, skip that market
- All markets empty → section omitted from prompt; no impact on trading cycle

## Files Changed

| File | Change |
|------|--------|
| `src/data/prediction_markets.py` | New — fetchers, cache, public function |
| `src/data/prediction_markets_config.yaml` | New — mapping config |
| `src/bot/strategy.py` | Add `_build_prediction_markets_section()`, update `_build_market_context()` and `generate_signals()` |
| `src/bot/engine.py` | Call `get_prediction_market_context()` in `_cycle()`, pass to `generate_signals()` |
| `src/config/settings.py` | Add `KALSHI_API_KEY`, `PREDICTION_MARKETS_CACHE_TTL` |
| `.env.example` | Add commented-out new keys |
| `requirements.txt` | No new deps (uses `requests`, already present) |

## Testing

- Unit test `_build_prediction_markets_section()` with fixture data covering macro-only, ticker-only, mixed, and empty cases
- Unit test cache invalidation logic
- Integration test: mock both APIs, verify prompt contains `=== PREDICTION MARKETS ===` section
- Test that missing `KALSHI_API_KEY` skips Kalshi silently without error
