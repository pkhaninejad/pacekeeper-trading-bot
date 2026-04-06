# Earnings Calendar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Block new position opens during earnings blackout windows and inject earnings warnings into the Claude prompt, using yfinance as primary data source and Finnhub as fallback.

**Architecture:** Standalone `EarningsCalendar` class instantiated in `TradingEngine`, passed explicitly to `RiskManager.validate()` and `ClaudeStrategy.generate_signals()`. Neither module fetches data itself. 24-hour in-process cache per ticker.

**Tech Stack:** Python 3.14, yfinance (already installed), requests (already installed via yfinance), Pydantic BaseSettings, pytest

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/data/earnings_calendar.py` | **Create** | `EarningsInfo` dataclass, `EarningsCalendar` class, 24h cache, yfinance + Finnhub fetch |
| `src/config/settings.py` | **Modify** | Add `EARNINGS_DAYS_BEFORE`, `EARNINGS_DAYS_AFTER`, `BLOCK_NEW_POSITIONS_ON_EARNINGS`, `FINNHUB_API_KEY` |
| `src/bot/risk_manager.py` | **Modify** | Add `earnings_info` param to `validate()`, block new-position signals in window |
| `src/bot/strategy.py` | **Modify** | Add `earnings_info` param to `generate_signals()` and `_build_market_context()`, inject warnings |
| `src/bot/engine.py` | **Modify** | Instantiate `EarningsCalendar`, fetch earnings info each cycle, pass to risk + strategy |
| `.env.example` | **Modify** | Document 4 new env vars |
| `tests/test_earnings_calendar.py` | **Create** | Unit tests for EarningsCalendar (mocked sources) |
| `tests/test_risk_manager.py` | **Modify** | Add earnings window tests to existing test file |
| `tests/test_strategy.py` | **Modify** | Add earnings warning prompt injection tests |

---

## Task 1: EarningsCalendar skeleton — dataclass and cache

**Files:**
- Create: `src/data/earnings_calendar.py`
- Create: `tests/test_earnings_calendar.py`

- [ ] **Step 1: Write failing tests for EarningsInfo dataclass**

```python
# tests/test_earnings_calendar.py
"""Tests for EarningsCalendar in src/data/earnings_calendar.py."""
from datetime import date, timedelta
from src.data.earnings_calendar import EarningsInfo


class TestEarningsInfo:
    def test_in_window_true(self):
        info = EarningsInfo(
            ticker="AAPL",
            earnings_date=date.today() + timedelta(days=1),
            days_until=1,
            in_window=True,
            source="yfinance",
        )
        assert info.in_window is True
        assert info.source == "yfinance"

    def test_unavailable_not_in_window(self):
        info = EarningsInfo(
            ticker="AAPL",
            earnings_date=None,
            days_until=None,
            in_window=False,
            source="unavailable",
        )
        assert info.earnings_date is None
        assert info.in_window is False
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/python -m pytest tests/test_earnings_calendar.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.data.earnings_calendar'`

- [ ] **Step 3: Create `src/data/earnings_calendar.py` with skeleton**

