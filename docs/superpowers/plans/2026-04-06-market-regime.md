# Market Regime Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add macro-market awareness (SPY 200-day EMA + VIX) so the bot scales position sizes by regime and skips Claude entirely in EXTREME_FEAR.

**Architecture:** New `src/data/market_regime.py` module with 1-hour cache; `TradingEngine._cycle()` calls it once per cycle and gates on EXTREME_FEAR before Claude runs; `RegimeResult` flows into `RiskManager.validate()` (multiplier) and `ClaudeStrategy.generate_signals()` (prompt section); dashboard header gets a regime badge.

**Tech Stack:** yfinance (already installed), Pydantic v2, pytest with unittest.mock

---

## File Map

| File | Action |
|---|---|
| `src/api/models.py` | Add `RegimeResult` model; add `regime: Optional[str]` to `BotStatus` |
| `src/data/market_regime.py` | **New** — `get_regime()`, yfinance fetch, 1h cache |
| `src/bot/risk_manager.py` | Add `regime` param to `validate()`, scale `max_allowed` |
| `src/bot/strategy.py` | Add `regime` param to `generate_signals()` and `_build_market_context()` |
| `src/bot/engine.py` | Call `get_regime()` in `_cycle()`, EXTREME_FEAR gate, pass regime through |
| `src/dashboard/templates/dashboard.html` | Regime badge CSS + HTML + JS |
| `tests/test_market_regime.py` | **New** — 4 boundary conditions, cache, fallback |
| `tests/test_risk_manager.py` | Add multiplier scaling tests |

---

## Task 1: Add `RegimeResult` model and `BotStatus.regime` field

**Files:**
- Modify: `src/api/models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py — add to existing file
from src.api.models import RegimeResult, BotStatus

def test_regime_result_bull():
    r = RegimeResult(
        regime="BULL",
        spy_vs_200ema=3.5,
        vix=15.0,
        position_size_multiplier=1.0,
        description="Bull market",
    )
    assert r.regime == "BULL"
    assert r.position_size_multiplier == 1.0

def test_bot_status_has_regime_field():
    s = BotStatus(enabled=True, environment="demo")
    assert s.regime is None  # optional, defaults to None
    s.regime = "BEAR"
    assert s.regime == "BEAR"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_models.py::test_regime_result_bull tests/test_models.py::test_bot_status_has_regime_field -v
```

Expected: `FAILED` — `RegimeResult` not defined, `BotStatus` has no `regime` field.

- [ ] **Step 3: Add `RegimeResult` and update `BotStatus` in `src/api/models.py`**

Add after the `TradeOutcome` class at the bottom of the file:

```python
class RegimeResult(BaseModel):
    regime: Literal["BULL", "NEUTRAL", "BEAR", "EXTREME_FEAR"]
    spy_vs_200ema: float        # % above/below 200-day EMA
    vix: float                  # current VIX level
    position_size_multiplier: float   # 1.0, 0.75, 0.50, or 0.0
    description: str
```

Add `regime` field to `BotStatus`:

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
    regime: Optional[str] = None
```

Also add `RegimeResult` to the imports line at the top — the `Literal` import is already present.

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_models.py::test_regime_result_bull tests/test_models.py::test_bot_status_has_regime_field -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/api/models.py tests/test_models.py
git commit -m "feat: add RegimeResult model and regime field to BotStatus"
```

---

## Task 2: Create `src/data/market_regime.py`

**Files:**
- Create: `src/data/market_regime.py`
- Create: `tests/test_market_regime.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_market_regime.py`:

