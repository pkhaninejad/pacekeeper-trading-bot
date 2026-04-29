"""Tests for evaluate_candidates()."""
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
import pytest

from prediction_bot.src.api.models import PredictionMarket, MarketCandidate
from prediction_bot.src.config.settings import PredictionBotSettings


def _candidate(
    id="m1",
    question="Will BTC stay above $80k?",
    category="crypto",
    yes_price=0.92,
    no_price=0.08,
    platform="polymarket",
    best_side="YES",
):
    return MarketCandidate(
        market=PredictionMarket(
            id=id,
            platform=platform,
            question=question,
            category=category,
            end_date=datetime.now(timezone.utc) + timedelta(hours=20),
            yes_price=yes_price,
            no_price=no_price,
            liquidity=50000,
        ),
        best_side=best_side,
        market_price=yes_price if best_side == "YES" else no_price,
    )


@pytest.fixture
def settings():
    return PredictionBotSettings(MIN_EDGE_PCT=0.02, ANTHROPIC_API_KEY="test-key")


class TestParseEvaluatorResponse:
    def test_parses_valid_json_array(self):
        from prediction_bot.src.bot.evaluator import _parse_llm_response

        raw = '[{"market_id":"m1","true_probability":0.97,"confidence":0.85,"reasoning":"Strong signal","recommended_side":"YES"}]'
        result = _parse_llm_response(raw)
        assert len(result) == 1
        assert result[0]["market_id"] == "m1"
        assert result[0]["true_probability"] == 0.97

    def test_handles_json_in_markdown_block(self):
        from prediction_bot.src.bot.evaluator import _parse_llm_response

        raw = '```json\n[{"market_id":"m1","true_probability":0.95,"confidence":0.8,"reasoning":"ok","recommended_side":"YES"}]\n```'
        result = _parse_llm_response(raw)
        assert len(result) == 1

    def test_returns_empty_on_invalid_json(self):
        from prediction_bot.src.bot.evaluator import _parse_llm_response

        result = _parse_llm_response("not json at all")
        assert result == []


class TestEdgeCalculation:
    def test_edge_yes_side(self):
        from prediction_bot.src.bot.evaluator import _calculate_edge

        edge = _calculate_edge(
            true_prob=0.97,
            recommended_side="YES",
            yes_price=0.92,
            no_price=0.08,
            platform="polymarket",
        )
        assert abs(edge - 0.03) < 0.001  # 0.97 - 0.92 - 0.02

    def test_edge_no_side(self):
        from prediction_bot.src.bot.evaluator import _calculate_edge

        edge = _calculate_edge(
            true_prob=0.03,
            recommended_side="NO",
            yes_price=0.92,
            no_price=0.08,
            platform="polymarket",
        )
        assert abs(edge - (0.97 - 0.08 - 0.02)) < 0.001

    def test_kalshi_higher_fee(self):
        from prediction_bot.src.bot.evaluator import _calculate_edge

        poly_edge = _calculate_edge(0.97, "YES", 0.92, 0.08, "polymarket")
        kalshi_edge = _calculate_edge(0.97, "YES", 0.92, 0.08, "kalshi")
        assert kalshi_edge < poly_edge

    def test_skip_returns_zero(self):
        from prediction_bot.src.bot.evaluator import _calculate_edge

        edge = _calculate_edge(0.92, "SKIP", 0.92, 0.08, "polymarket")
        assert edge == 0.0


def _make_mock_provider(response_text: str) -> MagicMock:
    provider = MagicMock()
    provider.name = "test-provider"
    provider.litellm_model = "test/model"
    provider.complete.return_value = response_text
    return provider


class TestEvaluateCandidates:
    @pytest.mark.asyncio
    async def test_returns_only_candidates_with_edge(self, settings):
        from prediction_bot.src.bot.evaluator import evaluate_candidates

        c1 = _candidate(id="m1", yes_price=0.92)
        c2 = _candidate(id="m2", yes_price=0.96)

        llm_response = '[{"market_id":"m1","true_probability":0.97,"confidence":0.85,"reasoning":"Strong","recommended_side":"YES"},{"market_id":"m2","true_probability":0.96,"confidence":0.5,"reasoning":"Meh","recommended_side":"SKIP"}]'

        with patch("prediction_bot.src.bot.evaluator.load_active_provider", return_value=_make_mock_provider(llm_response)):
            result = await evaluate_candidates([c1, c2], settings)

        assert len(result) == 1
        assert result[0].market.id == "m1"
        assert result[0].edge is not None
        assert result[0].edge > 0

    @pytest.mark.asyncio
    async def test_handles_malformed_llm_response(self, settings):
        from prediction_bot.src.bot.evaluator import evaluate_candidates

        c1 = _candidate(id="m1")

        with patch("prediction_bot.src.bot.evaluator.load_active_provider", return_value=_make_mock_provider("I cannot evaluate this.")):
            result = await evaluate_candidates([c1], settings)

        assert result == []