```python
"""
Earnings calendar — fetches next earnings dates and detects blackout windows.

Data sources (in priority order):
1. yfinance ticker.calendar — free, no key
2. Finnhub /calendar/earnings — free tier, requires FINNHUB_API_KEY

Results are cached per ticker for 24 hours (earnings dates don't change intraday).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal, Optional

logger = logging.getLogger(__name__)

CACHE_TTL_HOURS = 24

_cache: dict[str, dict] = {}  # {ticker: {"data": EarningsInfo, "fetched_at": datetime}}


@dataclass
class EarningsInfo:
    ticker: str
    earnings_date: Optional[date]
    days_until: Optional[int]   # None when earnings_date is None
    in_window: bool
    source: Literal["yfinance", "finnhub", "unavailable"]


def _is_fresh(entry: dict) -> bool:
    age = (datetime.utcnow() - entry["fetched_at"]).total_seconds()
    return age < CACHE_TTL_HOURS * 3600


class EarningsCalendar:
    """Fetches and caches earnings dates; detects blackout windows."""

    def __init__(self, days_before: int = 2, days_after: int = 1, finnhub_api_key: str = ""):
        self.days_before = days_before
        self.days_after = days_after
        self._finnhub_api_key = finnhub_api_key

    def get_next_earnings(self, ticker: str) -> Optional[date]:
        """Return next earnings date for ticker, or None if unavailable."""
        info = self._fetch(ticker)
        return info.earnings_date

    def is_earnings_window(self, ticker: str) -> bool:
        """Return True if today is within the blackout window for ticker."""
        info = self._fetch(ticker)
        return info.in_window

    def get_earnings_info(self, tickers: list[str]) -> dict[str, EarningsInfo]:
        """Bulk-fetch earnings info for all tickers. Returns dict keyed by ticker."""
        return {ticker: self._fetch(ticker) for ticker in tickers}

    def _fetch(self, ticker: str) -> EarningsInfo:
        """Return cached or freshly fetched EarningsInfo."""
        if ticker in _cache and _is_fresh(_cache[ticker]):
            return _cache[ticker]["data"]

        info = self._fetch_yfinance(ticker)
        if info is None and self._finnhub_api_key:
            info = self._fetch_finnhub(ticker)
        if info is None:
            info = EarningsInfo(
                ticker=ticker, earnings_date=None, days_until=None,
                in_window=False, source="unavailable",
            )

        _cache[ticker] = {"data": info, "fetched_at": datetime.utcnow()}
        return info

    def _build_info(self, ticker: str, earnings_date: date, source: Literal["yfinance", "finnhub"]) -> EarningsInfo:
        """Compute days_until and in_window from an earnings date."""
        today = date.today()
        days_until = (earnings_date - today).days
        in_window = -self.days_after <= days_until <= self.days_before
        return EarningsInfo(
            ticker=ticker,
            earnings_date=earnings_date,
            days_until=days_until,
            in_window=in_window,
            source=source,
        )

    def _fetch_yfinance(self, ticker: str) -> Optional[EarningsInfo]:
        """Try yfinance ticker.calendar for next earnings date."""
        raise NotImplementedError

    def _fetch_finnhub(self, ticker: str) -> Optional[EarningsInfo]:
        """Try Finnhub /calendar/earnings for next earnings date."""
        raise NotImplementedError
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
.venv/bin/python -m pytest tests/test_earnings_calendar.py::TestEarningsInfo -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add src/data/earnings_calendar.py tests/test_earnings_calendar.py
git commit -m "feat: add EarningsCalendar skeleton with dataclass and cache"
```

---

## Task 2: Implement yfinance data source

**Files:**
- Modify: `src/data/earnings_calendar.py`
- Modify: `tests/test_earnings_calendar.py`

- [ ] **Step 1: Write failing tests for yfinance fetch**

Add to `tests/test_earnings_calendar.py`:

