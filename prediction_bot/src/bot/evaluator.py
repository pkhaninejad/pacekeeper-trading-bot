"""LLM-based market probability evaluator."""
from __future__ import annotations

import json
import logging
import re

from prediction_bot.src.api.models import MarketCandidate
from prediction_bot.src.bot.evaluator_prompt import SYSTEM_PROMPT, build_user_prompt
from prediction_bot.src.config.llm_config import load_active_provider
from prediction_bot.src.config.settings import PredictionBotSettings
from prediction_bot.src.data.market_data import get_crypto_context, get_sports_scores

logger = logging.getLogger(__name__)

_FEES = {"polymarket": 0.02, "kalshi": 0.03}


def _parse_llm_response(raw: str) -> list[dict]:
    raw = re.sub(r"```(?:json)?\s*", "", raw).strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _calculate_edge(
    true_prob: float,
    recommended_side: str,
    yes_price: float,
    no_price: float,
    platform: str,
) -> float:
    if recommended_side == "SKIP":
        return 0.0
    fee = _FEES.get(platform, 0.02)
    if recommended_side == "YES":
        return true_prob - yes_price - fee
    else:
        return (1.0 - true_prob) - no_price - fee


async def _enrich(candidate: MarketCandidate) -> MarketCandidate:
    cat = candidate.market.category
    if cat == "crypto":
        ctx = await get_crypto_context(candidate.market.question)
        if ctx:
            return candidate.model_copy(update={"external_data": {"crypto": ctx}})
    elif cat == "sports":
        ctx = await get_sports_scores(candidate.market.question)
        if ctx:
            return candidate.model_copy(update={"external_data": {"sports": ctx}})
    return candidate


async def evaluate_candidates(
    candidates: list[MarketCandidate],
    settings: PredictionBotSettings,
) -> list[MarketCandidate]:
    """Enrich candidates, call LLM in batches of 10, return those with edge > MIN_EDGE_PCT."""
    provider = load_active_provider()
    logger.info("Using LLM provider: %s (%s)", provider.name, provider.litellm_model)

    enriched = []
    for c in candidates:
        enriched.append(await _enrich(c))

    results: list[MarketCandidate] = []
    batch_size = 10
    for i in range(0, len(enriched), batch_size):
        batch = enriched[i : i + batch_size]
        user_prompt = build_user_prompt(batch)
        try:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
            raw = provider.complete(messages)
        except Exception as e:
            logger.warning("LLM evaluation failed for batch %d: %s", i // batch_size, e)
            continue

        assessments = _parse_llm_response(raw)
        assessment_map = {a["market_id"]: a for a in assessments}

        for candidate in batch:
            assessment = assessment_map.get(candidate.market.id)
            if not assessment:
                continue
            side = assessment.get("recommended_side", "SKIP")
            true_prob = float(assessment.get("true_probability", 0.5))
            edge = _calculate_edge(
                true_prob, side,
                candidate.market.yes_price,
                candidate.market.no_price,
                candidate.market.platform,
            )
            if edge > settings.MIN_EDGE_PCT:
                results.append(candidate.model_copy(update={
                    "llm_true_prob": true_prob,
                    "llm_confidence": float(assessment.get("confidence", 0.5)),
                    "llm_reasoning": assessment.get("reasoning", ""),
                    "edge": edge,
                }))

    return results
