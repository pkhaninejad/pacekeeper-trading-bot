"""Tests for settings in src/config/settings.py."""

import pytest
from src.config.settings import Settings


class TestSettings:
    def test_demo_base_url(self):
        s = Settings(T212_ENV="demo")
        assert s.t212_base_url == "https://demo.trading212.com/api/v0"

    def test_live_base_url(self):
        s = Settings(T212_ENV="live")
        assert s.t212_base_url == "https://live.trading212.com/api/v0"

    def test_default_environment_is_demo(self):
        s = Settings()
        assert s.T212_ENV == "demo"

    def test_default_bot_enabled(self):
        s = Settings()
        assert s.BOT_ENABLED is True

    def test_default_trade_interval(self):
        s = Settings()
        assert s.TRADE_INTERVAL_SECONDS == 300

    def test_default_max_position_pct(self):
        s = Settings()
        assert s.MAX_POSITION_SIZE_PCT == pytest.approx(0.05)

    def test_default_max_open_positions(self):
        s = Settings()
        assert s.MAX_OPEN_POSITIONS == 10

    def test_default_stop_loss(self):
        s = Settings()
        assert s.STOP_LOSS_PCT == pytest.approx(0.02)

    def test_default_take_profit(self):
        s = Settings()
        assert s.TAKE_PROFIT_PCT == pytest.approx(0.04)

    def test_default_watchlist_not_empty(self):
        s = Settings()
        assert len(s.WATCHLIST) > 0
        assert "AAPL" in s.WATCHLIST

    def test_overriding_values(self):
        s = Settings(MAX_OPEN_POSITIONS=5, STOP_LOSS_PCT=0.03)
        assert s.MAX_OPEN_POSITIONS == 5
        assert s.STOP_LOSS_PCT == pytest.approx(0.03)

    def test_default_account_type_is_invest(self):
        s = Settings()
        assert s.T212_ACCOUNT_TYPE == "invest"

    def test_account_path_prefix_invest(self):
        s = Settings(T212_ACCOUNT_TYPE="invest")
        assert s.account_path_prefix == "/equity"

    def test_account_path_prefix_cfd(self):
        s = Settings(T212_ACCOUNT_TYPE="cfd")
        assert s.account_path_prefix == "/cfd"