```python
from unittest.mock import MagicMock, patch
from src.data.earnings_calendar import EarningsCalendar, _cache


class TestFetchYfinance:
    def setup_method(self):
        _cache.clear()

    def test_returns_earnings_info_from_yfinance(self):
        future_date = date.today() + timedelta(days=10)
        mock_ticker = MagicMock()
        mock_ticker.calendar = {"Earnings Date": [future_date]}

        with patch("src.data.earnings_calendar.yf.Ticker", return_value=mock_ticker):
            cal = EarningsCalendar(days_before=2, days_after=1)
            info = cal.get_next_earnings("AAPL")

        assert info == future_date

    def test_in_window_true_when_earnings_tomorrow(self):
        tomorrow = date.today() + timedelta(days=1)
        mock_ticker = MagicMock()
        mock_ticker.calendar = {"Earnings Date": [tomorrow]}

        with patch("src.data.earnings_calendar.yf.Ticker", return_value=mock_ticker):
            cal = EarningsCalendar(days_before=2, days_after=1)
            assert cal.is_earnings_window("AAPL") is True

    def test_not_in_window_when_earnings_far_away(self):
        far_date = date.today() + timedelta(days=30)
        mock_ticker = MagicMock()
        mock_ticker.calendar = {"Earnings Date": [far_date]}

        with patch("src.data.earnings_calendar.yf.Ticker", return_value=mock_ticker):
            cal = EarningsCalendar(days_before=2, days_after=1)
            assert cal.is_earnings_window("AAPL") is False

    def test_in_window_true_when_earnings_yesterday(self):
        yesterday = date.today() - timedelta(days=1)
        mock_ticker = MagicMock()
        mock_ticker.calendar = {"Earnings Date": [yesterday]}

        with patch("src.data.earnings_calendar.yf.Ticker", return_value=mock_ticker):
            cal = EarningsCalendar(days_before=2, days_after=1)
            assert cal.is_earnings_window("AAPL") is True

    def test_returns_none_when_calendar_missing_key(self):
        mock_ticker = MagicMock()
        mock_ticker.calendar = {}

        with patch("src.data.earnings_calendar.yf.Ticker", return_value=mock_ticker):
            cal = EarningsCalendar()
            info = cal.get_next_earnings("AAPL")

        assert info is None

    def test_returns_none_when_yfinance_raises(self):
        with patch("src.data.earnings_calendar.yf.Ticker", side_effect=Exception("network error")):
            cal = EarningsCalendar()
            info = cal.get_next_earnings("AAPL")

        assert info is None

    def test_result_cached_second_call_skips_network(self):
        future_date = date.today() + timedelta(days=5)
        mock_ticker = MagicMock()
        mock_ticker.calendar = {"Earnings Date": [future_date]}

        with patch("src.data.earnings_calendar.yf.Ticker", return_value=mock_ticker) as mock_yf:
            cal = EarningsCalendar()
            cal.get_next_earnings("AAPL")
            cal.get_next_earnings("AAPL")
            assert mock_yf.call_count == 1  # only fetched once
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/python -m pytest tests/test_earnings_calendar.py::TestFetchYfinance -v
```

Expected: `NotImplementedError`

- [ ] **Step 3: Implement `_fetch_yfinance` in `src/data/earnings_calendar.py`**

Replace the `_fetch_yfinance` method:

```python
def _fetch_yfinance(self, ticker: str) -> Optional[EarningsInfo]:
    """Try yfinance ticker.calendar for next earnings date."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        cal = t.calendar
        if not cal or "Earnings Date" not in cal:
            return None
        dates = cal["Earnings Date"]
        if not dates:
            return None
        # calendar returns a list; take the first (soonest) entry
        raw = dates[0]
        if hasattr(raw, "date"):
            earnings_date = raw.date()
        elif isinstance(raw, date):
            earnings_date = raw
        else:
            return None
        return self._build_info(ticker, earnings_date, "yfinance")
    except Exception as e:
        logger.debug("yfinance earnings fetch failed for %s: %s", ticker, e)
        return None
```

Also add `import yfinance as yf` at the top of `_fetch_yfinance` is already inside the method above; add it at module level too:

At the top of the file, after the existing imports add:

```python
try:
    import yfinance as yf
except ImportError:
    yf = None  # type: ignore
```

And update `_fetch_yfinance` to guard against missing yfinance:

