"""
AI-powered trading strategy.

Uses an LLM (via LiteLLM) to analyse market conditions and generate trading signals.
Supports any provider supported by LiteLLM: anthropic, openai, gemini, ollama, deepseek, qwen.
"""

import json
import logging
from datetime import UTC, datetime
import litellm
from src.config.settings import settings
from src.api.models import Position, CashInfo, TradeSignal, Instrument, RegimeResult
from src.bot.llm_config import ProviderConfig, load_provider_config
from src.bot.price_feed import get_price_summary
from src.data.earnings_calendar import EarningsInfo
from src.data.macro_calendar import MacroEvent
from src.data.news_feed import NewsItem

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert algorithmic trading assistant integrated with a
live brokerage (Trading212). Your job is to analyse market context and open positions,
then generate precise trading signals.

Rules you must follow:
- Only generate signals for tickers on the watchlist or listed under SCREENED CANDIDATES.
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


def _format_age(published_at: "datetime") -> str:
    """Return human-readable relative age string e.g. '2h ago', '1d ago'."""
    delta = datetime.now(UTC) - published_at.astimezone(UTC)
    seconds = int(delta.total_seconds())
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def _build_performance_summary(outcome_log: list) -> str:
    """Compute a performance summary string for the Claude prompt.

    Returns an empty string if fewer than 5 closed trades exist.
    """
    closed = [o for o in outcome_log if o.outcome != "OPEN"]
    if len(closed) < 5:
        return ""

    open_count = sum(1 for o in outcome_log if o.outcome == "OPEN")
    recent = closed[-20:]
    wins = [o for o in recent if o.outcome == "TP_HIT"]
    losses = [o for o in recent if o.outcome != "TP_HIT"]
    win_rate = len(wins) / len(recent) * 100

    buy_recent = [o for o in recent if o.action == "BUY"]
    sell_recent = [o for o in recent if o.action == "SELL"]
    buy_wins = sum(1 for o in buy_recent if o.outcome == "TP_HIT")
    sell_wins = sum(1 for o in sell_recent if o.outcome == "TP_HIT")

    avg_win = (sum(o.pnl_pct for o in wins if o.pnl_pct is not None) / len(wins)) if wins else 0.0
    avg_loss = (sum(o.pnl_pct for o in losses if o.pnl_pct is not None) / len(losses)) if losses else 0.0
    expectancy = (win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss)

    lines = [
        f"=== YOUR RECENT SIGNAL PERFORMANCE (last {len(recent)} trades) ===",
        f"  Overall: {len(wins)} wins / {len(losses)} losses / {open_count} open  (win rate {win_rate:.0f}%)",
    ]
    if buy_recent:
        buy_label = "well calibrated" if buy_wins / len(buy_recent) >= 0.5 else "consider raising confidence threshold"
        lines.append(
            f"  BUY signals:  {buy_wins}W / {len(buy_recent) - buy_wins}L"
            f"  ({buy_wins / len(buy_recent) * 100:.0f}% — {buy_label})"
        )
    if sell_recent:
        sell_label = "well calibrated" if sell_wins / len(sell_recent) >= 0.5 else "consider raising confidence threshold for shorts"
        lines.append(
            f"  SELL signals: {sell_wins}W / {len(sell_recent) - sell_wins}L"
            f"  ({sell_wins / len(sell_recent) * 100:.0f}% — {sell_label})"
        )
    lines.append(
        f"  Avg winner: +{avg_win:.1f}%  |  Avg loser: {avg_loss:.1f}%  |  Expectancy: {expectancy:+.1f}%/trade"
    )

    recent_losses = [o for o in reversed(closed) if o.outcome != "TP_HIT"][:3]
    if recent_losses:
        lines.append("")
        lines.append("  Recent losses:")
        now = datetime.now(UTC)
        for o in recent_losses:
            age = ""
            if o.closed_at:
                closed_at = o.closed_at if o.closed_at.tzinfo else o.closed_at.replace(tzinfo=UTC)
                days = (now - closed_at).days
                age = f" — {days} day{'s' if days != 1 else ''} ago"
            pnl = f"{o.pnl_pct:.1f}%" if o.pnl_pct is not None else "n/a"
            lines.append(
                f"    {o.ticker} {o.direction} (conf={o.confidence:.2f}) → {o.outcome} {pnl}{age}"
            )

    return "\n".join(lines)


def _build_macro_section(macro_events: list["MacroEvent"] | None, block_hours: int) -> str:
    """Format the === MACRO RISK === prompt section."""
    if not macro_events:
        return "\n=== MACRO RISK ===\n  No HIGH-impact macro events in the next 24h.\n"
    lines = []
    for ev in macro_events:
        h = ev.hours_until
        if h <= block_hours:
            when = f"in {h:.0f}h" if h >= 1 else "imminent"
            lines.append(
                f"  \u26a0\ufe0f  {ev.event} — {when} ({ev.release_time.strftime('%Y-%m-%d %H:%M')} UTC)"
                f" — new positions BLOCKED"
            )
        else:
            lines.append(
                f"  \u26a0\ufe0f  {ev.event} — in {h:.0f}h ({ev.release_time.strftime('%Y-%m-%d %H:%M')} UTC)"
            )
    return f"\n=== MACRO RISK ===\n{chr(10).join(lines)}\n"



