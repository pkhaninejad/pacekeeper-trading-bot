"""Tests for PredictionBotSettings."""
import os
import pytest


class TestPredictionBotSettings:
    def test_defaults_loaded(self):
        """All fields have sane defaults when no env vars set."""
        os.environ.pop("POLYMARKET_ENABLED", None)
        os.environ.pop("VIRTUAL_BANKROLL", None)
        from prediction_bot.src.config.settings import PredictionBotSettings
        s = PredictionBotSettings()
        assert s.POLYMARKET_ENABLED is True
        assert s.KALSHI_ENABLED is True
        assert s.VIRTUAL_BANKROLL == 1000.0
        assert s.MAX_POSITION_PCT == 0.10
        assert s.PM_DASHBOARD_PORT == 4001
        assert s.SCAN_INTERVAL_SECONDS == 120

    def test_env_override(self, monkeypatch):
        """Env vars override defaults."""
        monkeypatch.setenv("VIRTUAL_BANKROLL", "500.0")
        monkeypatch.setenv("PM_DASHBOARD_PORT", "4002")
        from prediction_bot.src.config.settings import PredictionBotSettings
        s = PredictionBotSettings()
        assert s.VIRTUAL_BANKROLL == 500.0
        assert s.PM_DASHBOARD_PORT == 4002

    def test_categories_default(self):
        """ENABLED_CATEGORIES defaults to all three."""
        from prediction_bot.src.config.settings import PredictionBotSettings
        s = PredictionBotSettings()
        assert set(s.ENABLED_CATEGORIES) == {"crypto", "sports", "politics"}
