# Market Regime Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect market regime from SPY + VIX each cycle, scale/block new LONG positions in bearish regimes, inject regime context into the Claude prompt, and surface the regime label + VIX on the dashboard.

**Architecture:** A new `RegimeDetector` class in `src/data/market_regime.py` fetches SPY and `^VIX` via yfinance (5-min cache), classifies the regime into BULL/NEUTRAL/BEAR/EXTREME_FEAR, and returns a `MarketRegime` dataclass with a `risk_multiplier`. The engine fetches this once per cycle, stores it in `BotStatus`, and passes it to `RiskManager.validate()` (blocks/scales) and `AIStrategy.generate_signals()` (prompt injection). The dashboard SSE stream already carries `BotStatus`, so a new HTML badge surfaces the regime with no extra polling.

**Tech Stack:** Python 3.14, yfinance (already installed), pydantic v2, FastAPI SSE, vanilla JS dashboard.

---

## File Map

| File | Action |
|---|---|
| `src/data/market_regime.py` | **Create** — `MarketRegime` dataclass + `RegimeDetector` |
| `tests/test_market_regime.py` | **Create** — regime classification + risk integration tests |
| `src/api/models.py` | **Modify** — add `market_regime`, `vix` fields to `BotStatus` |
| `src/bot/risk_manager.py` | **Modify** — add `regime` param to `validate()` |
| `src/bot/strategy.py` | **Modify** — add `regime` param to `generate_signals()` + `_build_market_context()` |
| `src/bot/engine.py` | **Modify** — fetch regime per cycle, set status fields, pass downstream |
| `src/dashboard/templates/dashboard.html` | **Modify** — add regime badge CSS + HTML + JS update logic |

---

## Task 1: Create `src/data/market_regime.py` with tests (TDD)

**Files:**
- Create: `tests/test_market_regime.py`
- Create: `src/data/market_regime.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_market_regime.py`:

