"""Unit tests for src/data/screener.py — no yfinance network calls."""
import pytest
from src.data.screener import ScreenCandidate, run_screener


def test_empty_universe():
    result = run_screener([], price_data={}, max_results=3)
    assert result == []
