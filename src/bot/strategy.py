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
from src.bot.price_feed import get_price_summary
from src.data.earnings_calendar import EarningsInfo

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
    price_data: dict | None = None,
    earnings_info: dict[str, "EarningsInfo"] | None = None,
) -> str:
    """Build the user prompt with current portfolio state."""
    if price_data is None:
        price_data = {}

    pos_summary = []
    for p in positions:
        pos_summary.append(
            f"  {p.ticker}: qty={p.quantity:.4f}, avg={p.averagePrice:.4f}, "
            f"current={p.currentPrice:.4f}, PnL={p.ppl:.2f} ({p.pnl_pct:.1f}%), "
            f"{'LONG' if p.is_long else 'SHORT'}"
        )

    instrument_info = {i.ticker: i.name for i in instruments if i.ticker in watchlist}

    # Format price feed + indicator section
    price_lines = []
    for ticker in watchlist:
        pd = price_data.get(ticker)
        if pd:
            ind = pd.get("indicators") or {}
            summary = ind.get("summary", "")
            price_lines.append(
                f"  {ticker}: price={pd['current_price']}, 1d_chg={pd['change_pct_1d']}%, "
                f"30d_range=[{pd['low_30d']}, {pd['high_30d']}], "
                f"recent_closes={pd['history']}\n"
                f"    indicators: {summary}"
            )
        else:
            price_lines.append(f"  {ticker}: (price data unavailable)")

    # Format earnings calendar section
    earnings_lines = []
    if earnings_info:
        for ticker in watchlist:
            info = earnings_info.get(ticker)
            if info is None:
                continue
            if info.in_window and info.earnings_date and info.days_until is not None:
                direction = "in" if info.days_until >= 0 else "ago"
                count = abs(info.days_until)
                earnings_lines.append(
                    f"  \u26a0\ufe0f  {ticker}: earnings {count} day(s) {direction} "
                    f"({info.earnings_date}) \u2014 new positions blocked by risk manager"
                )
            elif info.earnings_date:
                earnings_lines.append(
                    f"  \u2705  {ticker}: next earnings {info.earnings_date} \u2014 no restriction"
                )

    earnings_section = ""
    if earnings_lines:
        earnings_section = f"\n=== EARNINGS CALENDAR ===\n{chr(10).join(earnings_lines)}\n"

    context = f"""Current datetime (UTC): {datetime.utcnow().isoformat()}

=== PORTFOLIO ===
Free cash: {cash.free:.2f}
Total value: {cash.total:.2f}
Invested: {cash.invested:.2f}
Overall PnL: {cash.ppl:.2f}

Open positions ({len(positions)}):
{chr(10).join(pos_summary) if pos_summary else '  (none)'}

=== PRICE FEED (30-day) ===
{chr(10).join(price_lines) if price_lines else '  (unavailable)'}
{earnings_section}
=== WATCHLIST ===
{json.dumps({t: instrument_info.get(t, t) for t in watchlist}, indent=2)}

=== TASK ===
Analyse the portfolio and market conditions using the price feed data.
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
        earnings_info: dict[str, "EarningsInfo"] | None = None,
    ) -> list[TradeSignal]:
        """Call Claude and parse trade signals."""
        price_data = get_price_summary(watchlist)
        user_prompt = _build_market_context(
            positions, cash, watchlist, instruments, price_data, earnings_info
        )

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