```python
def _fetch_yfinance(self, ticker: str) -> Optional[EarningsInfo]:
    """Try yfinance ticker.calendar for next earnings date."""
    if yf is None:
        return None
    try:
        t = yf.Ticker(ticker)
        cal = t.calendar
        if not cal or "Earnings Date" not in cal:
            return None
        dates = cal["Earnings Date"]
        if not dates:
            return None
        raw = dates[0]
        if hasattr(raw, "date"):
            earnings_date = raw.date()
        elif isinstance(raw, date):
            earnings_date = raw
        else:
            return None
        return self._build_info(ticker, earnings_date, "yfinance")
    except Exception as e:
        logger.debug("yfinance earnings fetch failed for %s: %s", ticker, e)
        return None
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
.venv/bin/python -m pytest tests/test_earnings_calendar.py -v
```

Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add src/data/earnings_calendar.py tests/test_earnings_calendar.py
git commit -m "feat: implement yfinance earnings data source with 24h cache"
```

---

## Task 3: Implement Finnhub fallback

**Files:**
- Modify: `src/data/earnings_calendar.py`
- Modify: `tests/test_earnings_calendar.py`

- [ ] **Step 1: Write failing tests for Finnhub fallback**

Add to `tests/test_earnings_calendar.py`:

```python
class TestFetchFinnhub:
    def setup_method(self):
        _cache.clear()

    def test_finnhub_used_when_yfinance_returns_none(self):
        future_date = date.today() + timedelta(days=5)
        finnhub_response = {
            "earningsCalendar": [
                {
                    "symbol": "AAPL",
                    "date": future_date.isoformat(),
                    "epsActual": None,
                    "epsEstimate": 1.5,
                }
            ]
        }
        mock_ticker = MagicMock()
        mock_ticker.calendar = {}  # yfinance returns nothing

        with patch("src.data.earnings_calendar.yf.Ticker", return_value=mock_ticker):
            with patch("src.data.earnings_calendar.requests.get") as mock_get:
                mock_get.return_value.status_code = 200
                mock_get.return_value.json.return_value = finnhub_response

                cal = EarningsCalendar(finnhub_api_key="test-key")
                info = cal._fetch("AAPL")

        assert info.earnings_date == future_date
        assert info.source == "finnhub"

    def test_finnhub_skipped_when_no_api_key(self):
        mock_ticker = MagicMock()
        mock_ticker.calendar = {}

        with patch("src.data.earnings_calendar.yf.Ticker", return_value=mock_ticker):
            with patch("src.data.earnings_calendar.requests.get") as mock_get:
                cal = EarningsCalendar(finnhub_api_key="")
                info = cal._fetch("AAPL")

        mock_get.assert_not_called()
        assert info.source == "unavailable"

    def test_both_fail_returns_unavailable_not_in_window(self):
        mock_ticker = MagicMock()
        mock_ticker.calendar = {}

        with patch("src.data.earnings_calendar.yf.Ticker", return_value=mock_ticker):
            with patch("src.data.earnings_calendar.requests.get", side_effect=Exception("timeout")):
                cal = EarningsCalendar(finnhub_api_key="test-key")
                info = cal._fetch("AAPL")

        assert info.in_window is False
        assert info.source == "unavailable"

    def test_finnhub_empty_calendar_returns_unavailable(self):
        mock_ticker = MagicMock()
        mock_ticker.calendar = {}

        with patch("src.data.earnings_calendar.yf.Ticker", return_value=mock_ticker):
            with patch("src.data.earnings_calendar.requests.get") as mock_get:
                mock_get.return_value.status_code = 200
                mock_get.return_value.json.return_value = {"earningsCalendar": []}

                cal = EarningsCalendar(finnhub_api_key="test-key")
                info = cal._fetch("AAPL")

        assert info.source == "unavailable"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/python -m pytest tests/test_earnings_calendar.py::TestFetchFinnhub -v
