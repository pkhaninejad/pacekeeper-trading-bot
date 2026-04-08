"""Helpers for position quantity handling."""


def is_closable_quantity(quantity: float, epsilon: float = 1e-6) -> bool:
    """Return True only when quantity is meaningfully non-zero."""
    return abs(quantity) > epsilon


def resolve_close_quantity(position_quantity: float, max_sell: float | None, epsilon: float = 1e-6) -> float | None:
    """Return signed close quantity using maxSell when available, else quantity.

    Trading212 can occasionally report stale `quantity` but accurate `maxSell=0`.
    """
    closable_abs = abs(max_sell) if max_sell is not None else abs(position_quantity)
    if closable_abs <= epsilon:
        return None
    # Long positions close with negative qty; short positions (if any) close positive.
    return -closable_abs if position_quantity > 0 else closable_abs
