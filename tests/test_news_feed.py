"""Tests for NewsFeed in src/data/news_feed.py."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
from src.data.news_feed import NewsFeed, NewsItem, _cache


class TestNewsItem:
    def test_newsitem_fields(self):
        item = NewsItem(
            headline="Nvidia beats earnings",
            source="Reuters",
            published_at=datetime(2026, 4, 4, 10, 0, tzinfo=timezone.utc),
            url="https://example.com/article",
        )
        assert item.headline == "Nvidia beats earnings"
        assert item.source == "Reuters"
        assert item.url == "https://example.com/article"


class TestFetchFinnhub:
    def setup_method(self):
        _cache.clear()

    def test_fetch_finnhub_success(self):
        """Returns NewsItems filtered to lookback window, capped at max_headlines."""
        import time
        now_ts = int(datetime.now(timezone.utc).timestamp())
        old_ts = int((datetime.now(timezone.utc) - timedelta(days=10)).timestamp())

        finnhub_response = [
            {"headline": "Nvidia beats earnings", "source": "Reuters", "datetime": now_ts, "url": "https://a.com/1"},
            {"headline": "Nvidia raises guidance", "source": "Bloomberg", "datetime": now_ts - 3600, "url": "https://a.com/2"},
            {"headline": "Old stale article",     "source": "FT",        "datetime": old_ts,         "url": "https://a.com/3"},
        ]

        with patch("src.data.news_feed.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = finnhub_response

            feed = NewsFeed(lookback_days=3, max_headlines=5, cache_ttl=900, finnhub_api_key="test-key", news_api_key="")
            items = feed._fetch("NVDA")

        # Old article (10 days ago) must be filtered out
        assert len(items) == 2
        assert items[0].headline == "Nvidia beats earnings"
        assert items[0].source == "Reuters"
        assert items[1].headline == "Nvidia raises guidance"

    def test_max_headlines_cap(self):
        """Returns at most max_headlines items."""
        now_ts = int(datetime.now(timezone.utc).timestamp())
        finnhub_response = [
            {"headline": f"Article {i}", "source": "Reuters", "datetime": now_ts - i * 60, "url": f"https://a.com/{i}"}
            for i in range(10)
        ]

        with patch("src.data.news_feed.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = finnhub_response

            feed = NewsFeed(lookback_days=3, max_headlines=3, cache_ttl=900, finnhub_api_key="test-key", news_api_key="")
            items = feed._fetch("NVDA")

        assert len(items) == 3

    def test_finnhub_non_200_returns_empty(self):
        with patch("src.data.news_feed.requests.get") as mock_get:
            mock_get.return_value.status_code = 429

            feed = NewsFeed(lookback_days=3, max_headlines=5, cache_ttl=900, finnhub_api_key="test-key", news_api_key="")
            items = feed._fetch_finnhub("NVDA")

        assert items == []

    def test_result_cached_second_call_skips_network(self):
        now_ts = int(datetime.now(timezone.utc).timestamp())
        finnhub_response = [
            {"headline": "Cached article", "source": "Reuters", "datetime": now_ts, "url": "https://a.com/1"},
        ]

        with patch("src.data.news_feed.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = finnhub_response

            feed = NewsFeed(lookback_days=3, max_headlines=5, cache_ttl=900, finnhub_api_key="test-key", news_api_key="")
            feed._fetch("NVDA")
            feed._fetch("NVDA")  # second call

        assert mock_get.call_count == 1  # only fetched once


class TestFetchNewsAPIFallback:
    def setup_method(self):
        _cache.clear()

    def test_fetch_newsapi_fallback(self):
        """When Finnhub returns empty, NewsAPI is called and items are returned."""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        newsapi_response = {
            "articles": [
                {
                    "title": "Tesla recalls vehicles",
                    "source": {"name": "AP"},
                    "publishedAt": now_iso,
                    "url": "https://ap.com/1",
                }
            ]
        }

        with patch("src.data.news_feed.requests.get") as mock_get:
            # First call (Finnhub) returns empty list; second call (NewsAPI) returns articles
            finnhub_resp = MagicMock()
            finnhub_resp.status_code = 200
            finnhub_resp.json.return_value = []

            newsapi_resp = MagicMock()
            newsapi_resp.status_code = 200
            newsapi_resp.json.return_value = newsapi_response

            mock_get.side_effect = [finnhub_resp, newsapi_resp]

            feed = NewsFeed(lookback_days=3, max_headlines=5, cache_ttl=900, finnhub_api_key="fh-key", news_api_key="na-key")
            items = feed._fetch("TSLA")

        assert len(items) == 1
        assert items[0].headline == "Tesla recalls vehicles"
        assert items[0].source == "AP"

    def test_newsapi_skipped_when_finnhub_has_results(self):
        """NewsAPI is NOT called if Finnhub already returned items."""
        now_ts = int(datetime.now(timezone.utc).timestamp())
        finnhub_response = [
            {"headline": "Some news", "source": "Reuters", "datetime": now_ts, "url": "https://a.com/1"}
        ]

        with patch("src.data.news_feed.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = finnhub_response

            feed = NewsFeed(lookback_days=3, max_headlines=5, cache_ttl=900, finnhub_api_key="fh-key", news_api_key="na-key")
            feed._fetch("NVDA")

        # Only one HTTP call — Finnhub only
        assert mock_get.call_count == 1


class TestNoKeys:
    def setup_method(self):
        _cache.clear()

    def test_no_keys_returns_empty_without_raising(self):
        """Both keys empty → get_news returns empty list per ticker, no exception."""
        with patch("src.data.news_feed.requests.get") as mock_get:
            feed = NewsFeed(finnhub_api_key="", news_api_key="")
            result = feed.get_news(["AAPL", "NVDA"])

        mock_get.assert_not_called()
        assert result == {"AAPL": [], "NVDA": []}

    def test_finnhub_raises_returns_empty(self):
        """Network error on Finnhub → returns empty list, does not raise."""
        with patch("src.data.news_feed.requests.get", side_effect=Exception("timeout")):
            feed = NewsFeed(finnhub_api_key="fh-key", news_api_key="")
            items = feed._fetch("AAPL")

        assert items == []
