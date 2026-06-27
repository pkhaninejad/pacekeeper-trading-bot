"""Single-LIVE strategy designation for the stock bot — issue #109.

Exactly one strategy may place real Trading212 orders; every other active
strategy runs as a paper shadow. The designation is persisted to a small JSON
file so it survives restarts. Promoting a strategy to LIVE while the account is
in live mode requires the same confirmation that already gates live trading.
"""
from __future__ import annotations

import json
from pathlib import Path


class LiveConfirmationRequired(Exception):
    """Raised when designating a LIVE strategy in live mode without confirmation."""


class LiveDesignation:
    """Persisted, single-valued LIVE-strategy pointer (the invariant is structural:
    only one id is ever stored)."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    @property
    def live_strategy_id(self) -> str | None:
        try:
            data = json.loads(self.path.read_text())
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
        sid = data.get("strategy_id") if isinstance(data, dict) else None
        return sid or None

    def is_live(self, strategy_id: str) -> bool:
        return self.live_strategy_id == strategy_id

    def designate(self, strategy_id: str, *, env: str, live_confirmed: bool) -> None:
        """Make ``strategy_id`` the one LIVE strategy.

        In live mode this requires ``live_confirmed`` — otherwise raises
        ``LiveConfirmationRequired``. In demo mode it is always permitted.
        """
        if env == "live" and not live_confirmed:
            raise LiveConfirmationRequired(
                "Live confirmation is required to designate a LIVE strategy in live mode."
            )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"strategy_id": strategy_id}))

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