```python
"""Tests for src/data/market_regime.py — regime classification."""

import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from src.data.market_regime import MarketRegime, RegimeDetector


def _make_hist(closes: list[float], vix_closes: list[float] | None = None) -> tuple:
    """Return (spy_hist, vix_hist) as pandas DataFrames."""
    spy = pd.DataFrame({"Close": closes})
    vix_closes = vix_closes or [15.0] * len(closes)
    vix = pd.DataFrame({"Close": vix_closes})
    return spy, vix


def _patch_yf(spy_closes: list[float], vix_closes: list[float]):
    """Context manager: patches yfinance.Ticker so SPY and ^VIX return given closes."""
    spy_hist, vix_hist = _make_hist(spy_closes, vix_closes)

    def fake_ticker(sym):
        t = MagicMock()
        t.history.return_value = spy_hist if sym == "SPY" else vix_hist
        return t

    return patch("src.data.market_regime.yf.Ticker", side_effect=fake_ticker)


# ---------------------------------------------------------------------------
# Regime classification
# ---------------------------------------------------------------------------

class TestRegimeClassification:
    def setup_method(self):
        self.detector = RegimeDetector()

    def test_extreme_fear_vix_above_30(self):
        # VIX=35, SPY above both SMAs → still EXTREME_FEAR
        spy_closes = [100.0] * 30 + [105.0]  # 31 days, rising
        vix_closes = [35.0] * 31
        with _patch_yf(spy_closes, vix_closes):
            regime = self.detector.get_regime(use_cache=False)
        assert regime.label == "EXTREME_FEAR"
        assert regime.risk_multiplier == 0.0
        assert regime.vix == pytest.approx(35.0)

    def test_bear_vix_above_25(self):
        # VIX=27, SPY flat (above SMAs) → BEAR because VIX > 25
        spy_closes = [100.0] * 31
        vix_closes = [27.0] * 31
        with _patch_yf(spy_closes, vix_closes):
            regime = self.detector.get_regime(use_cache=False)
        assert regime.label == "BEAR"
        assert regime.risk_multiplier == pytest.approx(0.5)

    def test_bear_spy_below_both_smas(self):
        # VIX=18 (below 20), but SPY has been falling → below SMA10 and SMA30
        # Build a downtrend: 30 days at 100, then drop to 80
        spy_closes = [100.0] * 30 + [80.0]
        vix_closes = [18.0] * 31
        with _patch_yf(spy_closes, vix_closes):
            regime = self.detector.get_regime(use_cache=False)
        assert regime.label == "BEAR"
        assert regime.risk_multiplier == pytest.approx(0.5)

    def test_neutral_vix_above_20(self):
        # VIX=22, SPY flat (above SMAs)
        spy_closes = [100.0] * 31
        vix_closes = [22.0] * 31
        with _patch_yf(spy_closes, vix_closes):
            regime = self.detector.get_regime(use_cache=False)
        assert regime.label == "NEUTRAL"
        assert regime.risk_multiplier == pytest.approx(0.8)

    def test_bull_low_vix_spy_above_smas(self):
        # VIX=15, SPY steadily rising → above both SMAs
        spy_closes = [90.0 + i * 0.5 for i in range(31)]  # 90, 90.5, ..., 105
        vix_closes = [15.0] * 31
        with _patch_yf(spy_closes, vix_closes):
            regime = self.detector.get_regime(use_cache=False)
        assert regime.label == "BULL"
        assert regime.risk_multiplier == pytest.approx(1.0)

    def test_fallback_on_yfinance_unavailable(self):
        with patch("src.data.market_regime.yf", None):
            regime = self.detector.get_regime(use_cache=False)
        assert regime.label == "NEUTRAL"
        assert regime.risk_multiplier == pytest.approx(0.8)
        assert regime.vix == pytest.approx(0.0)

    def test_fallback_on_empty_history(self):
        def fake_ticker(sym):
            t = MagicMock()
            t.history.return_value = pd.DataFrame()
            return t

        with patch("src.data.market_regime.yf.Ticker", side_effect=fake_ticker):
            regime = self.detector.get_regime(use_cache=False)
        assert regime.label == "NEUTRAL"


# ---------------------------------------------------------------------------
# Cache behaviour
# ---------------------------------------------------------------------------

class TestRegimeCache:
    def setup_method(self):
        # Classification tests write to module-level _cache as a side effect
        # (even with use_cache=False, _fetch() always updates it).
        # Clear it so this test starts with a cold cache.
        import src.data.market_regime as mr
        mr._cache.clear()

    def test_cache_returns_same_object_within_ttl(self):
        detector = RegimeDetector()
        spy_closes = [100.0] * 31
        vix_closes = [15.0] * 31
        with _patch_yf(spy_closes, vix_closes) as mock_ticker:
            r1 = detector.get_regime(use_cache=True)
            r2 = detector.get_regime(use_cache=True)
        # yf.Ticker called once per symbol = 2 total (SPY + ^VIX), not 4
        assert mock_ticker.call_count == 2
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/python -m pytest tests/test_market_regime.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'src.data.market_regime'`

- [ ] **Step 3: Create `src/data/market_regime.py`**