```

Expected: `NotImplementedError`

- [ ] **Step 3: Implement `_fetch_finnhub` in `src/data/earnings_calendar.py`**

Add `import requests` near the top of the file (after the stdlib imports):

```python
import requests
```

Replace the `_fetch_finnhub` method:

```python
def _fetch_finnhub(self, ticker: str) -> Optional[EarningsInfo]:
    """Try Finnhub /calendar/earnings for next earnings date."""
    try:
        today = date.today()
        to_date = today + timedelta(days=90)
        url = "https://finnhub.io/api/v1/calendar/earnings"
        params = {
            "from": today.isoformat(),
            "to": to_date.isoformat(),
            "symbol": ticker,
            "token": self._finnhub_api_key,
        }
        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code != 200:
            logger.debug("Finnhub returned %s for %s", resp.status_code, ticker)
            return None
        data = resp.json()
        entries = data.get("earningsCalendar", [])
        if not entries:
            return None
        # First entry is the nearest upcoming earnings
        raw_date = entries[0].get("date")
        if not raw_date:
            return None
        earnings_date = date.fromisoformat(raw_date)
        return self._build_info(ticker, earnings_date, "finnhub")
    except Exception as e:
        logger.debug("Finnhub earnings fetch failed for %s: %s", ticker, e)
        return None
```

- [ ] **Step 4: Run all earnings tests**

```bash
.venv/bin/python -m pytest tests/test_earnings_calendar.py -v
```

Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add src/data/earnings_calendar.py tests/test_earnings_calendar.py
git commit -m "feat: add Finnhub fallback for earnings calendar"
```

---

## Task 4: Add settings env vars

**Files:**
- Modify: `src/config/settings.py`
- Modify: `.env.example`

- [ ] **Step 1: Add 4 new fields to `Settings` in `src/config/settings.py`**

After the `WATCHLIST` field, add:

```python
    # Earnings calendar
    EARNINGS_DAYS_BEFORE: int = 2           # days before earnings to block new positions
    EARNINGS_DAYS_AFTER: int = 1            # days after earnings to stop blocking
    BLOCK_NEW_POSITIONS_ON_EARNINGS: bool = True
    FINNHUB_API_KEY: str = ""               # optional; enables Finnhub fallback
```

- [ ] **Step 2: Run settings tests to confirm nothing broke**

```bash
.venv/bin/python -m pytest tests/test_settings.py -v
```

Expected: all pass

- [ ] **Step 3: Add new vars to `.env.example`**

In `.env.example`, add a new section after the existing risk parameters:

```
# Earnings calendar — avoid trading around earnings announcements
EARNINGS_DAYS_BEFORE=2
EARNINGS_DAYS_AFTER=1
BLOCK_NEW_POSITIONS_ON_EARNINGS=true
FINNHUB_API_KEY=           # get free key at finnhub.io
```

- [ ] **Step 4: Commit**

```bash
git add src/config/settings.py .env.example
git commit -m "feat: add earnings calendar settings (EARNINGS_DAYS_BEFORE/AFTER, BLOCK_NEW_POSITIONS_ON_EARNINGS, FINNHUB_API_KEY)"
```

---

## Task 5: Earnings window check in RiskManager

**Files:**
- Modify: `src/bot/risk_manager.py`
- Modify: `tests/test_risk_manager.py`

- [ ] **Step 1: Write failing tests for earnings block**

Add to `tests/test_risk_manager.py`:

```python
from datetime import date, timedelta
from src.data.earnings_calendar import EarningsInfo


def make_earnings_info(ticker: str, in_window: bool) -> dict:
    return {
        ticker: EarningsInfo(
            ticker=ticker,
            earnings_date=date.today() + timedelta(days=1) if in_window else date.today() + timedelta(days=30),
            days_until=1 if in_window else 30,
            in_window=in_window,
            source="yfinance",
        )
    }


class TestEarningsWindow:
    def setup_method(self):
        self.rm = RiskManager()

    def test_buy_blocked_during_earnings_window(self):
        signal = make_signal(ticker="AAPL", action="BUY", direction="LONG")
        earnings = make_earnings_info("AAPL", in_window=True)
        approved, reason = self.rm.validate(signal, [], make_cash(), earnings_info=earnings)
        assert approved is False
        assert "earnings" in reason.lower()

    def test_close_allowed_during_earnings_window(self):
        signal = make_signal(ticker="AAPL", action="SELL", direction="CLOSE")
        earnings = make_earnings_info("AAPL", in_window=True)
        approved, _ = self.rm.validate(signal, [], make_cash(), earnings_info=earnings)
        assert approved is True

    def test_buy_allowed_outside_earnings_window(self):
        signal = make_signal(ticker="AAPL", action="BUY", direction="LONG")
        earnings = make_earnings_info("AAPL", in_window=False)
        approved, _ = self.rm.validate(signal, [], make_cash(), earnings_info=earnings)
        assert approved is True

    def test_no_earnings_info_does_not_block(self):
        signal = make_signal(ticker="AAPL", action="BUY", direction="LONG")
        approved, _ = self.rm.validate(signal, [], make_cash(), earnings_info=None)
        assert approved is True

    def test_ticker_not_in_earnings_dict_does_not_block(self):
        signal = make_signal(ticker="AAPL", action="BUY", direction="LONG")
        earnings = make_earnings_info("TSLA", in_window=True)  # different ticker
        approved, _ = self.rm.validate(signal, [], make_cash(), earnings_info=earnings)
        assert approved is True
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/python -m pytest tests/test_risk_manager.py::TestEarningsWindow -v
```

Expected: `TypeError: validate() got an unexpected keyword argument 'earnings_info'`

- [ ] **Step 3: Update `RiskManager.validate()` signature and add earnings check**

In `src/bot/risk_manager.py`, update the imports at the top:

```python
from src.config.settings import settings
from src.api.models import TradeSignal, Position, CashInfo
```

Add the `EarningsInfo` import:

```python
from src.config.settings import settings
from src.api.models import TradeSignal, Position, CashInfo
from src.data.earnings_calendar import EarningsInfo
```

Update the `validate` method signature and add the earnings check after the confidence gate:

```python
    def validate(
        self,
        signal: TradeSignal,
        positions: list[Position],
        cash: CashInfo,
        earnings_info: dict[str, "EarningsInfo"] | None = None,
    ) -> tuple[bool, str]:
        """
        Returns (approved, reason).
        """
        # Confidence gate
        if signal.confidence < self.min_confidence:
            return False, f"Confidence {signal.confidence:.2f} below threshold {self.min_confidence}"

        # Earnings window gate (only blocks new position opens, not CLOSE)
        is_close = signal.direction == "CLOSE"
        if (
            not is_close
            and settings.BLOCK_NEW_POSITIONS_ON_EARNINGS
            and earnings_info is not None
        ):
            info = earnings_info.get(signal.ticker)
            if info is not None and info.in_window:
                days = info.days_until
                direction = "in" if days is not None and days >= 0 else "ago"
                count = abs(days) if days is not None else "?"
                return False, (
                    f"Earnings window blocked: {signal.ticker} earnings "
                    f"{count} day(s) {direction} — no new positions allowed"
                )

        # Max open positions gate (only for new positions)
        position_tickers = {p.ticker for p in positions}
        is_new = signal.ticker not in position_tickers

        if is_new and not is_close and len(positions) >= self.max_open_positions:
            return False, f"Max open positions ({self.max_open_positions}) reached"

        # Cash availability (for buys / shorts)
        if signal.action == "BUY" and signal.suggested_quantity and signal.suggested_price:
            required = signal.suggested_quantity * signal.suggested_price
            if required > cash.free:
                return False, f"Insufficient cash: need {required:.2f}, have {cash.free:.2f}"

        # Position size limit
        if signal.suggested_quantity and signal.suggested_price:
            trade_value = abs(signal.suggested_quantity) * signal.suggested_price
            max_allowed = cash.total * self.max_position_pct
            if trade_value > max_allowed:
                # Auto-scale down
                signal.suggested_quantity = (max_allowed / signal.suggested_price) * (
                    1 if signal.suggested_quantity > 0 else -1
                )
                logger.info(
                    "Scaled position size for %s to %.4f (max %.2f)",
                    signal.ticker, signal.suggested_quantity, max_allowed,
                )

        # Don't double up same direction
        existing = next((p for p in positions if p.ticker == signal.ticker), None)
        if existing and not is_close:
            if signal.direction == "LONG" and existing.is_long:
                return False, f"Already long {signal.ticker}"
            if signal.direction == "SHORT" and existing.is_short:
                return False, f"Already short {signal.ticker}"

        return True, "Approved"
```