def _build_market_context(
    positions: list[Position],
    cash: CashInfo,
    watchlist: list[str],
    instruments: list[Instrument],
    price_data: dict | None = None,
    earnings_info: dict[str, "EarningsInfo"] | None = None,
    news_data: dict[str, list["NewsItem"]] | None = None,
    macro_events: list["MacroEvent"] | None = None,
    outcome_log: list | None = None,
    regime: "RegimeResult | None" = None,
    screen_candidates: list | None = None,
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

    # Format news section
    news_section = ""
    if news_data:
        news_lines = []
        for ticker in watchlist:
            items = news_data.get(ticker, [])
            news_lines.append(f"{ticker} (last {settings.NEWS_LOOKBACK_DAYS} days):")
            if items:
                for item in items:
                    age = _format_age(item.published_at)
                    news_lines.append(f'  "{item.headline}" \u2014 {item.source}, {age}')
            else:
                news_lines.append("  (no recent news)")
            news_lines.append("")  # blank line between tickers
        news_section = f"\n=== RECENT NEWS ===\n{chr(10).join(news_lines)}"

    macro_section = _build_macro_section(macro_events, settings.MACRO_BLOCK_HOURS)

    perf_section = ""
    if outcome_log:
        summary = _build_performance_summary(outcome_log)
        if summary:
            perf_section = f"\n{summary}\n"

    regime_section = ""
    if regime:
        spy_label = "above" if regime.spy_vs_200ema >= 0 else "below"
        pct_label = f"{abs(regime.spy_vs_200ema):.1f}% {spy_label} 200EMA"
        size_label = (
            f"reduced {int((1 - regime.position_size_multiplier) * 100)}% by risk manager"
            if regime.position_size_multiplier < 1.0
            else "normal (100%)"
        )
        bias_map = {
            "BULL": "Favour LONG signals",
            "NEUTRAL": "No directional bias",
            "BEAR": "Prefer SHORT signals or HOLD",
            "EXTREME_FEAR": "CLOSE only — no new positions",
        }
        bias = bias_map.get(regime.regime, "")
        regime_section = (
            f"\n=== MARKET REGIME ===\n"
            f"Regime:        {regime.regime}\n"
            f"SPY vs 200EMA: {regime.spy_vs_200ema:+.1f}% ({pct_label})\n"
            f"VIX:           {regime.vix:.1f}\n"
            f"Position size: {size_label}\n"
            f"Bias:          {bias}\n"
        )

    screened_section = ""
    if screen_candidates:
        sc_lines = []
        for c in screen_candidates:
            sc_lines.append(f"  {c.ticker}: {c.details} — {c.trigger}")
        screened_section = (
            "\n=== SCREENED CANDIDATES (this cycle only) ===\n"
            + "\n".join(sc_lines)
            + "\n  (apply same signal discipline; these are not permanent watchlist members)\n"
        )

    context = f"""Current datetime (UTC): {datetime.now(UTC).isoformat()}

=== PORTFOLIO ===
Free cash: {cash.free:.2f}
Total value: {cash.total:.2f}
Invested: {cash.invested:.2f}
Overall PnL: {cash.ppl:.2f}

Open positions ({len(positions)}):
{chr(10).join(pos_summary) if pos_summary else '  (none)'}

=== PRICE FEED (30-day) ===
{chr(10).join(price_lines) if price_lines else '  (unavailable)'}
{earnings_section}{macro_section}{news_section}{perf_section}{regime_section}
=== WATCHLIST ===
{json.dumps({t: instrument_info.get(t, t) for t in watchlist}, indent=2)}
{screened_section}
=== TASK ===
Analyse the portfolio and market conditions using the price feed data.
Generate trading signals for up to 5 tickers.
Focus on tickers where there is a clear directional view.
Return ONLY a JSON array of TradeSignal objects.
"""
    return context


class AIStrategy:
    """LLM-powered trading strategy. Provider-agnostic via LiteLLM."""

    def generate_signals(
        self,
        positions: list[Position],
        cash: CashInfo,
        watchlist: list[str],
        instruments: list[Instrument],
        provider_config: "ProviderConfig | None" = None,
        earnings_info: dict[str, "EarningsInfo"] | None = None,
        news_data: dict[str, list["NewsItem"]] | None = None,
        macro_events: list["MacroEvent"] | None = None,
        outcome_log: list | None = None,
        regime: "RegimeResult | None" = None,
        screen_candidates: list | None = None,
    ) -> list[TradeSignal]:
        """Call the configured LLM provider and parse trade signals."""
        if provider_config is None:
            provider_config = load_provider_config()

        all_tickers = watchlist + [c.ticker for c in (screen_candidates or [])]
        price_data = get_price_summary(all_tickers)
        user_prompt = _build_market_context(
            positions, cash, watchlist, instruments, price_data,
            earnings_info, news_data, macro_events, outcome_log,
            regime=regime,
            screen_candidates=screen_candidates,
        )

        logger.info("Calling %s/%s for trading signals...", provider_config.provider, provider_config.model)
        try:
            response = litellm.completion(
                model=provider_config.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                api_key=provider_config.api_key or None,
                api_base=provider_config.base_url or None,
                max_tokens=2048,
            )
            raw = response.choices[0].message.content.strip()
            logger.debug("LLM raw response: %s", raw)

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
            logger.error("Failed to parse LLM response as JSON: %s", e)
            return []
        except Exception as e:
            logger.error("LLM API error: %s", e)
            return []