```python
"""Tests for src/data/market_regime.py."""

from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np
from src.data.market_regime import get_regime, _classify, _CACHE
from src.api.models import RegimeResult


def _make_spy_hist(current_price: float, ema200: float) -> pd.DataFrame:
    """Build a minimal SPY DataFrame where the last close is current_price
    and the 200-day EMA of the series evaluates to approximately ema200."""
    # 210 rows: first 209 at ema200 level, last one at current_price
    closes = [ema200] * 209 + [current_price]
    return pd.DataFrame({"Close": closes})


class TestClassify:
    def test_bull(self):
        # SPY 5% above EMA200, VIX 15 → BULL
        result = _classify(spy_vs_200ema=5.0, vix=15.0)
        assert result.regime == "BULL"
        assert result.position_size_multiplier == 1.0

    def test_neutral_vix_range(self):
        # SPY 5% above EMA200 but VIX 25 → NEUTRAL
        result = _classify(spy_vs_200ema=5.0, vix=25.0)
        assert result.regime == "NEUTRAL"
        assert result.position_size_multiplier == 0.75

    def test_neutral_spy_within_band(self):
        # SPY within ±2% of EMA200, VIX 15 → NEUTRAL
        result = _classify(spy_vs_200ema=1.0, vix=15.0)
        assert result.regime == "NEUTRAL"
        assert result.position_size_multiplier == 0.75

    def test_bear(self):
        # SPY 5% below EMA200, VIX 32 → BEAR
        result = _classify(spy_vs_200ema=-5.0, vix=32.0)
        assert result.regime == "BEAR"
        assert result.position_size_multiplier == 0.50

    def test_extreme_fear(self):
        # VIX > 40 → EXTREME_FEAR regardless of SPY
        result = _classify(spy_vs_200ema=5.0, vix=45.0)
        assert result.regime == "EXTREME_FEAR"
        assert result.position_size_multiplier == 0.0

    def test_extreme_fear_overrides_bull_spy(self):
        result = _classify(spy_vs_200ema=10.0, vix=41.0)
        assert result.regime == "EXTREME_FEAR"


class TestGetRegime:
    def setup_method(self):
        _CACHE.clear()

    def _make_spy_df(self, last_close: float) -> pd.DataFrame:
        """210 rows — enough for a 200-day EMA. All at last_close."""
        return pd.DataFrame({"Close": [last_close] * 210})

    def _make_vix_df(self, vix_close: float) -> pd.DataFrame:
        return pd.DataFrame({"Close": [vix_close]})

    def test_get_regime_returns_regime_result(self):
        spy_df = self._make_spy_df(500.0)
        vix_df = self._make_vix_df(15.0)
        with patch("src.data.market_regime._fetch_spy", return_value=spy_df), \
             patch("src.data.market_regime._fetch_vix", return_value=vix_df):
            result = get_regime()
        assert isinstance(result, RegimeResult)

    def test_get_regime_caches_result(self):
        spy_df = self._make_spy_df(500.0)
        vix_df = self._make_vix_df(15.0)
        with patch("src.data.market_regime._fetch_spy", return_value=spy_df) as mock_spy, \
             patch("src.data.market_regime._fetch_vix", return_value=vix_df):
            get_regime()
            get_regime()
        # Second call should use cache — fetch called only once
        assert mock_spy.call_count == 1

    def test_get_regime_fallback_on_yfinance_failure(self):
        with patch("src.data.market_regime._fetch_spy", side_effect=Exception("network error")), \
             patch("src.data.market_regime._fetch_vix", side_effect=Exception("network error")):
            result = get_regime()
        assert result.regime == "NEUTRAL"
        assert result.position_size_multiplier == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_market_regime.py -v
```

Expected: `ERROR` — module `src.data.market_regime` not found.

- [ ] **Step 3: Create `src/data/market_regime.py`**

