# News & Sentiment Feed — Design Spec

**Issue:** [#13](https://github.com/pkhaninejad/Claude-trade-bot/issues/13)
**Date:** 2026-04-06
**Status:** Approved

---

## Overview

Add a `NewsFeed` class that fetches recent headlines per ticker from Finnhub (with NewsAPI as optional fallback) and injects them into the Claude strategy prompt each trading cycle. This gives Claude fundamental context — earnings beats, regulatory actions, macro events — that price data alone cannot provide.

---

## Architecture

Mirrors the existing `EarningsCalendar` pattern exactly:

- `NewsFeed` class lives in `src/data/news_feed.py`
- Instantiated once in `TradingEngine.__init__`
- `get_news(tickers)` called in `TradingEngine._cycle()` before signal generation
- Result passed as `news_data` into `ClaudeStrategy.generate_signals()`
- Injected into the Claude prompt inside `_build_market_context()`

All external data orchestration stays in the engine. No new patterns introduced.

---

## Data Model

```python
@dataclass
class NewsItem:
    headline: str
    source: str
    published_at: datetime  # UTC
    url: str                # for traceability; not injected into prompt
```

`sentiment` field is omitted — Claude assesses sentiment from headline text directly.

---

## `NewsFeed` Class (`src/data/news_feed.py`)

```python
class NewsFeed:
    def __init__(
        self,
        lookback_days: int,
        max_headlines: int,
        cache_ttl: int,
        finnhub_api_key: str,
        news_api_key: str,
    ): ...

    def get_news(self, tickers: list[str]) -> dict[str, list[NewsItem]]:
        """Bulk-fetch news for all tickers. Returns dict keyed by ticker."""

    def _fetch(self, ticker: str) -> list[NewsItem]:
        """Check cache; call Finnhub, then NewsAPI fallback if needed."""

    def _fetch_finnhub(self, ticker: str) -> list[NewsItem]:
        """GET /company-news; filter by lookback_days; return ≤ max_headlines items."""

    def _fetch_newsapi(self, ticker: str) -> list[NewsItem]:
        """Fallback: search NewsAPI for ticker; return ≤ max_headlines items."""
```

**Cache:** module-level `_cache: dict[str, dict]` with `fetched_at` timestamps. TTL = `NEWS_CACHE_TTL_SECONDS`. Same `_is_fresh()` helper pattern as `EarningsCalendar`.

**Failure handling:** if both keys are empty, or all HTTP calls fail, `_fetch` returns `[]` silently — never raises. The bot continues without news context.

---

## Settings (`src/config/settings.py`)

```python
# News feed (FINNHUB_API_KEY already exists — reused)
NEWS_API_KEY: str = ""                   # optional NewsAPI fallback
NEWS_LOOKBACK_DAYS: int = 3              # filter headlines older than N days
NEWS_MAX_HEADLINES_PER_TICKER: int = 5   # cap per ticker per cycle
NEWS_CACHE_TTL_SECONDS: int = 900        # 15-minute default
```

---

## Engine Wiring (`src/bot/engine.py`)

```python
# __init__
self.news = NewsFeed(
    lookback_days=settings.NEWS_LOOKBACK_DAYS,
    max_headlines=settings.NEWS_MAX_HEADLINES_PER_TICKER,
    cache_ttl=settings.NEWS_CACHE_TTL_SECONDS,
    finnhub_api_key=settings.FINNHUB_API_KEY,
    news_api_key=settings.NEWS_API_KEY,
)

# _cycle()
news_data = self.news.get_news(settings.WATCHLIST)
signals = self.strategy.generate_signals(
    positions, cash, settings.WATCHLIST, instruments, earnings_info, news_data
)
```

---

## Prompt Injection (`src/bot/strategy.py`)

`_build_market_context()` gains `news_data: dict[str, list[NewsItem]] | None = None`.

A `=== RECENT NEWS ===` section is inserted between the earnings section and `=== WATCHLIST ===`:

```
=== RECENT NEWS ===
NVDA (last 3 days):
  "Nvidia beats Q4 earnings, raises guidance" — Reuters, 2h ago
  "Blackwell GPU demand outpacing supply" — Bloomberg, 5h ago
  "EU opens antitrust probe into Nvidia" — FT, 1d ago

TSLA (last 3 days):
  "Tesla recalls 125,000 vehicles over seatbelt issue" — AP, 4h ago

AAPL (last 3 days):
  (no recent news)
```

- All watchlist tickers appear, even those with no news (explicit `(no recent news)` signals to Claude that absence was checked)
- Age is human-readable relative time computed at prompt-build time ("2h ago", "1d ago")
- No sentiment prefix — Claude infers from headline text
- Section is omitted entirely if `news_data` is `None` or empty

`generate_signals()` signature:
```python
def generate_signals(
    self,
    positions: list[Position],
    cash: CashInfo,
    watchlist: list[str],
    instruments: list[Instrument],
    earnings_info: dict[str, EarningsInfo] | None = None,
    news_data: dict[str, list[NewsItem]] | None = None,
) -> list[TradeSignal]:
```

---

## Tests (`tests/test_news_feed.py`)

Three unit tests with mocked HTTP, mirroring `tests/test_earnings_calendar.py` style:

1. **`test_fetch_finnhub_success`** — mock valid Finnhub response; assert correct `NewsItem` fields, count ≤ `max_headlines`, headlines older than `lookback_days` excluded

2. **`test_fetch_newsapi_fallback`** — mock Finnhub empty + valid NewsAPI response; assert fallback fires and returns items

3. **`test_no_keys_returns_empty`** — `NewsFeed` with empty keys; assert `get_news()` returns `[]` per ticker without raising

---

## Files Changed

| File | Change |
|------|--------|
| `src/data/news_feed.py` | **New** — `NewsItem` dataclass + `NewsFeed` class |
| `src/config/settings.py` | Add `NEWS_API_KEY`, `NEWS_LOOKBACK_DAYS`, `NEWS_MAX_HEADLINES_PER_TICKER`, `NEWS_CACHE_TTL_SECONDS` |
| `src/bot/engine.py` | Instantiate `NewsFeed`, fetch news in `_cycle()`, pass to `generate_signals()` |
| `src/bot/strategy.py` | Add `news_data` param to `generate_signals()` and `_build_market_context()`; inject `=== RECENT NEWS ===` section |
| `tests/test_news_feed.py` | **New** — 3 unit tests with mocked HTTP |
| `.env.example` | Document new env vars |

---

## Definition of Done

- [ ] News headlines appear in Claude prompt during trading cycle log output
- [ ] Missing API keys do not crash the bot — cycle completes normally
- [ ] Unit tests pass with mocked HTTP responses
- [ ] `NEWS_CACHE_TTL_SECONDS` prevents duplicate Finnhub calls within a cycle
