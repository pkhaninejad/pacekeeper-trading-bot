# Market Regime Detection — Design Spec

**Date:** 2026-04-07  
**Issue:** [#56](https://github.com/pkhaninejad/Claude-trade-bot/issues/56)  
**Branch:** `feat/market-regime`

## Problem

On broad market selloff days the engine generates LONG signals because:
1. No market regime awareness — the bot treats every day as neutral.
2. SHORT signals are hard-blocked by `RiskManager` (Invest/ISA account can't short), leaving regime protection as the only bearish mechanism.

## Goal

Detect market regime from SPY trend + VIX each cycle and use it to:
- Warn Claude about the macro environment (prompt injection).
- Scale position sizes down in BEAR / block new LONGs in EXTREME_FEAR.
- Surface the current regime + VIX on the dashboard status panel.

---

## Architecture

### New module: `src/data/market_regime.py`

Follows the same pattern as `macro_calendar.py` and `price_feed.py`.

```python
@dataclass
class MarketRegime:
    label: str          # "BULL" | "NEUTRAL" | "BEAR" | "EXTREME_FEAR"
    vix: float          # latest VIX close
    spy_change_pct: float   # SPY 1-day % change
    risk_multiplier: float  # applied to max_position_pct in RiskManager
```

`RegimeDetector.get_regime()`:
- Fetches `SPY` and `^VIX` via yfinance (already a project dependency).
- Computes SPY SMA10, SMA30 from 30-day history.
- 5-minute in-process cache (same TTL as `price_feed.py`).
- Fails silently: returns `MarketRegime(label="NEUTRAL", vix=0.0, spy_change_pct=0.0, risk_multiplier=0.8)` if yfinance unavailable or fetch fails.

**Classification (checked in order):**

| Condition | Regime | `risk_multiplier` |
|---|---|---|
| VIX > 30 | `EXTREME_FEAR` | `0.0` (blocks new longs) |
| VIX > 25 **or** SPY below SMA10 & SMA30 | `BEAR` | `0.5` |
| VIX > 20 **or** SPY below one SMA | `NEUTRAL` | `0.8` |
| VIX ≤ 20 **and** SPY above both SMAs | `BULL` | `1.0` |

---

### `src/api/models.py`

Add two optional fields to `BotStatus`:
```python
market_regime: str | None = None
vix: float | None = None
```

---

### `src/bot/engine.py`

- `__init__`: add `self.regime_detector = RegimeDetector()`.
- `_cycle()`: call `regime = self.regime_detector.get_regime()` before signal generation. Set `self.status.market_regime = regime.label` and `self.status.vix = regime.vix`. Pass `regime` to `strategy.generate_signals()` and `risk.validate()`.

---

### `src/bot/strategy.py`

`_build_market_context()` gains a `regime: MarketRegime | None` parameter. When present, adds a new section to the Claude prompt (between the macro section and the watchlist):

```
=== MARKET REGIME ===
  Label: BEAR  |  VIX: 28.4  |  SPY 1d: -3.2%
  ⚠️  Bearish regime — raise the confidence bar for new LONGs, favour CLOSE signals on existing positions.
```

Regime-specific guidance text:
- BULL: "Bullish regime — normal signal generation."
- NEUTRAL: "Neutral regime — apply standard confidence thresholds."
- BEAR: "Bearish regime — raise the confidence bar for new LONGs, favour CLOSE signals on existing positions."
- EXTREME_FEAR: "Extreme fear (VIX >30) — new LONG positions are blocked by the risk manager. Focus only on CLOSE signals."

`AIStrategy.generate_signals()` gains a `regime` parameter and passes it through to `_build_market_context()`.

---

### `src/bot/risk_manager.py`

`validate()` gains a `regime: MarketRegime | None` parameter. Applied only to new LONG positions (not to CLOSE signals):

- `EXTREME_FEAR` → `return False, "EXTREME_FEAR regime (VIX >30): new LONG positions blocked"`
- `BEAR` → `effective_max_pct = self.max_position_pct * 0.5`
- `NEUTRAL` → `effective_max_pct = self.max_position_pct * 0.8`
- `BULL` / `None` → `effective_max_pct = self.max_position_pct` (unchanged)

The scaled `effective_max_pct` replaces `self.max_position_pct` in the position-size limit check and `compute_quantity` is unchanged (size scaling happens inline in `validate()`).

---

### Dashboard (`src/dashboard/static/`)

The existing SSE stream carries `BotStatus` JSON to the frontend. The regime badge is added to the status panel (same row as bot enabled / market open):

- Badge text: `BULL`, `NEUTRAL`, `BEAR`, or `EXTREME_FEAR · VIX 28.4`
- Colors: green (BULL), yellow (NEUTRAL), orange (BEAR), red (EXTREME_FEAR)
- Hidden when `market_regime` is `null` (first cycle not yet completed).

No new API endpoints or polling needed.

---

### Tests: `tests/test_market_regime.py`

Unit tests mock yfinance output for all four regime boundaries:
- VIX=35 → EXTREME_FEAR, multiplier=0.0
- VIX=27, SPY below both SMAs → BEAR, multiplier=0.5
- VIX=22 → NEUTRAL, multiplier=0.8
- VIX=18, SPY above both SMAs → BULL, multiplier=1.0
- yfinance unavailable → NEUTRAL fallback, no exception raised

Also unit-test `RiskManager.validate()` with each regime:
- EXTREME_FEAR blocks new LONG
- BEAR scales position size to 50%
- NEUTRAL scales to 80%
- BULL unchanged
- CLOSE signals pass through regardless of regime

---

## File Change Summary

| File | Change |
|---|---|
| `src/data/market_regime.py` | **New** — `MarketRegime` dataclass + `RegimeDetector` |
| `src/api/models.py` | Add `market_regime`, `vix` to `BotStatus` |
| `src/bot/engine.py` | Fetch regime per cycle, set status fields, pass to strategy + risk |
| `src/bot/strategy.py` | Add `regime` param to `generate_signals()` + `_build_market_context()` |
| `src/bot/risk_manager.py` | Add `regime` param to `validate()`, apply multiplier / block |
| `src/dashboard/static/` | Add regime badge to status panel |
| `tests/test_market_regime.py` | **New** — unit tests for regime classification + risk integration |

## Out of Scope

- CFD / short support (tracked separately in issue #48).
- Persisting regime history across restarts (in-memory only, like all other state).
- Configurable VIX thresholds in `.env` (hardcoded; can be added later if needed).