- [ ] **Step 4: Run all risk manager tests**

```bash
.venv/bin/python -m pytest tests/test_risk_manager.py -v
```

Expected: all tests pass (existing tests still pass because `earnings_info=None` by default)

- [ ] **Step 5: Commit**

```bash
git add src/bot/risk_manager.py tests/test_risk_manager.py
git commit -m "feat: block new position signals during earnings window in RiskManager"
```

---

## Task 6: Inject earnings warnings into Claude prompt

**Files:**
- Modify: `src/bot/strategy.py`
- Modify: `tests/test_strategy.py`

- [ ] **Step 1: Write failing tests for earnings prompt injection**

Add to `tests/test_strategy.py`:

```python
from datetime import date, timedelta
from src.data.earnings_calendar import EarningsInfo


def make_earnings_info_dict(**overrides) -> dict:
    """Build an earnings_info dict for AAPL."""
    defaults = {
        "AAPL": EarningsInfo(
            ticker="AAPL",
            earnings_date=date.today() + timedelta(days=1),
            days_until=1,
            in_window=True,
            source="yfinance",
        )
    }
    defaults.update(overrides)
    return defaults


class TestEarningsPromptInjection:
    def test_warning_line_when_in_window(self):
        earnings = make_earnings_info_dict()
        ctx = _build_market_context([], make_cash(), ["AAPL"], [], earnings_info=earnings)
        assert "⚠️" in ctx
        assert "AAPL" in ctx
        assert "earnings" in ctx.lower()

    def test_clear_line_when_not_in_window(self):
        earnings = {
            "AAPL": EarningsInfo(
                ticker="AAPL",
                earnings_date=date.today() + timedelta(days=30),
                days_until=30,
                in_window=False,
                source="yfinance",
            )
        }
        ctx = _build_market_context([], make_cash(), ["AAPL"], [], earnings_info=earnings)
        assert "✅" in ctx
        assert "AAPL" in ctx

    def test_no_earnings_section_when_no_info(self):
        ctx = _build_market_context([], make_cash(), ["AAPL"], [], earnings_info=None)
        assert "EARNINGS" not in ctx

    def test_earnings_section_present_when_info_provided(self):
        earnings = make_earnings_info_dict()
        ctx = _build_market_context([], make_cash(), ["AAPL"], [], earnings_info=earnings)
        assert "EARNINGS" in ctx
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/python -m pytest tests/test_strategy.py::TestEarningsPromptInjection -v
```

Expected: `TypeError: _build_market_context() got an unexpected keyword argument 'earnings_info'`

- [ ] **Step 3: Update `_build_market_context` in `src/bot/strategy.py`**

Update the import at the top of `src/bot/strategy.py`:

```python
from src.data.earnings_calendar import EarningsInfo
```

Update the `_build_market_context` function signature to add `earnings_info` and `price_data` defaults, and append an earnings section:

```python
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
                    f"  ⚠️  {ticker}: earnings {count} day(s) {direction} "
                    f"({info.earnings_date}) — new positions blocked by risk manager"
                )
            elif info.earnings_date:
                earnings_lines.append(
                    f"  ✅  {ticker}: next earnings {info.earnings_date} — no restriction"
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
```