```python
"""
Market regime detection using SPY 200-day EMA and VIX.

Classifies current market conditions into BULL / NEUTRAL / BEAR / EXTREME_FEAR
and returns a position_size_multiplier the risk manager applies to max position size.

Results are cached for REGIME_CACHE_TTL seconds (1 hour) — no need to recalculate
every 5-minute cycle.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from src.api.models import RegimeResult

logger = logging.getLogger(__name__)

REGIME_CACHE_TTL = 3600  # 1 hour

_CACHE: dict = {}
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="regime")


def _fetch_spy() -> "pd.DataFrame":
    import yfinance as yf
    t = yf.Ticker("SPY")
    return t.history(period="1y", auto_adjust=True)


def _fetch_vix() -> "pd.DataFrame":
    import yfinance as yf
    t = yf.Ticker("^VIX")
    return t.history(period="5d", auto_adjust=True)


def _classify(spy_vs_200ema: float, vix: float) -> RegimeResult:
    """Pure classification logic — no I/O. Testable in isolation."""
    if vix > 40:
        return RegimeResult(
            regime="EXTREME_FEAR",
            spy_vs_200ema=spy_vs_200ema,
            vix=vix,
            position_size_multiplier=0.0,
            description=f"VIX={vix:.1f} — extreme fear, all new positions blocked",
        )
    if spy_vs_200ema > 2.0 and vix < 20:
        return RegimeResult(
            regime="BULL",
            spy_vs_200ema=spy_vs_200ema,
            vix=vix,
            position_size_multiplier=1.0,
            description=f"SPY {spy_vs_200ema:+.1f}% above 200EMA, VIX={vix:.1f} — bull market",
        )
    if spy_vs_200ema < -2.0 and vix > 30:
        return RegimeResult(
            regime="BEAR",
            spy_vs_200ema=spy_vs_200ema,
            vix=vix,
            position_size_multiplier=0.50,
            description=f"SPY {spy_vs_200ema:+.1f}% below 200EMA, VIX={vix:.1f} — bear market",
        )
    return RegimeResult(
        regime="NEUTRAL",
        spy_vs_200ema=spy_vs_200ema,
        vix=vix,
        position_size_multiplier=0.75,
        description=f"SPY {spy_vs_200ema:+.1f}% vs 200EMA, VIX={vix:.1f} — neutral",
    )


def _neutral_fallback() -> RegimeResult:
    return RegimeResult(
        regime="NEUTRAL",
        spy_vs_200ema=0.0,
        vix=0.0,
        position_size_multiplier=1.0,
        description="Regime data unavailable — defaulting to NEUTRAL (full sizing)",
    )


def _is_fresh() -> bool:
    if "fetched_at" not in _CACHE:
        return False
    return (datetime.utcnow() - _CACHE["fetched_at"]).total_seconds() < REGIME_CACHE_TTL


def get_regime() -> RegimeResult:
    """
    Return current market regime. Cached for 1 hour.
    Falls back to NEUTRAL (multiplier 1.0) on any yfinance failure.
    """
    if _is_fresh():
        return _CACHE["result"]

    try:
        import yfinance  # noqa — check availability before spinning threads
    except ImportError:
        logger.warning("yfinance not installed — regime detection disabled, using NEUTRAL")
        return _neutral_fallback()

    try:
        futures = {
            _executor.submit(_fetch_spy): "spy",
            _executor.submit(_fetch_vix): "vix",
        }
        data = {}
        for future in as_completed(futures, timeout=15):
            key = futures[future]
            data[key] = future.result()

        spy_hist = data.get("spy")
        vix_hist = data.get("vix")

        if spy_hist is None or spy_hist.empty or len(spy_hist) < 200:
            logger.warning("Regime: insufficient SPY history — using NEUTRAL")
            return _neutral_fallback()
        if vix_hist is None or vix_hist.empty:
            logger.warning("Regime: VIX data unavailable — using NEUTRAL")
            return _neutral_fallback()

        spy_close = spy_hist["Close"].dropna()
        ema200 = spy_close.ewm(span=200, adjust=False).mean().iloc[-1]
        spy_current = spy_close.iloc[-1]
        spy_vs_200ema = (spy_current - ema200) / ema200 * 100

        vix = float(vix_hist["Close"].dropna().iloc[-1])

        result = _classify(spy_vs_200ema=round(spy_vs_200ema, 2), vix=round(vix, 2))
        _CACHE["result"] = result
        _CACHE["fetched_at"] = datetime.utcnow()
        logger.info("Market regime: %s (SPY %+.1f%% vs 200EMA, VIX=%.1f)", result.regime, spy_vs_200ema, vix)
        return result

    except Exception as e:
        logger.warning("Regime detection failed: %s — using NEUTRAL", e)
        return _neutral_fallback()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_market_regime.py -v
```