```python
"""
Market regime detection — classifies current market as BULL/NEUTRAL/BEAR/EXTREME_FEAR.

Uses SPY (trend) and ^VIX (fear gauge) via yfinance. Results are cached for 5 minutes.
Fails silently: returns NEUTRAL if yfinance is unavailable or the fetch fails.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
except ImportError:
    yf = None  # type: ignore[assignment]

_CACHE_TTL = 300  # seconds — 5 minutes, same as price_feed.py
_cache: dict = {}  # {"regime": MarketRegime, "fetched_at": datetime}


@dataclass
class MarketRegime:
    label: str            # "BULL" | "NEUTRAL" | "BEAR" | "EXTREME_FEAR"
    vix: float            # latest VIX close
    spy_change_pct: float # SPY 1-day % change
    risk_multiplier: float  # 1.0 / 0.8 / 0.5 / 0.0


_NEUTRAL_FALLBACK = MarketRegime(
    label="NEUTRAL", vix=0.0, spy_change_pct=0.0, risk_multiplier=0.8
)


def _cache_fresh() -> bool:
    if not _cache:
        return False
    age = (datetime.utcnow() - _cache["fetched_at"]).total_seconds()
    return age < _CACHE_TTL


def _classify(vix: float, spy_above_sma10: bool, spy_above_sma30: bool) -> tuple[str, float]:
    """Return (label, risk_multiplier) based on VIX level and SPY vs SMAs."""
    if vix > 30:
        return "EXTREME_FEAR", 0.0
    if vix > 25 or (not spy_above_sma10 and not spy_above_sma30):
        return "BEAR", 0.5
    if vix > 20 or not spy_above_sma10 or not spy_above_sma30:
        return "NEUTRAL", 0.8
    return "BULL", 1.0


class RegimeDetector:
    """Fetches SPY + VIX from yfinance and classifies the market regime."""

    def get_regime(self, use_cache: bool = True) -> MarketRegime:
        """Return the current MarketRegime. Uses cache if fresh and use_cache=True."""
        if use_cache and _cache_fresh():
            return _cache["regime"]

        regime = self._fetch()
        _cache["regime"] = regime
        _cache["fetched_at"] = datetime.utcnow()
        return regime

    def _fetch(self) -> MarketRegime:
        if yf is None:
            logger.warning("yfinance not available — regime defaulting to NEUTRAL")
            return _NEUTRAL_FALLBACK

        try:
            spy_hist = yf.Ticker("SPY").history(period="3mo", auto_adjust=True)
            vix_hist = yf.Ticker("^VIX").history(period="5d", auto_adjust=True)

            if spy_hist.empty or vix_hist.empty:
                logger.warning("Regime fetch: empty history — defaulting to NEUTRAL")
                return _NEUTRAL_FALLBACK

            spy_closes = spy_hist["Close"].dropna().tolist()
            vix_closes = vix_hist["Close"].dropna().tolist()

            if len(spy_closes) < 30 or not vix_closes:
                logger.warning("Regime fetch: insufficient history — defaulting to NEUTRAL")
                return _NEUTRAL_FALLBACK

            current_spy = spy_closes[-1]
            prev_spy = spy_closes[-2]
            spy_change_pct = ((current_spy - prev_spy) / prev_spy * 100) if prev_spy else 0.0

            sma10 = sum(spy_closes[-10:]) / 10
            sma30 = sum(spy_closes[-30:]) / 30
            spy_above_sma10 = current_spy > sma10
            spy_above_sma30 = current_spy > sma30

            vix = vix_closes[-1]
            label, risk_multiplier = _classify(vix, spy_above_sma10, spy_above_sma30)

            regime = MarketRegime(
                label=label,
                vix=round(vix, 2),
                spy_change_pct=round(spy_change_pct, 2),
                risk_multiplier=risk_multiplier,
            )
            logger.info(
                "Market regime: %s (VIX=%.1f, SPY 1d=%+.1f%%, above SMA10=%s, SMA30=%s)",
                label, vix, spy_change_pct, spy_above_sma10, spy_above_sma30,
            )
            return regime

        except Exception as e:
            logger.warning("Regime detection failed: %s — defaulting to NEUTRAL", e)
            return _NEUTRAL_FALLBACK
```

- [ ] **Step 4: Run tests again**

```bash
.venv/bin/python -m pytest tests/test_market_regime.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/data/market_regime.py tests/test_market_regime.py
git commit -m "feat: add MarketRegime detection (SPY + VIX via yfinance)"
```

---

## Task 2: Add `market_regime` and `vix` to `BotStatus`

**Files:**
- Modify: `src/api/models.py:113-124`

- [ ] **Step 1: Add two optional fields to `BotStatus`**

In `src/api/models.py`, find the `BotStatus` class and add two fields at the end:

```python
class BotStatus(BaseModel):
    enabled: bool
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    total_trades_today: int = 0
    total_pnl: float = 0.0
    open_positions: int = 0
    signals_generated: int = 0
    environment: str = "demo"
    market_open: bool = False
    next_market_open: Optional[datetime] = None
    market_regime: Optional[str] = None
    vix: Optional[float] = None
```

