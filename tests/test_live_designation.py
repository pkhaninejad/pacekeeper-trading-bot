"""Tests for the single-LIVE strategy designation — issue #109."""
import pytest

from src.bot.live_designation import LiveConfirmationRequired, LiveDesignation


def _designation(tmp_path):
    return LiveDesignation(tmp_path / "live_strategy.json")


def test_no_designation_by_default(tmp_path):
    d = _designation(tmp_path)
    assert d.live_strategy_id is None
    assert d.is_live("anything") is False


def test_designate_in_demo_no_confirmation(tmp_path):
    d = _designation(tmp_path)
    d.designate("s1", env="demo", live_confirmed=False)
    assert d.live_strategy_id == "s1"
    assert d.is_live("s1") is True
    assert d.is_live("s2") is False


def test_single_live_invariant_replaces(tmp_path):
    d = _designation(tmp_path)
    d.designate("s1", env="demo", live_confirmed=False)
    d.designate("s2", env="demo", live_confirmed=False)
    assert d.live_strategy_id == "s2"
    assert d.is_live("s1") is False


def test_live_mode_requires_confirmation(tmp_path):
    d = _designation(tmp_path)
    with pytest.raises(LiveConfirmationRequired):
        d.designate("s1", env="live", live_confirmed=False)
    assert d.live_strategy_id is None  # unchanged


def test_live_mode_with_confirmation_succeeds(tmp_path):
    d = _designation(tmp_path)
    d.designate("s1", env="live", live_confirmed=True)
    assert d.live_strategy_id == "s1"


def test_persists_across_instances(tmp_path):
    _designation(tmp_path).designate("s1", env="demo", live_confirmed=False)
    assert _designation(tmp_path).live_strategy_id == "s1"


def test_clear(tmp_path):
    d = _designation(tmp_path)
    d.designate("s1", env="demo", live_confirmed=False)
    d.clear()
    assert d.live_strategy_id is None
    d.clear()  # idempotent
