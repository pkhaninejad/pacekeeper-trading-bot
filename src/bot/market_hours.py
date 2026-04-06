"""
NYSE market hours gate.

Regular session: 09:30–16:00 Eastern Time, Monday–Friday.
No built-in holiday calendar — major US holidays are listed explicitly.
Uses zoneinfo (Python 3.9+ stdlib) — no extra packages needed.
"""

from datetime import date, time, datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# US market holidays 2025–2026 (NYSE observed dates)
_HOLIDAYS: frozenset[date] = frozenset([
    # 2025
    date(2025, 1, 1),   # New Year's Day
    date(2025, 1, 20),  # MLK Day
    date(2025, 2, 17),  # Presidents' Day
    date(2025, 4, 18),  # Good Friday
    date(2025, 5, 26),  # Memorial Day
    date(2025, 6, 19),  # Juneteenth
    date(2025, 7, 4),   # Independence Day
    date(2025, 9, 1),   # Labor Day
    date(2025, 11, 27), # Thanksgiving
    date(2025, 12, 25), # Christmas
    # 2026
    date(2026, 1, 1),   # New Year's Day
    date(2026, 1, 19),  # MLK Day
    date(2026, 2, 16),  # Presidents' Day
    date(2026, 4, 3),   # Good Friday
    date(2026, 5, 25),  # Memorial Day
    date(2026, 6, 19),  # Juneteenth
    date(2026, 7, 3),   # Independence Day (observed)
    date(2026, 9, 7),   # Labor Day
    date(2026, 11, 26), # Thanksgiving
    date(2026, 12, 25), # Christmas
])

_OPEN  = time(9, 30)
_CLOSE = time(16, 0)


def is_market_open(now: datetime | None = None) -> bool:
    """Return True if NYSE regular session is currently open."""
    if now is None:
        now = datetime.now(ET)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=ET)
    else:
        now = now.astimezone(ET)

    if now.weekday() >= 5:          # Saturday=5, Sunday=6
        return False
    if now.date() in _HOLIDAYS:
        return False
    return _OPEN <= now.time() < _CLOSE


def next_open(now: datetime | None = None) -> datetime:
    """Return the next NYSE open as a timezone-aware ET datetime."""
    if now is None:
        now = datetime.now(ET)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=ET)
    else:
        now = now.astimezone(ET)

    from datetime import timedelta
    candidate = now.replace(hour=9, minute=30, second=0, microsecond=0)
    if now >= candidate:
        candidate += timedelta(days=1)

    while candidate.weekday() >= 5 or candidate.date() in _HOLIDAYS:
        candidate += timedelta(days=1)

    return candidate
