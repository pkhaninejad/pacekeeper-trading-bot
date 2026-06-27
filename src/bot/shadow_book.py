"""Paper execution for non-LIVE stock strategies — issue #109.

A shadow strategy never touches Trading212. Its approved opens become virtual
trades in a ``ShadowPortfolio``; its exits (stop-loss / take-profit per the
strategy's own params) settle against current market prices. The same
``StockStrategyRunner`` that drives the LIVE strategy drives the shadows, so a
strategy behaves identically whether it trades real money or paper.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.api.models import CashInfo, Position, TradeSignal
from src.bot.strategy_runner import StockStrategyRunner
from strategy_kit.portfolio import ShadowPortfolio


@dataclass
class ShadowHolding:
    trade_id: int
    entry_price: float
    quantity: float
    direction: str  # "long" | "short"


async def run_shadow_strategy(
    *,
    portfolio: ShadowPortfolio,
    strategy_id: str,
    runner: StockStrategyRunner,
    signals: list[TradeSignal],
    prices: dict[str, float],
    holdings: dict[str, ShadowHolding],
) -> dict:
    """Advance one shadow strategy by one cycle.

    ``holdings`` maps ticker → open virtual holding and is mutated in place.
    ``prices`` maps ticker → current price (price_feed current_price).
    Returns ``{"opened": int, "closed": int}``.
    """
    def build_positions() -> list[Position]:
        out: list[Position] = []
        for ticker, h in holdings.items():
            current = prices.get(ticker, h.entry_price)
            out.append(Position(
                ticker=ticker, quantity=h.quantity,
                averagePrice=h.entry_price, currentPrice=current, ppl=0.0,
            ))
        return out

    # 1. Exits — close virtual positions hitting this strategy's stop / take.
    closed = 0
    for pos in runner.manage_exits(build_positions()):
        h = holdings.get(pos.ticker)
        if h is None:
            continue
        exit_price = prices.get(pos.ticker, pos.currentPrice)
        await portfolio.close_trade(h.trade_id, exit_price)
        del holdings[pos.ticker]
        closed += 1

    # 2. Opens — approved signals become new virtual trades, sized to the
    #    shadow bankroll.
    bankroll = (await portfolio.equity_curve(strategy_id))[-1].balance
    cash = CashInfo(free=bankroll, total=bankroll, ppl=0.0, result=0.0,
                    invested=0.0, pieCash=0.0)
    opened = 0
    for sig in runner.run(signals, build_positions(), cash):
        if sig.direction == "CLOSE" or sig.action != "BUY" or sig.ticker in holdings:
            continue
        price = sig.suggested_price or prices.get(sig.ticker)
        qty = sig.suggested_quantity
        if not price or not qty:
            continue
        direction = "short" if sig.direction == "SHORT" else "long"
        trade_id = await portfolio.open_trade(
            strategy_id, sig.ticker, entry_price=price, quantity=qty, direction=direction,
        )
        holdings[sig.ticker] = ShadowHolding(trade_id, price, qty, direction)
        opened += 1

    return {"opened": opened, "closed": closed}
