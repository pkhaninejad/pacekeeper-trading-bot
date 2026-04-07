# Market Regime Detection — Design Spec

**Issue:** [#15](https://github.com/pkhaninejad/Claude-trade-bot/issues/15)
**Date:** 2026-04-06
**Status:** Approved

---

## Overview

Add macro-market awareness to the trading bot so it sizes positions and biases signals according to the current S&P 500 trend and VIX fear level. In extreme fear (VIX > 40), Claude is not called at all — the engine only manages exits.

---

## Regime Classification

| Regime | Condition | Position multiplier | Engine behaviour |
|---|---|---|---|
| `BULL` | SPY > 200-day EMA by >2%, VIX < 20 | 1.0 | Normal |
| `NEUTRAL` | SPY within ±2% of 200-day EMA, or VIX 20–30 | 0.75 | Reduced sizing |
| `BEAR` | SPY > 2% below 200-day EMA, VIX > 30 | 0.50 | Reduced sizing, Claude biased SHORT |
| `EXTREME_FEAR` | VIX > 40 (overrides all other conditions) | 0.0 | Skip Claude entirely, exits only |

---

## Data Layer — `src/data/market_regime.py`

New module. Mirrors the `price_feed.py` pattern.

- Fetches SPY (1y period for 200-day EMA) and `^VIX` (1d period for latest close) via `yfinance` in a `ThreadPoolExecutor`
- 1-hour in-process cache (dict + timestamp), same structure as `_cache` in `price_feed.py`
- Falls back to `NEUTRAL` with multiplier 1.0 if yfinance fails; logs a warning
- Single public function: `get_regime() -> RegimeResult`

**`RegimeResult`** added to `src/api/models.py`:

```python
class RegimeResult(BaseModel):
    regime: Literal["BULL", "NEUTRAL", "BEAR", "EXTREME_FEAR"]
    spy_vs_200ema: float        # % above/below 200-day EMA
    vix: float                  # current VIX level
    position_size_multiplier: float   # 1.0, 0.75, 0.50, or 0.0
    description: str
```

---

## Engine Integration — `src/bot/engine.py`

`_cycle()` calls `get_regime()` once, immediately after the market-hours gate, and stores the result on `self._last_regime`.

**EXTREME_FEAR gate** (mirrors market-hours pattern):

```python
if self._last_regime.regime == "EXTREME_FEAR":
    logger.warning("EXTREME_FEAR regime — skipping signals, exits only")
    await self._manage_exits(client, positions)
    return
```

For all other regimes, `RegimeResult` is passed to:
1. `self.risk.validate(..., regime=self._last_regime)` — applies multiplier
2. `self.strategy.generate_signals(..., regime=self._last_regime)` — injects regime section into Claude prompt

`BotStatus` gets one new optional field: `regime: Optional[str] = None`, updated each cycle.

---

## Risk Manager — `src/bot/risk_manager.py`

`validate()` accepts an optional `regime: RegimeResult | None = None` parameter.

In the position-size check, effective max is scaled before the existing auto-scale logic:

```python
effective_max_pct = self.max_position_pct * (regime.position_size_multiplier if regime else 1.0)
max_allowed = cash.total * effective_max_pct
```

No other changes to risk manager logic.

---

## Strategy — `src/bot/strategy.py`

`generate_signals()` and `_build_market_context()` accept an optional `regime: RegimeResult | None = None`.

When provided, `_build_market_context()` appends a `=== MARKET REGIME ===` section to the Claude prompt:

```
=== MARKET REGIME ===
Regime:        BEAR
SPY vs 200EMA: -4.2% (below — bearish trend)
VIX:           32.1 (elevated fear)
Position size: reduced 50% by risk manager
Bias:          Prefer SHORT signals or HOLD
```

---

## Dashboard

- `GET /api/status` already returns `BotStatus` — `regime` field is visible with no new endpoint
- Dashboard HTML header gets a small regime badge (green `BULL`, yellow `NEUTRAL`, red `BEAR`, black `EXTREME_FEAR`)

---

## Files to Create / Modify

| File | Change |
|---|---|
| `src/data/market_regime.py` | **New** — `get_regime()`, 1h cache |
| `src/api/models.py` | Add `RegimeResult` model; add `regime` field to `BotStatus` |
| `src/bot/engine.py` | Call `get_regime()` each cycle, EXTREME_FEAR gate, pass to risk + strategy |
| `src/bot/risk_manager.py` | Accept `regime` param, apply multiplier to position size |
| `src/bot/strategy.py` | Accept `regime` param, inject into Claude prompt |
| `src/dashboard/templates/dashboard.html` | Regime badge in header |
| `tests/test_market_regime.py` | **New** — all 4 boundary conditions (mocked yfinance) |
| `tests/test_risk_manager.py` | Add multiplier scaling tests |

---

## Error Handling

- yfinance failure → log warning, return `NEUTRAL` (multiplier 1.0, no disruption to trading)
- Cache hit always wins; stale data (>1h) triggers a fresh fetch

---

## Definition of Done

- [ ] Regime correctly classified across all 4 states
- [ ] EXTREME_FEAR skips Claude entirely
- [ ] Position sizes scaled by multiplier in all other regimes
- [ ] Regime section visible in Claude prompt
- [ ] Regime badge visible on dashboard header
- [ ] Unit tests for all 4 regime boundary conditions
- [ ] `RiskManager` tests for multiplier scaling