- [ ] **Step 2: Verify existing model tests still pass**

```bash
.venv/bin/python -m pytest tests/test_models.py -v
```

Expected: All existing tests PASS.

- [ ] **Step 3: Commit**

```bash
git add src/api/models.py
git commit -m "feat: add market_regime and vix fields to BotStatus"
```

---

## Task 3: Update `RiskManager.validate()` to apply regime (TDD)

**Files:**
- Modify: `tests/test_market_regime.py` (append new test class)
- Modify: `src/bot/risk_manager.py:22-106`

- [ ] **Step 1: Append regime tests to `tests/test_market_regime.py`**

Add the following at the end of `tests/test_market_regime.py`:

```python
# ---------------------------------------------------------------------------
# RiskManager regime integration
# ---------------------------------------------------------------------------

from src.api.models import TradeSignal, CashInfo
from src.bot.risk_manager import RiskManager


def make_signal(**kwargs) -> TradeSignal:
    defaults = dict(
        ticker="AAPL", action="BUY", direction="LONG",
        confidence=0.8, reasoning="test", order_type="MARKET",
    )
    defaults.update(kwargs)
    return TradeSignal(**defaults)


def make_cash(**kwargs) -> CashInfo:
    defaults = dict(free=10_000.0, total=20_000.0, ppl=0.0, result=0.0, invested=10_000.0, pieCash=0.0)
    defaults.update(kwargs)
    return CashInfo(**defaults)


class TestRiskManagerRegime:
    def setup_method(self):
        self.rm = RiskManager()

    def test_extreme_fear_blocks_new_long(self):
        regime = MarketRegime(label="EXTREME_FEAR", vix=35.0, spy_change_pct=-4.0, risk_multiplier=0.0)
        signal = make_signal(action="BUY", direction="LONG")
        approved, reason = self.rm.validate(signal, [], make_cash(), regime=regime)
        assert approved is False
        assert "EXTREME_FEAR" in reason

    def test_extreme_fear_does_not_block_close(self):
        regime = MarketRegime(label="EXTREME_FEAR", vix=35.0, spy_change_pct=-4.0, risk_multiplier=0.0)
        signal = make_signal(action="SELL", direction="CLOSE")
        approved, _ = self.rm.validate(signal, [], make_cash(), regime=regime)
        assert approved is True

    def test_bear_scales_position_size_to_50pct(self):
        regime = MarketRegime(label="BEAR", vix=27.0, spy_change_pct=-2.0, risk_multiplier=0.5)
        # suggested_quantity large enough to trigger scaling
        # max_position_pct = 0.05, total = 20_000 → max = 1_000
        # With BEAR multiplier 0.5 → effective max = 500 → qty scaled to 500/100 = 5
        signal = make_signal(
            suggested_quantity=200.0,   # 200 * 100 = 20,000 — exceeds max
            suggested_price=100.0,
        )
        cash = make_cash(free=30_000.0, total=20_000.0)
        self.rm.validate(signal, [], cash, regime=regime)
        expected_qty = (20_000.0 * 0.05 * 0.5) / 100.0  # 5.0
        assert signal.suggested_quantity == pytest.approx(expected_qty)

    def test_neutral_scales_position_size_to_80pct(self):
        regime = MarketRegime(label="NEUTRAL", vix=22.0, spy_change_pct=-0.5, risk_multiplier=0.8)
        signal = make_signal(
            suggested_quantity=200.0,
            suggested_price=100.0,
        )
        cash = make_cash(free=30_000.0, total=20_000.0)
        self.rm.validate(signal, [], cash, regime=regime)
        expected_qty = (20_000.0 * 0.05 * 0.8) / 100.0  # 8.0
        assert signal.suggested_quantity == pytest.approx(expected_qty)

    def test_bull_does_not_scale(self):
        regime = MarketRegime(label="BULL", vix=15.0, spy_change_pct=0.5, risk_multiplier=1.0)
        signal = make_signal(
            suggested_quantity=200.0,
            suggested_price=100.0,
        )
        cash = make_cash(free=30_000.0, total=20_000.0)
        self.rm.validate(signal, [], cash, regime=regime)
        expected_qty = (20_000.0 * 0.05 * 1.0) / 100.0  # 10.0
        assert signal.suggested_quantity == pytest.approx(expected_qty)

    def test_no_regime_uses_full_size(self):
        signal = make_signal(
            suggested_quantity=200.0,
            suggested_price=100.0,
        )
        cash = make_cash(free=30_000.0, total=20_000.0)
        self.rm.validate(signal, [], cash, regime=None)
        expected_qty = (20_000.0 * 0.05) / 100.0  # 10.0
        assert signal.suggested_quantity == pytest.approx(expected_qty)
```