Expected: all `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/data/market_regime.py tests/test_market_regime.py
git commit -m "feat: add market regime detection module with 1h cache"
```

---

## Task 3: Update `RiskManager.validate()` to apply regime multiplier

**Files:**
- Modify: `src/bot/risk_manager.py`
- Modify: `tests/test_risk_manager.py`

- [ ] **Step 1: Write the failing tests**

Add to the bottom of `tests/test_risk_manager.py`:

```python
# ---------------------------------------------------------------------------
# RiskManager regime multiplier
# ---------------------------------------------------------------------------

from src.api.models import RegimeResult


def make_regime(regime: str, multiplier: float) -> RegimeResult:
    return RegimeResult(
        regime=regime,
        spy_vs_200ema=0.0,
        vix=20.0,
        position_size_multiplier=multiplier,
        description="test",
    )


class TestRegimeMultiplier:
    def setup_method(self):
        self.rm = RiskManager()

    def test_bear_regime_reduces_max_allowed(self):
        # max_position_pct=0.05, total=20_000 → normal max=1_000
        # BEAR multiplier=0.5 → max=500
        # Signal asks for qty=8 @ price=100 = 800 → should be scaled down to 5.0
        signal = make_signal(suggested_quantity=8.0, suggested_price=100.0)
        cash = make_cash(free=1_000.0, total=20_000.0)
        regime = make_regime("BEAR", 0.50)
        approved, _ = self.rm.validate(signal, [], cash, regime=regime)
        assert approved is True
        expected_qty = (20_000.0 * 0.05 * 0.50) / 100.0  # 500 / 100 = 5.0
        assert signal.suggested_quantity == pytest.approx(expected_qty)

    def test_neutral_regime_reduces_max_allowed(self):
        # NEUTRAL multiplier=0.75 → max=750
        signal = make_signal(suggested_quantity=8.0, suggested_price=100.0)
        cash = make_cash(free=1_000.0, total=20_000.0)
        regime = make_regime("NEUTRAL", 0.75)
        approved, _ = self.rm.validate(signal, [], cash, regime=regime)
        assert approved is True
        expected_qty = (20_000.0 * 0.05 * 0.75) / 100.0  # 750 / 100 = 7.5
        assert signal.suggested_quantity == pytest.approx(expected_qty)

    def test_bull_regime_no_reduction(self):
        # BULL multiplier=1.0 → no change from default
        signal = make_signal(suggested_quantity=8.0, suggested_price=100.0)
        cash = make_cash(free=1_000.0, total=20_000.0)
        regime = make_regime("BULL", 1.0)
        approved, _ = self.rm.validate(signal, [], cash, regime=regime)
        assert approved is True
        expected_qty = (20_000.0 * 0.05 * 1.0) / 100.0  # 1000 / 100 = 10.0
        # signal was 8, which is within max, so NOT scaled down
        assert signal.suggested_quantity == pytest.approx(8.0)

    def test_no_regime_behaves_as_before(self):
        # No regime arg → multiplier defaults to 1.0, existing behaviour unchanged
        signal = make_signal(suggested_quantity=8.0, suggested_price=100.0)
        cash = make_cash(free=1_000.0, total=20_000.0)
        approved, _ = self.rm.validate(signal, [], cash)
        assert approved is True
        assert signal.suggested_quantity == pytest.approx(8.0)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_risk_manager.py::TestRegimeMultiplier -v
```

Expected: `FAILED` — `validate()` does not accept `regime` kwarg.

- [ ] **Step 3: Update `src/bot/risk_manager.py`**

