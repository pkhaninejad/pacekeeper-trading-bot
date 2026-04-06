"""
News feed — fetches recent headlines per ticker from Finnhub (NewsAPI fallback).

Results are cached per ticker for NEWS_CACHE_TTL_SECONDS (default 15 min).
Fails silently when no API keys are configured.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import requests

logger = logging.getLogger(__name__)

_cache: dict[str, dict] = {}  # {ticker: {"data": list[NewsItem], "fetched_at": datetime}}


@dataclass
class NewsItem:
    headline: str
    source: str
    published_at: datetime  # UTC
    url: str                # for traceability; not injected into prompt


def _is_fresh(entry: dict, cache_ttl: int) -> bool:
    age = (datetime.now(UTC) - entry["fetched_at"]).total_seconds()
    return age < cache_ttl


class NewsFeed:
    """Fetches and caches news headlines per ticker."""

    def __init__(
        self,
        lookback_days: int = 3,
        max_headlines: int = 5,
        cache_ttl: int = 900,
        finnhub_api_key: str = "",
        news_api_key: str = "",
    ):
        self.lookback_days = lookback_days
        self.max_headlines = max_headlines
        self.cache_ttl = cache_ttl
        self._finnhub_api_key = finnhub_api_key
        self._news_api_key = news_api_key

    def get_news(self, tickers: list[str]) -> dict[str, list[NewsItem]]:
        """Bulk-fetch news for all tickers. Returns dict keyed by ticker."""
        return {ticker: self._fetch(ticker) for ticker in tickers}

    def _fetch(self, ticker: str) -> list[NewsItem]:
        """Return cached or freshly fetched news items."""
        if ticker in _cache and _is_fresh(_cache[ticker], self.cache_ttl):
            return _cache[ticker]["data"]

        items: list[NewsItem] = []
        if self._finnhub_api_key:
            items = self._fetch_finnhub(ticker)
        if not items and self._news_api_key:
            items = self._fetch_newsapi(ticker)

        _cache[ticker] = {"data": items, "fetched_at": datetime.now(UTC)}
        return items

    def _fetch_finnhub(self, ticker: str) -> list[NewsItem]:
        """GET Finnhub /company-news; filter by lookback_days; return <= max_headlines items."""
        try:
            cutoff = datetime.now(UTC) - timedelta(days=self.lookback_days)
            from_date = cutoff.strftime("%Y-%m-%d")
            to_date = datetime.now(UTC).strftime("%Y-%m-%d")
            url = "https://finnhub.io/api/v1/company-news"
            params = {
                "symbol": ticker,
                "from": from_date,
                "to": to_date,
                "token": self._finnhub_api_key,
            }
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code != 200:
                logger.debug("Finnhub news returned %s for %s", resp.status_code, ticker)
                return []
            articles = resp.json()
            if not isinstance(articles, list):
                return []
            items = []
            for article in articles:
                ts = article.get("datetime")
                if not ts:
                    continue
                published_at = datetime.fromtimestamp(ts, tz=UTC)
                if published_at < cutoff:
                    continue
                items.append(NewsItem(
                    headline=article.get("headline", "").strip(),
                    source=article.get("source", "").strip(),
                    published_at=published_at,
                    url=article.get("url", ""),
                ))
            # Sort newest-first, cap at max_headlines
            items.sort(key=lambda x: x.published_at, reverse=True)
            return items[: self.max_headlines]
        except Exception as e:
            logger.debug("Finnhub news fetch failed for %s: %s", ticker, e)
            return []

    def _fetch_newsapi(self, ticker: str) -> list[NewsItem]:
        """Fallback: search NewsAPI for ticker; return <= max_headlines items."""
        try:
            cutoff = datetime.now(UTC) - timedelta(days=self.lookback_days)
            url = "https://newsapi.org/v2/everything"
            params = {
                "q": ticker,
                "from": cutoff.strftime("%Y-%m-%dT%H:%M:%S"),
                "sortBy": "publishedAt",
                "pageSize": self.max_headlines,
                "apiKey": self._news_api_key,
            }
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code != 200:
                logger.debug("NewsAPI returned %s for %s", resp.status_code, ticker)
                return []
            data = resp.json()
            articles = data.get("articles", [])
            items = []
            for article in articles:
                raw_date = article.get("publishedAt", "")
                if not raw_date:
                    continue
                try:
                    published_at = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                except ValueError:
                    continue
                source_name = (article.get("source") or {}).get("name", "").strip()
                items.append(NewsItem(
                    headline=(article.get("title") or "").strip(),
                    source=source_name,
                    published_at=published_at,
                    url=article.get("url", ""),
                ))
            return items[: self.max_headlines]
        except Exception as e:
            logger.debug("NewsAPI fetch failed for %s: %s", ticker, e)
            return []