- [ ] **Step 2: Run new tests to confirm they fail**

```bash
.venv/bin/python -m pytest tests/test_market_regime.py::TestRiskManagerRegime -v 2>&1 | head -20
```

Expected: `TypeError` — `validate()` does not yet accept `regime`.

- [ ] **Step 3: Update `src/bot/risk_manager.py`**

Change the `validate()` signature and add regime logic. The full updated method:

```python
from src.data.market_regime import MarketRegime  # add to imports at top
```

Replace the `validate` method (lines 22–106):

```python
    def validate(
        self,
        signal: TradeSignal,
        positions: list[Position],
        cash: CashInfo,
        earnings_info: dict[str, "EarningsInfo"] | None = None,
        macro_events: list["MacroEvent"] | None = None,
        regime: "MarketRegime | None" = None,
    ) -> tuple[bool, str]:
        """
        Returns (approved, reason).
        """
        normalized_ticker = self._normalize_ticker(signal.ticker)

        # Confidence gate
        if signal.confidence < self.min_confidence:
            return False, f"Confidence {signal.confidence:.2f} below threshold {self.min_confidence}"

        is_close = signal.direction == "CLOSE"

        # Macro calendar gate (only blocks new position opens, not CLOSE)
        if (
            not is_close
            and settings.BLOCK_NEW_POSITIONS_ON_MACRO
            and macro_events
        ):
            blocking = [e for e in macro_events if e.hours_until <= settings.MACRO_BLOCK_HOURS]
            if blocking:
                names = ", ".join(e.event for e in blocking[:3])
                return False, f"Macro event block: {names} within {settings.MACRO_BLOCK_HOURS}h — no new positions"

        # Earnings window gate (only blocks new position opens, not CLOSE)
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

        # Market regime gate (only blocks new LONG opens, not CLOSE)
        if not is_close and signal.direction == "LONG" and regime is not None:
            if regime.label == "EXTREME_FEAR":
                return False, f"EXTREME_FEAR regime (VIX {regime.vix:.1f} >30): new LONG positions blocked"

        # Equity accounts on Trading212 do not support opening short positions.
        if signal.direction == "SHORT":
            return False, f"Short selling is not supported for {normalized_ticker}"

        # Max open positions gate (only for new positions)
        existing = self._find_position(positions, signal.ticker)
        is_new = existing is None

        if is_new and not is_close and len(positions) >= self.max_open_positions:
            return False, f"Max open positions ({self.max_open_positions}) reached"

        # Cash availability (for buys / shorts)
        if signal.action == "BUY" and signal.suggested_quantity and signal.suggested_price:
            required = signal.suggested_quantity * signal.suggested_price
            if required > cash.free:
                return False, f"Insufficient cash: need {required:.2f}, have {cash.free:.2f}"

        # Position size limit — apply regime multiplier to effective max
        if signal.suggested_quantity and signal.suggested_price:
            multiplier = regime.risk_multiplier if (regime and not is_close) else 1.0
            effective_max = cash.total * self.max_position_pct * multiplier
            trade_value = abs(signal.suggested_quantity) * signal.suggested_price
            if trade_value > effective_max:
                signal.suggested_quantity = (effective_max / signal.suggested_price) * (
                    1 if signal.suggested_quantity > 0 else -1
                )
                logger.info(
                    "Scaled position size for %s to %.4f (effective_max %.2f, regime=%s)",
                    signal.ticker, signal.suggested_quantity, effective_max,
                    regime.label if regime else "none",
                )

        # Don't double up same direction
        if existing and not is_close:
            if signal.direction == "LONG" and existing.is_long:
                return False, f"Already long {signal.ticker}"
            if signal.direction == "SHORT" and existing.is_short:
                return False, f"Already short {signal.ticker}"

        return True, "Approved"
```