Change the `validate` signature and import:

```python
from src.api.models import TradeSignal, Position, CashInfo, RegimeResult
```

Change the `validate` method signature:

```python
def validate(
    self,
    signal: TradeSignal,
    positions: list[Position],
    cash: CashInfo,
    earnings_info: dict[str, "EarningsInfo"] | None = None,
    regime: "RegimeResult | None" = None,
) -> tuple[bool, str]:
```

Replace the position-size limit block (lines 66–77 in the original):

```python
        # Position size limit (regime multiplier applied here)
        if signal.suggested_quantity and signal.suggested_price:
            trade_value = abs(signal.suggested_quantity) * signal.suggested_price
            multiplier = regime.position_size_multiplier if regime else 1.0
            max_allowed = cash.total * self.max_position_pct * multiplier
            if trade_value > max_allowed:
                # Auto-scale down
                signal.suggested_quantity = (max_allowed / signal.suggested_price) * (
                    1 if signal.suggested_quantity > 0 else -1
                )
                logger.info(
                    "Scaled position size for %s to %.4f (max %.2f, regime=%s)",
                    signal.ticker, signal.suggested_quantity, max_allowed,
                    regime.regime if regime else "none",
                )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_risk_manager.py -v
```

Expected: all `PASSED` (new tests + existing tests unchanged)

- [ ] **Step 5: Commit**

```bash
git add src/bot/risk_manager.py tests/test_risk_manager.py
git commit -m "feat: apply regime position_size_multiplier in RiskManager"
```

---

## Task 4: Inject regime into Claude prompt in `strategy.py`

**Files:**
- Modify: `src/bot/strategy.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_strategy.py` (or create it if missing):

```python
from src.api.models import RegimeResult
from src.bot.strategy import _build_market_context
from src.api.models import CashInfo

def make_cash():
    return CashInfo(free=10000, total=20000, ppl=0, result=0, invested=10000, pieCash=0)

def make_regime(regime_name: str) -> RegimeResult:
    labels = {
        "BULL": (1.0, "bull market"),
        "NEUTRAL": (0.75, "neutral"),
        "BEAR": (0.50, "bear market"),
    }
    mult, desc = labels[regime_name]
    return RegimeResult(
        regime=regime_name,
        spy_vs_200ema=3.0 if regime_name == "BULL" else -3.0,
        vix=15.0 if regime_name == "BULL" else 32.0,
        position_size_multiplier=mult,
        description=desc,
    )

def test_regime_section_included_in_prompt():
    regime = make_regime("BEAR")
    prompt = _build_market_context([], make_cash(), ["AAPL"], [], regime=regime)
    assert "MARKET REGIME" in prompt
    assert "BEAR" in prompt

def test_no_regime_prompt_unchanged():
    prompt = _build_market_context([], make_cash(), ["AAPL"], [])
    assert "MARKET REGIME" not in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_strategy.py::test_regime_section_included_in_prompt tests/test_strategy.py::test_no_regime_prompt_unchanged -v
```

Expected: `FAILED` — `_build_market_context` does not accept `regime` kwarg.

- [ ] **Step 3: Update `src/bot/strategy.py`**

Add `RegimeResult` to the models import:

```python
from src.api.models import Position, CashInfo, TradeSignal, Instrument, RegimeResult
```

Update `_build_market_context` signature (add `regime` param at the end):

```python
def _build_market_context(
    positions: list[Position],
    cash: CashInfo,
    watchlist: list[str],
    instruments: list[Instrument],
    price_data: dict | None = None,
    earnings_info: dict[str, "EarningsInfo"] | None = None,
    news_data: dict[str, list["NewsItem"]] | None = None,
    outcome_log: list | None = None,
    regime: "RegimeResult | None" = None,
) -> str:
```

Add regime section builder just before the `context = f"""...` line:

```python
    regime_section = ""
    if regime:
        spy_label = "above" if regime.spy_vs_200ema >= 0 else "below"
        pct_label = f"{abs(regime.spy_vs_200ema):.1f}% {spy_label} 200EMA"
        size_label = f"reduced {int((1 - regime.position_size_multiplier) * 100)}% by risk manager" \
            if regime.position_size_multiplier < 1.0 else "normal (100%)"
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
```

Insert `{regime_section}` into the context f-string, after `{perf_section}` and before `=== WATCHLIST ===`:

```python
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
{earnings_section}{news_section}{perf_section}{regime_section}
=== WATCHLIST ===
{json.dumps({t: instrument_info.get(t, t) for t in watchlist}, indent=2)}

=== TASK ===
Analyse the portfolio and market conditions using the price feed data.
Generate trading signals for up to 5 tickers.
Focus on tickers where there is a clear directional view.
Return ONLY a JSON array of TradeSignal objects.
"""
```

Update `generate_signals` signature to accept and pass `regime`:

```python
    def generate_signals(
        self,
        positions: list[Position],
        cash: CashInfo,
        watchlist: list[str],
        instruments: list[Instrument],
        earnings_info: dict[str, "EarningsInfo"] | None = None,
        news_data: dict[str, list["NewsItem"]] | None = None,
        outcome_log: list | None = None,
        regime: "RegimeResult | None" = None,
    ) -> list[TradeSignal]:
        """Call Claude and parse trade signals."""
        price_data = get_price_summary(watchlist)
        user_prompt = _build_market_context(
            positions, cash, watchlist, instruments, price_data,
            earnings_info, news_data, outcome_log, regime,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_strategy.py -v
```

Expected: all `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/bot/strategy.py tests/test_strategy.py
git commit -m "feat: inject market regime section into Claude prompt"
```

---

## Task 5: Integrate regime into `TradingEngine._cycle()`

**Files:**
- Modify: `src/bot/engine.py`

No new tests for this task — engine integration is covered by the existing end-to-end test structure. The unit-testable pieces (regime detection, risk multiplier, prompt injection) are already tested.

- [ ] **Step 1: Add import and `_last_regime` to `__init__`**

Add to the imports at the top of `src/bot/engine.py`:

```python
from src.data.market_regime import get_regime
from src.api.models import (
    MarketOrderRequest, LimitOrderRequest, StopOrderRequest,
    TradeSignal, BotStatus, Position, TradeOutcome, RegimeResult,
)
```

Add `_last_regime` attribute to `TradingEngine.__init__` (after `self._session_date`):

```python
        self._last_regime: RegimeResult | None = None
```

- [ ] **Step 2: Add regime fetch and EXTREME_FEAR gate to `_cycle()`**

In `_cycle()`, immediately after the market-hours gate block (after the `if not open_now:` block, before `logger.info("=== Trading cycle started ===")`), add:

```python
        # Fetch market regime (cached 1h) — EXTREME_FEAR blocks new signals
        self._last_regime = get_regime()
        self.status.regime = self._last_regime.regime
        if self._last_regime.regime == "EXTREME_FEAR":
            logger.warning(
                "EXTREME_FEAR regime (VIX=%.1f) — skipping signals, managing exits only",
                self._last_regime.vix,
            )
            async with Trading212Client() as client:
                positions = await client.get_positions()
                await self._manage_exits(client, positions)
            return
```

- [ ] **Step 3: Pass regime to `risk.validate()` and `strategy.generate_signals()`**

In `_cycle()`, update the `generate_signals` call:

```python
            signals = self.strategy.generate_signals(
                positions, cash, settings.WATCHLIST, instruments, earnings_info, news_data,
                outcome_log=self.outcome_log,
                regime=self._last_regime,
            )
```

Update the `risk.validate` call:

```python
                approved, reason = self.risk.validate(
                    signal, positions, cash, earnings_info, regime=self._last_regime
                )
```

- [ ] **Step 4: Run full test suite to confirm no regressions**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all existing tests `PASSED`, no new failures.

