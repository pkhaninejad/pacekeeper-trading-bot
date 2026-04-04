"""
Claude AI-powered trading strategy.

Uses Claude to analyse market conditions and generate long/short signals.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional
import anthropic
from src.config.settings import settings
from src.api.models import Position, CashInfo, TradeSignal, Instrument

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert algorithmic trading assistant integrated with a
live brokerage (Trading212). Your job is to analyse market context and open positions,
then generate precise trading signals.

Rules you must follow:
- Only generate signals for tickers on the watchlist.
- Never risk more than {max_position_pct}% of the portfolio on a single trade.
- Apply stop-loss at {stop_loss_pct}% and take-profit at {take_profit_pct}%.
- Prefer HOLD when confidence is below 0.6.
- Return ONLY valid JSON matching the TradeSignal schema — no prose.
- Consider existing positions before opening new ones (avoid duplication).
- If shorting: quantity must be negative.

TradeSignal JSON schema:
{{
  "ticker": "string",
  "action": "BUY" | "SELL" | "HOLD",
  "direction": "LONG" | "SHORT" | "CLOSE",
  "confidence": float (0.0–1.0),
  "reasoning": "brief explanation",
  "suggested_quantity": float | null,
  "suggested_price": float | null,
  "order_type": "MARKET" | "LIMIT" | "STOP"
}}

Return a JSON array of TradeSignal objects — one per ticker you have a view on.
""".format(
    max_position_pct=settings.MAX_POSITION_SIZE_PCT * 100,
    stop_loss_pct=settings.STOP_LOSS_PCT * 100,
    take_profit_pct=settings.TAKE_PROFIT_PCT * 100,
)


def _build_market_context(
    positions: list[Position],
    cash: CashInfo,
    watchlist: list[str],
    instruments: list[Instrument],
) -> str:
    """Build the user prompt with current portfolio state."""
    pos_summary = []
    for p in positions:
        pos_summary.append(
            f"  {p.ticker}: qty={p.quantity:.4f}, avg={p.averagePrice:.4f}, "
            f"current={p.currentPrice:.4f}, PnL={p.ppl:.2f} ({p.pnl_pct:.1f}%), "
            f"{'LONG' if p.is_long else 'SHORT'}"
        )

    instrument_info = {i.ticker: i.name for i in instruments if i.ticker in watchlist}

    context = f"""Current datetime (UTC): {datetime.utcnow().isoformat()}

=== PORTFOLIO ===
Free cash: {cash.free:.2f} {' '}
Total value: {cash.total:.2f}
Invested: {cash.invested:.2f}
Overall PnL: {cash.ppl:.2f}

Open positions ({len(positions)}):
{chr(10).join(pos_summary) if pos_summary else '  (none)'}

=== WATCHLIST ===
{json.dumps({t: instrument_info.get(t, t) for t in watchlist}, indent=2)}

=== TASK ===
Analyse the portfolio and market conditions.
Generate trading signals for up to 5 tickers.
Focus on tickers where there is a clear directional view.
Return ONLY a JSON array of TradeSignal objects.
"""
    return context


class ClaudeStrategy:
    """Uses Claude Sonnet to generate long/short signals."""

    def __init__(self):
        self._client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def generate_signals(
        self,
        positions: list[Position],
        cash: CashInfo,
        watchlist: list[str],
        instruments: list[Instrument],
    ) -> list[TradeSignal]:
        """Call Claude and parse trade signals."""
        user_prompt = _build_market_context(positions, cash, watchlist, instruments)

        logger.info("Calling Claude for trading signals...")
        try:
            message = self._client.messages.create(
                model=settings.CLAUDE_MODEL,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            raw = message.content[0].text.strip()
            logger.debug("Claude raw response: %s", raw)

            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]

            signals_data = json.loads(raw)
            if isinstance(signals_data, dict):
                signals_data = [signals_data]

            signals = []
            for s in signals_data:
                try:
                    signals.append(TradeSignal(**s))
                except Exception as e:
                    logger.warning("Skipping malformed signal %s: %s", s, e)

            logger.info("Generated %d signals", len(signals))
            return signals

        except json.JSONDecodeError as e:
            logger.error("Failed to parse Claude response as JSON: %s", e)
            return []
        except Exception as e:
            logger.error("Claude API error: %s", e)
            return []