- [ ] **Step 4: Run all market regime tests**

```bash
.venv/bin/python -m pytest tests/test_market_regime.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Run existing risk manager tests to check nothing regressed**

```bash
.venv/bin/python -m pytest tests/test_risk_manager.py -v
```

Expected: All tests PASS. (Existing tests pass `regime=None` implicitly via default.)

- [ ] **Step 6: Commit**

```bash
git add src/bot/risk_manager.py tests/test_market_regime.py
git commit -m "feat: apply market regime multiplier in RiskManager.validate()"
```

---

## Task 4: Inject regime into the Claude strategy prompt (TDD)

**Files:**
- Modify: `tests/test_strategy.py` (append new tests)
- Modify: `src/bot/strategy.py:149-260`

- [ ] **Step 1: Append regime tests to `tests/test_strategy.py`**

Add at the end of `tests/test_strategy.py`:

```python
from src.data.market_regime import MarketRegime


class TestBuildMarketContextRegime:
    def _ctx(self, regime):
        from src.bot.strategy import _build_market_context
        from src.api.models import CashInfo
        cash = CashInfo(free=5000, total=10000, ppl=0, result=0, invested=5000, pieCash=0)
        return _build_market_context([], cash, ["AAPL"], [], regime=regime)

    def test_regime_section_present_when_regime_provided(self):
        regime = MarketRegime(label="BEAR", vix=28.4, spy_change_pct=-3.2, risk_multiplier=0.5)
        ctx = self._ctx(regime)
        assert "MARKET REGIME" in ctx
        assert "BEAR" in ctx
        assert "28.4" in ctx

    def test_regime_section_absent_when_none(self):
        ctx = self._ctx(None)
        assert "MARKET REGIME" not in ctx

    def test_extreme_fear_guidance_in_prompt(self):
        regime = MarketRegime(label="EXTREME_FEAR", vix=32.0, spy_change_pct=-5.0, risk_multiplier=0.0)
        ctx = self._ctx(regime)
        assert "blocked" in ctx.lower() or "CLOSE" in ctx

    def test_bull_guidance_in_prompt(self):
        regime = MarketRegime(label="BULL", vix=15.0, spy_change_pct=0.8, risk_multiplier=1.0)
        ctx = self._ctx(regime)
        assert "BULL" in ctx
        assert "normal" in ctx.lower()
```

- [ ] **Step 2: Run new tests to confirm they fail**

```bash
.venv/bin/python -m pytest tests/test_strategy.py::TestBuildMarketContextRegime -v 2>&1 | head -20
```

Expected: `TypeError` — `_build_market_context()` does not yet accept `regime`.

- [ ] **Step 3: Update `src/bot/strategy.py`**

**3a.** Add the import near the top (after existing data imports):

```python
from src.data.market_regime import MarketRegime
```

**3b.** Add the `_build_regime_section` helper after `_build_macro_section`:

```python
_REGIME_GUIDANCE = {
    "BULL": "Bullish regime — normal signal generation.",
    "NEUTRAL": "Neutral regime — apply standard confidence thresholds.",
    "BEAR": "Bearish regime — raise the confidence bar for new LONGs, favour CLOSE signals on existing positions.",
    "EXTREME_FEAR": "Extreme fear (VIX >30) — new LONG positions are blocked by the risk manager. Focus only on CLOSE signals.",
}


def _build_regime_section(regime: "MarketRegime | None") -> str:
    """Format the === MARKET REGIME === prompt section."""
    if regime is None:
        return ""
    guidance = _REGIME_GUIDANCE.get(regime.label, "")
    return (
        f"\n=== MARKET REGIME ===\n"
        f"  Label: {regime.label}  |  VIX: {regime.vix:.1f}  |  SPY 1d: {regime.spy_change_pct:+.1f}%\n"
        f"  {guidance}\n"
    )
