"""Tests for NewsFeed in src/data/news_feed.py."""
from datetime import datetime, timezone
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
