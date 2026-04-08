"""
Macro economic calendar — fetches upcoming HIGH-impact events from Finnhub.

Blocks new positions within MACRO_BLOCK_HOURS of a HIGH-impact release
(FOMC, CPI, NFP, etc.). Results are cached for 1 hour since the event
schedule does not change intraday.

Fails silently when FINNHUB_API_KEY is unset.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import requests

logger = logging.getLogger(__name__)

_cache: dict[str, object] = {}   # {"data": list[MacroEvent], "fetched_at": datetime}
_CACHE_TTL_SECONDS = 3600        # 1 hour


@dataclass
class MacroEvent:
    event: str
    release_time: datetime   # UTC
    impact: str              # "HIGH" | "MEDIUM" | "LOW"
    hours_until: float       # negative = already passed


def _cache_fresh() -> bool:
    if not _cache:
        return False
    age = (datetime.now(UTC) - _cache["fetched_at"]).total_seconds()  # type: ignore[arg-type]
    return age < _CACHE_TTL_SECONDS


class MacroCalendar:
    """Fetches and caches upcoming macro economic events from Finnhub."""

    def __init__(self, finnhub_api_key: str = ""):
        self._api_key = finnhub_api_key

    def get_high_impact_events(self, hours_ahead: int = 24) -> list[MacroEvent]:
        """Return HIGH-impact events within the next *hours_ahead* hours.

        Returns an empty list when the API key is absent or the request fails.
        """
        if not self._api_key:
            return []

        if _cache_fresh():
            return self._filter(_cache["data"], hours_ahead)  # type: ignore[arg-type]

        events = self._fetch_all()
        _cache["data"] = events
        _cache["fetched_at"] = datetime.now(UTC)
        return self._filter(events, hours_ahead)

    def _fetch_all(self) -> list[MacroEvent]:
        """Fetch economic calendar from Finnhub for the next 7 days."""
        try:
            now = datetime.now(UTC)
            from_date = now.strftime("%Y-%m-%d")
            to_date = (now + timedelta(days=7)).strftime("%Y-%m-%d")
            resp = requests.get(
                "https://finnhub.io/api/v1/calendar/economic",
                params={"from": from_date, "to": to_date, "token": self._api_key},
                timeout=5,
            )
            if resp.status_code != 200:
                logger.debug("Finnhub macro calendar returned %s", resp.status_code)
                return []
            data = resp.json()
            raw_events = data.get("economicCalendar", []) if isinstance(data, dict) else data
            if not isinstance(raw_events, list):
                return []

            events: list[MacroEvent] = []
            for item in raw_events:
                impact = (item.get("impact") or "").upper()
                if impact != "HIGH":
                    continue
                time_str = item.get("time") or item.get("date") or ""
                if not time_str:
                    continue
                try:
                    # Finnhub returns ISO-8601 strings e.g. "2024-03-20T14:00:00+00:00"
                    release_time = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                    if release_time.tzinfo is None:
                        release_time = release_time.replace(tzinfo=UTC)
                except ValueError:
                    continue
                hours_until = (release_time - datetime.now(UTC)).total_seconds() / 3600
                events.append(MacroEvent(
                    event=item.get("event", "Unknown event").strip(),
                    release_time=release_time,
                    impact=impact,
                    hours_until=round(hours_until, 1),
                ))
            return events
        except Exception as e:
            logger.debug("Macro calendar fetch failed: %s", e)
            return []

    @staticmethod
    def _filter(events: list[MacroEvent], hours_ahead: int) -> list[MacroEvent]:
        """Return events whose release is within the next *hours_ahead* hours."""
        now = datetime.now(UTC)
        cutoff = now + timedelta(hours=hours_ahead)
        result = []
        for ev in events:
            # Recalculate hours_until from live clock (cache may be stale by minutes)
            hours_until = (ev.release_time - now).total_seconds() / 3600
            if 0 <= hours_until <= hours_ahead or ev.release_time <= now <= ev.release_time + timedelta(hours=1):
                result.append(MacroEvent(
                    event=ev.event,
                    release_time=ev.release_time,
                    impact=ev.impact,
                    hours_until=round(hours_until, 1),
                ))
        return result