```

**3c.** Update `_build_market_context` signature to accept `regime`:

```python
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
    regime: "MarketRegime | None" = None,
) -> str:
```

**3d.** Inside `_build_market_context`, add the regime section. Replace the line:

```python
    macro_section = _build_macro_section(macro_events, settings.MACRO_BLOCK_HOURS)
```

with:

```python
    macro_section = _build_macro_section(macro_events, settings.MACRO_BLOCK_HOURS)
    regime_section = _build_regime_section(regime)
```

**3e.** Replace the `context = f"""..."""` block's `{macro_section}` reference. Find this line in the f-string:

```python
{chr(10).join(price_lines) if price_lines else '  (unavailable)'}
{earnings_section}{macro_section}{news_section}{perf_section}
```

Change it to:

```python
{chr(10).join(price_lines) if price_lines else '  (unavailable)'}
{earnings_section}{macro_section}{regime_section}{news_section}{perf_section}
```

**3f.** Update `AIStrategy.generate_signals()` to accept and pass `regime`:

Add `regime: "MarketRegime | None" = None` to the method signature and pass it to `_build_market_context`:

```python
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
        regime: "MarketRegime | None" = None,
    ) -> list[TradeSignal]:
        """Call the configured LLM provider and parse trade signals."""
        if provider_config is None:
            provider_config = load_provider_config()

        price_data = get_price_summary(watchlist)
        user_prompt = _build_market_context(
            positions, cash, watchlist, instruments, price_data,
            earnings_info, news_data, macro_events, outcome_log,
            regime=regime,
        )
        # ... rest of method unchanged
```

- [ ] **Step 4: Run strategy tests**

```bash
.venv/bin/python -m pytest tests/test_strategy.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bot/strategy.py tests/test_strategy.py
git commit -m "feat: inject market regime context into Claude strategy prompt"
```

---

## Task 5: Wire regime into `TradingEngine._cycle()`

**Files:**
- Modify: `src/bot/engine.py:1-27` (imports) and `src/bot/engine.py:30-70` (`__init__`) and `src/bot/engine.py:233-332` (`_cycle`)

- [ ] **Step 1: Add import to `src/bot/engine.py`**

After the existing data imports (line ~26), add:

```python
from src.data.market_regime import RegimeDetector
```

- [ ] **Step 2: Add `regime_detector` to `__init__`**

After `self.macro = MacroCalendar(...)` (line ~47), add:

```python
        self.regime_detector = RegimeDetector()
```

- [ ] **Step 3: Fetch regime in `_cycle()` and set status**

In `_cycle()`, after the line `macro_events = self.macro.get_high_impact_events(hours_ahead=24)` (line ~295), add:

```python
            # Fetch market regime (SPY trend + VIX)
            regime = self.regime_detector.get_regime()
            self.status.market_regime = regime.label
            self.status.vix = regime.vix
```

- [ ] **Step 4: Pass `regime` to `strategy.generate_signals()`**

Find the `signals = self.strategy.generate_signals(...)` call (~line 298) and add `regime=regime,`:

```python
            signals = self.strategy.generate_signals(
                positions, cash, settings.WATCHLIST, instruments,
                provider_config=self._provider_config,
                earnings_info=earnings_info,
                news_data=news_data,
                macro_events=macro_events,
                outcome_log=self.outcome_log,
                regime=regime,
            )
```

- [ ] **Step 5: Pass `regime` to `risk.validate()`**

Find the `approved, reason = self.risk.validate(...)` call (~line 321) and add `regime=regime,`:

```python
                approved, reason = self.risk.validate(
                    signal, positions, cash, earnings_info, macro_events,
                    regime=regime,
                )
```

- [ ] **Step 6: Run all tests to check nothing regressed**

```bash
.venv/bin/python -m pytest tests/ -v --ignore=tests/test_dashboard_positions_live.py
```

Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/bot/engine.py
git commit -m "feat: fetch market regime per cycle, wire into strategy and risk manager"
```