- [ ] **Step 5: Commit**

```bash
git add src/bot/engine.py
git commit -m "feat: integrate market regime into trading cycle with EXTREME_FEAR gate"
```

---

## Task 6: Add regime badge to dashboard

**Files:**
- Modify: `src/dashboard/templates/dashboard.html`

- [ ] **Step 1: Add CSS for regime badge**

In the `<style>` block, after the `.market-badge.open` rule (around line 60), add:

```css
    .regime-badge {
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 20px;
      font-weight: 700;
      background: rgba(63,185,80,.2);
      color: var(--green);
    }
    .regime-badge.neutral {
      background: rgba(210,153,34,.2);
      color: var(--yellow);
    }
    .regime-badge.bear {
      background: rgba(248,81,73,.2);
      color: var(--red);
    }
    .regime-badge.extreme-fear {
      background: rgba(188,140,255,.2);
      color: var(--purple);
    }
```

- [ ] **Step 2: Add regime badge HTML element**

In the `<header>` section, after the `<span id="market-badge">` line (line 224), add:

```html
    <span class="regime-badge" id="regime-badge" style="display:none">BULL</span>
```

- [ ] **Step 3: Add regime badge update in JavaScript**

In the `updateStatus` function, after the market-badge update block (after line 448), add:

```javascript
      const rb = document.getElementById('regime-badge');
      if (s.regime) {
        rb.textContent = s.regime.replace('_', ' ');
        const classMap = {
          'BULL': '',
          'NEUTRAL': 'neutral',
          'BEAR': 'bear',
          'EXTREME_FEAR': 'extreme-fear',
        };
        rb.className = 'regime-badge ' + (classMap[s.regime] || '');
        rb.style.display = '';
      } else {
        rb.style.display = 'none';
      }
```

- [ ] **Step 4: Run existing tests to confirm no Python regressions**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all `PASSED` (HTML change has no Python tests)

- [ ] **Step 5: Commit**

```bash
git add src/dashboard/templates/dashboard.html
git commit -m "feat: add market regime badge to dashboard header"
```

---

## Task 7: Open PR

- [ ] **Step 1: Push branch and open PR**

```bash
git checkout -b feat/market-regime
git push -u origin feat/market-regime
gh pr create \
  --title "feat: market regime detection (SPY 200EMA + VIX)" \
  --body "$(cat <<'EOF'
## Summary
- Adds `src/data/market_regime.py` — classifies BULL / NEUTRAL / BEAR / EXTREME_FEAR using SPY 200-day EMA and VIX, cached 1 hour
- EXTREME_FEAR (VIX > 40) skips Claude entirely; engine only runs stop-loss/take-profit exits
- Position sizes scaled by regime multiplier (1.0 / 0.75 / 0.50) in RiskManager
- Regime section injected into Claude prompt for directional bias
- Regime badge displayed in dashboard header

Closes #15

## Test plan
- [ ] `pytest tests/test_market_regime.py` — all 4 boundary conditions, cache, fallback
- [ ] `pytest tests/test_risk_manager.py` — multiplier scaling tests
- [ ] `pytest tests/test_strategy.py` — regime prompt injection
- [ ] `pytest tests/` — full suite, no regressions

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review Checklist

- [x] `RegimeResult` model defined before use in Task 1 — all later tasks reference it correctly
- [x] `_classify(spy_vs_200ema, vix)` signature matches usage in `get_regime()` and tests
- [x] `validate(..., regime=...)` kwarg matches the call-site in engine Task 5
- [x] `generate_signals(..., regime=...)` and `_build_market_context(..., regime=...)` signatures consistent
- [x] `_CACHE` is the module-level dict imported in tests for `setup_method` clearing
- [x] EXTREME_FEAR gate in engine opens its own `Trading212Client` context (positions needed for `_manage_exits`)
- [x] Dashboard JS `classMap` covers all 4 regime values
- [x] All 4 spec boundary conditions covered by `TestClassify`