- [ ] **Step 4: Update `generate_signals` to accept and forward `earnings_info`**

Replace the entire `generate_signals` method in `src/bot/strategy.py`:

```python
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
```

- [ ] **Step 5: Run all strategy tests**

```bash
.venv/bin/python -m pytest tests/test_strategy.py -v
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add src/bot/strategy.py tests/test_strategy.py
git commit -m "feat: inject earnings warnings into Claude strategy prompt"
```

---

## Task 7: Wire EarningsCalendar into TradingEngine

**Files:**
- Modify: `src/bot/engine.py`

- [ ] **Step 1: Add `EarningsCalendar` import and instantiation in `TradingEngine.__init__`**

At the top of `src/bot/engine.py`, add the import:

```python
from src.data.earnings_calendar import EarningsCalendar
```

In `TradingEngine.__init__`, after `self.risk = RiskManager()`, add:

```python
        self.earnings = EarningsCalendar(
            days_before=settings.EARNINGS_DAYS_BEFORE,
            days_after=settings.EARNINGS_DAYS_AFTER,
            finnhub_api_key=settings.FINNHUB_API_KEY,
        )
```

- [ ] **Step 2: Fetch earnings info in `_cycle` and pass to risk + strategy**

In `TradingEngine._cycle`, after the second `positions = await client.get_positions()` call (line ~147, after `_manage_exits`), add:

```python
            # Fetch earnings calendar for watchlist
            earnings_info = self.earnings.get_earnings_info(settings.WATCHLIST)
```

Update the `generate_signals` call to pass `earnings_info`:

```python
            signals = self.strategy.generate_signals(
                positions, cash, settings.WATCHLIST, instruments, earnings_info
            )
```

Update the `risk.validate` call to pass `earnings_info`:

```python
                approved, reason = self.risk.validate(signal, positions, cash, earnings_info)
```

- [ ] **Step 3: Run all tests to confirm nothing broke**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all tests pass

- [ ] **Step 4: Commit**

```bash
git add src/bot/engine.py
git commit -m "feat: wire EarningsCalendar into TradingEngine cycle"
```

---

## Task 8: Final integration check and PR

**Files:** none new

- [ ] **Step 1: Run full test suite**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all tests pass, no warnings about missing imports

- [ ] **Step 2: Verify `.env.example` is complete**

Check that `.env.example` contains all 4 new entries:
- `EARNINGS_DAYS_BEFORE`
- `EARNINGS_DAYS_AFTER`
- `BLOCK_NEW_POSITIONS_ON_EARNINGS`
- `FINNHUB_API_KEY`

- [ ] **Step 3: Create PR targeting the main branch**

```bash
gh pr create \
  --title "feat: earnings calendar — avoid trading around earnings dates (closes #14)" \
  --body "$(cat <<'EOF'
## Summary
- Adds `EarningsCalendar` class in `src/data/earnings_calendar.py` with yfinance primary + Finnhub fallback
- `RiskManager.validate()` blocks new position signals during configurable blackout window (default: 2 days before, 1 day after)
- CLOSE signals always pass — reducing risk during earnings is always permitted
- Claude prompt includes per-ticker earnings warnings (⚠️ in window / ✅ no restriction)
- 24-hour in-process cache per ticker
- Configurable via `EARNINGS_DAYS_BEFORE`, `EARNINGS_DAYS_AFTER`, `BLOCK_NEW_POSITIONS_ON_EARNINGS`, `FINNHUB_API_KEY`

## Test plan
- [ ] `pytest tests/test_earnings_calendar.py` — all new unit tests pass
- [ ] `pytest tests/test_risk_manager.py` — earnings window tests + all existing tests pass
- [ ] `pytest tests/test_strategy.py` — earnings prompt injection tests + all existing tests pass
- [ ] Full suite: `pytest tests/ -v` — no regressions

Closes #14

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