---

## Task 6: Add regime badge to the dashboard

**Files:**
- Modify: `src/dashboard/templates/dashboard.html`

The badge goes in the header, between the market-badge and the next-open-label. The SSE stream already carries the updated `BotStatus` JSON — no new endpoints needed.

- [ ] **Step 1: Add CSS for the regime badge**

In `dashboard.html`, find the `.market-badge.open` CSS block (around line 57–60) and add the regime badge styles immediately after it:

```css
    .regime-badge {
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 20px;
      font-weight: 700;
    }
    .regime-badge.bull   { background: rgba(63,185,80,.2);  color: var(--green);  }
    .regime-badge.neutral { background: rgba(88,166,255,.2); color: var(--blue);   }
    .regime-badge.bear   { background: rgba(210,153,34,.2); color: var(--yellow); }
    .regime-badge.extreme-fear { background: rgba(248,81,73,.2); color: var(--red); }
```

- [ ] **Step 2: Add the badge element to the header HTML**

Find the header block (around line 273–280):

```html
    <span class="market-badge" id="market-badge">CLOSED</span>
    <span id="next-open-label" style="font-size:11px;color:var(--muted)"></span>
```

Change it to:

```html
    <span class="market-badge" id="market-badge">CLOSED</span>
    <span class="regime-badge" id="regime-badge" style="display:none"></span>
    <span id="next-open-label" style="font-size:11px;color:var(--muted)"></span>
```

- [ ] **Step 3: Add JS update logic in `updateStatus()`**

Find the JS block that updates the market-badge (around line 526–528):

```javascript
      const mb = document.getElementById('market-badge');
      mb.textContent = s.market_open ? 'MARKET OPEN' : 'MARKET CLOSED';
      mb.className = 'market-badge' + (s.market_open ? ' open' : '');
```

Add the regime badge update immediately after:

```javascript
      const rb = document.getElementById('regime-badge');
      if (s.market_regime) {
        const vixStr = s.vix != null ? ` · VIX ${s.vix.toFixed(1)}` : '';
        rb.textContent = s.market_regime.replace('_', ' ') + vixStr;
        rb.className = 'regime-badge ' + s.market_regime.toLowerCase().replace('_', '-');
        rb.style.display = '';
      } else {
        rb.style.display = 'none';
      }
```

- [ ] **Step 4: Run the full test suite one more time**

```bash
.venv/bin/python -m pytest tests/ -v --ignore=tests/test_dashboard_positions_live.py
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dashboard/templates/dashboard.html
git commit -m "feat: add market regime badge to dashboard header"
```

---

## Task 7: Open PR

- [ ] **Step 1: Push branch**

```bash
git push -u origin feat/multi-model-support
```

- [ ] **Step 2: Create PR**

```bash
gh pr create \
  --base claude/trading-bot-automation-kHiwZ \
  --title "feat: market regime detection — block/scale LONGs in bearish conditions" \
  --body "$(cat <<'EOF'
## Summary

- Adds `src/data/market_regime.py`: fetches SPY + ^VIX via yfinance, classifies regime as BULL / NEUTRAL / BEAR / EXTREME_FEAR with a cached 5-min TTL
- `RiskManager.validate()` blocks new LONGs in EXTREME_FEAR (VIX >30) and scales position size to 50% in BEAR, 80% in NEUTRAL
- Claude prompt now includes a `=== MARKET REGIME ===` section with label, VIX, SPY 1d change, and regime-specific guidance
- `BotStatus` gains `market_regime` and `vix` fields surfaced via the existing SSE stream
- Dashboard header shows a colored regime badge (green/blue/yellow/red) with live VIX

Closes #56

## Test plan

- [ ] `pytest tests/test_market_regime.py` — all regime classification + risk integration tests pass
- [ ] `pytest tests/test_strategy.py` — prompt section tests pass
- [ ] `pytest tests/test_risk_manager.py` — no regressions
- [ ] Start bot locally, check dashboard header shows regime badge after first cycle
- [ ] Verify console logs show `Market regime: BEAR (VIX=...)` each cycle

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
