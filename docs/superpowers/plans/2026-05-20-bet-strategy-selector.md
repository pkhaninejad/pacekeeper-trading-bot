# Bet Strategy Selector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users pick one of three bet-sizing/side-selection strategies — Contrarian, Kelly, or Min R:R — from the dashboard, so the bot's risk/reward structure is transparent and configurable.

**Architecture:** A new `BET_STRATEGY` field on `PredictionBotSettings` controls behavior in two places: `scanner.py` (which side to buy and what to filter) and `paper_trader.py` (how much to allocate). The dashboard gains a radio-button selector with plain-English descriptions and the existing Save Settings button persists the choice.

**Tech Stack:** Python 3.14, FastAPI, Pydantic v2, aiosqlite, Jinja2, vanilla JS (no build step)

---

## File Map

| File | Change |
|---|---|
| `prediction_bot/src/config/settings.py` | Add `BET_STRATEGY` and `MIN_RR_RATIO` fields |
| `prediction_bot/src/bot/scanner.py` | Strategy-aware side selection + Min R:R filter |
| `prediction_bot/src/bot/paper_trader.py` | Kelly-based position sizing |
| `prediction_bot/src/dashboard/app.py` | Expose new fields in `ScannerSettingsUpdate` and settings routes |
| `prediction_bot/src/dashboard/templates/dashboard.html` | Strategy selector UI |
| `prediction_bot/tests/test_scanner.py` | Tests for contrarian and min_rr scanner behavior |
| `prediction_bot/tests/test_paper_trader.py` | Tests for Kelly sizing |

---

## Task 1: Add strategy fields to settings

**Files:**
- Modify: `prediction_bot/src/config/settings.py`

- [ ] **Step 1: Add the two new fields**

Open `prediction_bot/src/config/settings.py` and replace the class body so it reads:

```python
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class PredictionBotSettings(BaseSettings):
    POLYMARKET_ENABLED: bool = True
    KALSHI_ENABLED: bool = False
    KALSHI_API_KEY: str = ""
    KALSHI_API_SECRET: str = ""
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-sonnet-4-6"
    SCAN_INTERVAL_SECONDS: int = 120
    EXPIRY_WINDOW_HOURS: int = 168
    HIGH_PROB_MIN: float = 0.80
    HIGH_PROB_MAX: float = 0.97
    MIN_LIQUIDITY: float = 1000.0
    MIN_EDGE_PCT: float = 0.02
    ENABLED_CATEGORIES: list[str] = ["crypto", "sports", "politics"]
    VIRTUAL_BANKROLL: float = 1000.0
    MAX_POSITION_PCT: float = 0.10
    MAX_OPEN_POSITIONS: int = 20
    PM_DB_PATH: str = "prediction_bot/data/paper_trades.db"
    PM_DASHBOARD_PORT: int = 4001
    BET_STRATEGY: Literal["contrarian", "kelly", "min_rr"] = "contrarian"
    MIN_RR_RATIO: float = 0.25

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


pm_settings = PredictionBotSettings()
```

- [ ] **Step 2: Verify no import errors**

```bash
cd /Users/pkhaninejad/Desktop/apps/Claude-trade-bot && .venv/bin/python -c "from prediction_bot.src.config.settings import PredictionBotSettings; s = PredictionBotSettings(); print(s.BET_STRATEGY, s.MIN_RR_RATIO)"
```

Expected output: `contrarian 0.25`

- [ ] **Step 3: Commit**

```bash
git add prediction_bot/src/config/settings.py
git commit -m "feat(prediction-bot): add BET_STRATEGY and MIN_RR_RATIO settings"
```

---

## Task 2: Update scanner for strategy-aware side selection

**Files:**
- Modify: `prediction_bot/src/bot/scanner.py`
- Test: `prediction_bot/tests/test_scanner.py`

### Background — what each strategy means in the scanner

| Strategy | Which side to buy | Filter applied to |
|---|---|---|
| `contrarian` | LOW-probability side (e.g. NO when YES=0.92) | The HIGH-probability side price must be in `[HIGH_PROB_MIN, HIGH_PROB_MAX]` |
| `kelly` | HIGH-probability side (current behaviour) | The high-prob side price in `[HIGH_PROB_MIN, HIGH_PROB_MAX]` |
| `min_rr` | HIGH-probability side (current behaviour) | Same as kelly, plus `(1 − best_price) / best_price ≥ MIN_RR_RATIO` |

- [ ] **Step 1: Write failing tests**

Append to `prediction_bot/tests/test_scanner.py`:

```python
@pytest.mark.asyncio
async def test_contrarian_picks_low_prob_side():
    """Contrarian strategy buys NO when YES is the high-prob side."""
    from prediction_bot.src.bot.scanner import scan_markets

    s = PredictionBotSettings(
        HIGH_PROB_MIN=0.80, HIGH_PROB_MAX=0.97,
        MIN_LIQUIDITY=0, EXPIRY_WINDOW_HOURS=48,
        ENABLED_CATEGORIES=["crypto"],
        BET_STRATEGY="contrarian",
    )
    m = _market(yes_price=0.92)  # YES=0.92 is high-prob; contrarian buys NO@0.08
    poly_mock = AsyncMock()
    poly_mock.get_near_expiry_markets = AsyncMock(return_value=[m])

    result = await scan_markets([poly_mock], s)
    assert len(result) == 1
    assert result[0].best_side == "NO"
    assert abs(result[0].market_price - 0.08) < 0.001


@pytest.mark.asyncio
async def test_contrarian_excludes_when_high_prob_out_of_range():
    """Contrarian: market excluded if the high-prob side is outside [MIN, MAX]."""
    from prediction_bot.src.bot.scanner import scan_markets

    s = PredictionBotSettings(
        HIGH_PROB_MIN=0.80, HIGH_PROB_MAX=0.97,
        MIN_LIQUIDITY=0, EXPIRY_WINDOW_HOURS=48,
        ENABLED_CATEGORIES=["crypto"],
        BET_STRATEGY="contrarian",
    )
    m = _market(yes_price=0.60)  # 60% YES is below HIGH_PROB_MIN
    poly_mock = AsyncMock()
    poly_mock.get_near_expiry_markets = AsyncMock(return_value=[m])

    result = await scan_markets([poly_mock], s)
    assert len(result) == 0


@pytest.mark.asyncio
async def test_min_rr_excludes_poor_ratio():
    """Min R:R: market excluded when (1-price)/price < MIN_RR_RATIO."""
    from prediction_bot.src.bot.scanner import scan_markets

    s = PredictionBotSettings(
        HIGH_PROB_MIN=0.80, HIGH_PROB_MAX=0.97,
        MIN_LIQUIDITY=0, EXPIRY_WINDOW_HOURS=48,
        ENABLED_CATEGORIES=["crypto"],
        BET_STRATEGY="min_rr",
        MIN_RR_RATIO=0.25,
    )
    # YES=0.94 → (1-0.94)/0.94 = 0.064, below 0.25
    poor = _market(id="poor", yes_price=0.94)
    # YES=0.80 → (1-0.80)/0.80 = 0.25, meets threshold exactly
    ok = _market(id="ok", yes_price=0.80)
    poly_mock = AsyncMock()
    poly_mock.get_near_expiry_markets = AsyncMock(return_value=[poor, ok])

    result = await scan_markets([poly_mock], s)
    ids = [c.market.id for c in result]
    assert "ok" in ids
    assert "poor" not in ids


@pytest.mark.asyncio
async def test_kelly_strategy_picks_high_prob_side():
    """Kelly strategy picks the same high-prob side as the original logic."""
    from prediction_bot.src.bot.scanner import scan_markets

    s = PredictionBotSettings(
        HIGH_PROB_MIN=0.80, HIGH_PROB_MAX=0.97,
        MIN_LIQUIDITY=0, EXPIRY_WINDOW_HOURS=48,
        ENABLED_CATEGORIES=["crypto"],
        BET_STRATEGY="kelly",
    )
    m = _market(yes_price=0.90)
    poly_mock = AsyncMock()
    poly_mock.get_near_expiry_markets = AsyncMock(return_value=[m])

    result = await scan_markets([poly_mock], s)
    assert len(result) == 1
    assert result[0].best_side == "YES"
    assert abs(result[0].market_price - 0.90) < 0.001
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/pkhaninejad/Desktop/apps/Claude-trade-bot && .venv/bin/python -m pytest prediction_bot/tests/test_scanner.py::test_contrarian_picks_low_prob_side prediction_bot/tests/test_scanner.py::test_contrarian_excludes_when_high_prob_out_of_range prediction_bot/tests/test_scanner.py::test_min_rr_excludes_poor_ratio prediction_bot/tests/test_scanner.py::test_kelly_strategy_picks_high_prob_side -v
```

Expected: 4 FAILs (scanner doesn't know about strategies yet).

- [ ] **Step 3: Rewrite scanner.py**

Replace `prediction_bot/src/bot/scanner.py` entirely:

```python
"""Market scanner — filters and ranks MarketCandidate list from all platforms."""
from __future__ import annotations

import logging
import math

from prediction_bot.src.api.models import MarketCandidate, PredictionMarket
from prediction_bot.src.config.settings import PredictionBotSettings

logger = logging.getLogger(__name__)


async def scan_markets(
    clients: list,
    settings: PredictionBotSettings,
) -> list[MarketCandidate]:
    """Scan all platform clients and return ranked MarketCandidate list (best first, max 50)."""
    raw: list[PredictionMarket] = []

    for client in clients:
        name = getattr(client, "platform", type(client).__name__)
        try:
            markets = await client.get_near_expiry_markets(
                hours=settings.EXPIRY_WINDOW_HOURS,
                min_liquidity=settings.MIN_LIQUIDITY,
            )
            raw.extend(markets)
            logger.info("%s: %d near-expiry markets fetched", name, len(markets))
        except Exception as e:
            logger.warning("%s scan error: %s", name, e)

    candidates: list[MarketCandidate] = []
    for market in raw:
        if market.category not in settings.ENABLED_CATEGORIES:
            continue
        if market.liquidity < settings.MIN_LIQUIDITY:
            continue

        candidate = _apply_strategy(market, settings)
        if candidate is not None:
            candidates.append(candidate)

    def _score(c: MarketCandidate) -> float:
        return (1.0 - c.market_price) * math.log(c.market.liquidity + 1)

    candidates.sort(key=_score, reverse=True)
    return candidates[:50]


def _apply_strategy(
    market: PredictionMarket,
    settings: PredictionBotSettings,
) -> MarketCandidate | None:
    """Return a MarketCandidate for this market under the active strategy, or None to skip."""
    high_side = "YES" if market.yes_price >= market.no_price else "NO"
    high_price = market.yes_price if high_side == "YES" else market.no_price

    if not (settings.HIGH_PROB_MIN <= high_price <= settings.HIGH_PROB_MAX):
        return None

    if settings.BET_STRATEGY == "contrarian":
        best_side = "NO" if high_side == "YES" else "YES"
        best_price = market.no_price if best_side == "NO" else market.yes_price
    else:
        best_side = high_side
        best_price = high_price
        if settings.BET_STRATEGY == "min_rr":
            rr = (1.0 - best_price) / best_price if best_price > 0 else 0.0
            if rr < settings.MIN_RR_RATIO:
                return None

    return MarketCandidate(
        market=market,
        best_side=best_side,
        market_price=best_price,
    )
```

- [ ] **Step 4: Run new tests — expect all pass**

```bash
cd /Users/pkhaninejad/Desktop/apps/Claude-trade-bot && .venv/bin/python -m pytest prediction_bot/tests/test_scanner.py -v
```

Expected: all tests pass. The existing `test_best_side_yes` and `test_best_side_no` tests use default settings (no `BET_STRATEGY`), which defaults to `"contrarian"` — verify they still pass after that default is confirmed correct, or update them to pass `BET_STRATEGY="kelly"` so they test the old high-prob logic explicitly.

> **Note:** If `test_best_side_yes` or `test_best_side_no` fail because the default is now `"contrarian"`, update those two test fixtures to pass `BET_STRATEGY="kelly"` in their settings.

- [ ] **Step 5: Commit**

```bash
git add prediction_bot/src/bot/scanner.py prediction_bot/tests/test_scanner.py
git commit -m "feat(prediction-bot): strategy-aware side selection in scanner"
```

---

## Task 3: Kelly position sizing in PaperTrader

**Files:**
- Modify: `prediction_bot/src/bot/paper_trader.py`
- Test: `prediction_bot/tests/test_paper_trader.py`

### Kelly formula

```
kelly_fraction = max(0, (llm_confidence − entry_price) / (1 − entry_price))
allocation      = min(kelly_fraction × bankroll, MAX_POSITION_PCT × bankroll)
```

If `kelly_fraction == 0` (LLM confidence ≤ entry price, meaning no edge), the trade is skipped.

- [ ] **Step 1: Write failing tests**

Append to `prediction_bot/tests/test_paper_trader.py`:

```python
@pytest.fixture
async def kelly_trader(tmp_path):
    from prediction_bot.src.data.result_store import ResultStore
    from prediction_bot.src.bot.paper_trader import PaperTrader

    settings = PredictionBotSettings(
        VIRTUAL_BANKROLL=1000.0,
        MAX_POSITION_PCT=0.10,
        MAX_OPEN_POSITIONS=5,
        BET_STRATEGY="kelly",
    )
    store = ResultStore(str(tmp_path / "kelly_test.db"))
    pt = PaperTrader(store=store, settings=settings)
    await pt.initialize()
    return pt


class TestKellySizing:
    async def test_kelly_sizes_by_edge(self, kelly_trader):
        """Kelly allocation = (confidence - price) / (1 - price) * bankroll."""
        # confidence=0.85, entry=0.70 → kelly = (0.85-0.70)/(1-0.70) = 0.5
        # allocation = min(0.5 * 1000, 0.10 * 1000) = 100.0
        c = _candidate(yes_price=0.70)
        c = c.model_copy(update={"llm_confidence": 0.85})
        trade = await kelly_trader.place_paper_trade(c)
        assert trade is not None
        assert abs(trade.cost - 100.0) < 1.0  # capped at MAX_POSITION_PCT

    async def test_kelly_skips_no_edge(self, kelly_trader):
        """Kelly skips trade when llm_confidence <= entry_price (zero/negative edge)."""
        # confidence=0.85, entry=0.90 → kelly = (0.85-0.90)/(1-0.90) = -0.5 → skip
        c = _candidate(yes_price=0.90)
        c = c.model_copy(update={"llm_confidence": 0.85})
        trade = await kelly_trader.place_paper_trade(c)
        assert trade is None

    async def test_kelly_small_edge_small_bet(self, kelly_trader):
        """Kelly allocates less than MAX_POSITION_PCT when edge is small."""
        # confidence=0.82, entry=0.80 → kelly = (0.82-0.80)/(1-0.80) = 0.10
        # allocation = 0.10 * 1000 = 100.0 (happens to equal MAX_POSITION_PCT cap here)
        # Use a tighter example: confidence=0.805, entry=0.80 → kelly = 0.025
        # allocation = 0.025 * 1000 = 25.0, below the 100.0 cap
        c = _candidate(yes_price=0.80)
        c = c.model_copy(update={"llm_confidence": 0.805})
        trade = await kelly_trader.place_paper_trade(c)
        assert trade is not None
        assert trade.cost < 100.0  # below the cap
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/pkhaninejad/Desktop/apps/Claude-trade-bot && .venv/bin/python -m pytest prediction_bot/tests/test_paper_trader.py::TestKellySizing -v
```

Expected: 3 FAILs.

- [ ] **Step 3: Implement Kelly sizing in paper_trader.py**

In `prediction_bot/src/bot/paper_trader.py`, replace the `place_paper_trade` method:

```python
async def place_paper_trade(self, candidate: MarketCandidate) -> PaperTrade | None:
    bankroll = await self.store.get_bankroll()
    open_trades = await self.store.get_open_trades()

    if len(open_trades) >= self.settings.MAX_OPEN_POSITIONS:
        logger.debug("Max positions reached, skipping %s", candidate.market.id)
        return None

    existing_ids = {t.market_id for t in open_trades}
    if candidate.market.id in existing_ids:
        logger.debug("Already holding %s, skipping", candidate.market.id)
        return None

    entry_price = candidate.market_price
    if entry_price <= 0:
        return None

    max_allocation = bankroll * self.settings.MAX_POSITION_PCT

    if self.settings.BET_STRATEGY == "kelly":
        confidence = candidate.llm_confidence or 0.5
        kelly_frac = (confidence - entry_price) / (1.0 - entry_price) if entry_price < 1.0 else 0.0
        if kelly_frac <= 0:
            logger.debug("No Kelly edge for %s (conf=%.2f, price=%.2f), skipping", candidate.market.id, confidence, entry_price)
            return None
        max_allocation = min(kelly_frac * bankroll, max_allocation)

    quantity = int(max_allocation / entry_price)
    if quantity < 1:
        logger.debug("Insufficient bankroll for %s", candidate.market.id)
        return None

    cost = entry_price * quantity
    trade = PaperTrade(
        platform=candidate.market.platform,
        market_id=candidate.market.id,
        market_question=candidate.market.question,
        category=candidate.market.category,
        side=candidate.best_side,
        entry_price=entry_price,
        quantity=float(quantity),
        cost=cost,
        confidence=candidate.llm_confidence or 0.5,
        reasoning=candidate.llm_reasoning,
        created_at=datetime.now(UTC),
        end_date=candidate.market.end_date,
    )
    trade_id = await self.store.add_trade(trade, initial_bankroll=bankroll)
    logger.info(
        "Paper trade: %s '%s' @ $%.2f (qty=%d, cost=$%.2f)",
        trade.side, trade.market_question[:60], trade.entry_price, quantity, cost,
    )
    return trade.model_copy(update={"id": trade_id})
```

- [ ] **Step 4: Run all paper trader tests**

```bash
cd /Users/pkhaninejad/Desktop/apps/Claude-trade-bot && .venv/bin/python -m pytest prediction_bot/tests/test_paper_trader.py -v
```

Expected: all tests pass. The existing `test_quantity_calculation` test uses default settings (no `BET_STRATEGY`), which is `"contrarian"` — flat sizing applies, so existing behaviour is unchanged.

- [ ] **Step 5: Commit**

```bash
git add prediction_bot/src/bot/paper_trader.py prediction_bot/tests/test_paper_trader.py
git commit -m "feat(prediction-bot): Kelly position sizing for kelly strategy"
```

---

## Task 4: Expose strategy in API settings endpoints

**Files:**
- Modify: `prediction_bot/src/dashboard/app.py`

- [ ] **Step 1: Update the Pydantic model and route handlers**

In `prediction_bot/src/dashboard/app.py`, replace `ScannerSettingsUpdate` and the two settings routes:

```python
from typing import Literal

class ScannerSettingsUpdate(BaseModel):
    expiry_window_hours: int = Field(ge=1, le=24 * 365)
    min_liquidity: float = Field(ge=0.0)
    high_prob_min: float = Field(ge=0.0, le=1.0)
    high_prob_max: float = Field(ge=0.0, le=1.0)
    enabled_categories: list[str]
    bet_strategy: Literal["contrarian", "kelly", "min_rr"] = "contrarian"
    min_rr_ratio: float = Field(default=0.25, ge=0.01, le=1.0)


@app.get("/api/settings")
async def get_settings():
    return {
        "expiry_window_hours": engine.settings.EXPIRY_WINDOW_HOURS,
        "min_liquidity": engine.settings.MIN_LIQUIDITY,
        "high_prob_min": engine.settings.HIGH_PROB_MIN,
        "high_prob_max": engine.settings.HIGH_PROB_MAX,
        "enabled_categories": engine.settings.ENABLED_CATEGORIES,
        "bet_strategy": engine.settings.BET_STRATEGY,
        "min_rr_ratio": engine.settings.MIN_RR_RATIO,
    }


@app.post("/api/settings")
async def update_settings(payload: ScannerSettingsUpdate):
    if payload.high_prob_min > payload.high_prob_max:
        return {"error": "high_prob_min cannot be greater than high_prob_max"}, 400
    cleaned_categories = [c.strip().lower() for c in payload.enabled_categories if c.strip()]
    if not cleaned_categories:
        return {"error": "at least one category is required"}, 400

    engine.settings.EXPIRY_WINDOW_HOURS = payload.expiry_window_hours
    engine.settings.MIN_LIQUIDITY = payload.min_liquidity
    engine.settings.HIGH_PROB_MIN = payload.high_prob_min
    engine.settings.HIGH_PROB_MAX = payload.high_prob_max
    engine.settings.ENABLED_CATEGORIES = cleaned_categories
    engine.settings.BET_STRATEGY = payload.bet_strategy
    engine.settings.MIN_RR_RATIO = payload.min_rr_ratio

    return {
        "updated": True,
        "settings": {
            "expiry_window_hours": engine.settings.EXPIRY_WINDOW_HOURS,
            "min_liquidity": engine.settings.MIN_LIQUIDITY,
            "high_prob_min": engine.settings.HIGH_PROB_MIN,
            "high_prob_max": engine.settings.HIGH_PROB_MAX,
            "enabled_categories": engine.settings.ENABLED_CATEGORIES,
            "bet_strategy": engine.settings.BET_STRATEGY,
            "min_rr_ratio": engine.settings.MIN_RR_RATIO,
        },
    }
```

Also add `from typing import Literal` at the top of app.py if not already present.

- [ ] **Step 2: Verify server starts**

```bash
cd /Users/pkhaninejad/Desktop/apps/Claude-trade-bot && .venv/bin/python -c "from prediction_bot.src.dashboard.app import app; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add prediction_bot/src/dashboard/app.py
git commit -m "feat(prediction-bot): expose bet_strategy and min_rr_ratio in settings API"
```

---

## Task 5: Dashboard UI — strategy selector

**Files:**
- Modify: `prediction_bot/src/dashboard/templates/dashboard.html`

The new UI sits **above** the existing settings grid inside the `<div class="section">` that contains "Scanner Settings". It adds:
1. A risk/reward warning callout (amber-tinted box explaining the math)
2. Three radio cards — one per strategy — each with a title, one-line description, and the key math
3. A "Min R:R Ratio" input row that is shown/hidden via JS depending on the selected radio
4. JS updates to `loadSettings()` and `saveSettings()` to include the new fields

- [ ] **Step 1: Add CSS for strategy cards**

Inside the `<style>` block in `dashboard.html`, add after the last existing rule:

```css
.strategy-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 12px; }
.strategy-card { border: 1px solid #30363d; border-radius: 6px; padding: 12px; cursor: pointer; transition: border-color 0.15s; }
.strategy-card:hover { border-color: #58a6ff; }
.strategy-card input[type=radio] { display: none; }
.strategy-card.selected { border-color: #58a6ff; background: #161b22; }
.strategy-card .s-title { font-size: 0.85em; font-weight: 600; color: #c9d1d9; margin-bottom: 4px; }
.strategy-card .s-desc { font-size: 0.75em; color: #8b949e; line-height: 1.4; }
.strategy-card .s-math { font-size: 0.72em; color: #3fb950; font-family: monospace; margin-top: 6px; }
.rr-callout { background: #1a1200; border: 1px solid #b8730e; border-radius: 6px; padding: 10px 14px; font-size: 0.76em; color: #d4a237; margin-bottom: 12px; line-height: 1.5; }
#min-rr-row { display: none; margin-top: 8px; }
```

- [ ] **Step 2: Add the strategy selector HTML**

Inside the `<div class="section">` containing `<h2>Scanner Settings</h2>`, insert the following **before** `<div class="settings-grid">`:

```html
<div class="rr-callout">
  <strong>Why does your win rate not translate to profit?</strong><br>
  When you buy the high-probability side at $0.94, a win returns only $0.06/share while a loss costs $0.94/share — a 15:1 loss-to-win ratio. You need a <em>94%</em> win rate just to break even. Choose a strategy below to fix this.
</div>

<div class="strategy-grid">
  <label class="strategy-card" id="card-contrarian" onclick="selectStrategy('contrarian')">
    <input type="radio" name="bet_strategy" value="contrarian">
    <div class="s-title">Contrarian</div>
    <div class="s-desc">Buy the low-probability side when the market is overconfident. Small cost, large payout when right.</div>
    <div class="s-math">Buy: LOW side &nbsp;|&nbsp; Cost: $0.03–0.20 &nbsp;|&nbsp; Win: $0.80–0.97</div>
  </label>
  <label class="strategy-card" id="card-kelly" onclick="selectStrategy('kelly')">
    <input type="radio" name="bet_strategy" value="kelly">
    <div class="s-title">Kelly Sizing</div>
    <div class="s-desc">Buy the high-probability side but bet only in proportion to your edge over the market price.</div>
    <div class="s-math">Size = (confidence − price) / (1 − price) × bankroll</div>
  </label>
  <label class="strategy-card" id="card-min_rr" onclick="selectStrategy('min_rr')">
    <input type="radio" name="bet_strategy" value="min_rr">
    <div class="s-title">Min Reward / Risk</div>
    <div class="s-desc">Buy the high-probability side only when upside ÷ downside meets a minimum ratio you set.</div>
    <div class="s-math">Filter: (1 − price) / price ≥ ratio</div>
  </label>
</div>
<div id="min-rr-row">
  <label style="font-size:0.75em;color:#8b949e">
    Min R:R Ratio
    <span class="hint" title="Minimum required (win payout) / (loss cost). 0.25 means you must win at least $0.25 for every $1 risked. Caps entries at ~$0.80.">?</span>
  </label>
  <input id="setting-min-rr-ratio" type="number" min="0.01" max="1" step="0.01" style="width:120px;background:#0d1117;border:1px solid #30363d;color:#c9d1d9;padding:6px 8px;border-radius:4px;font-family:monospace;">
</div>
```

- [ ] **Step 3: Add `selectStrategy` JS helper and update `loadSettings` / `saveSettings`**

In the `<script>` block, add this function:

```js
function selectStrategy(value) {
  document.querySelectorAll('.strategy-card').forEach(c => c.classList.remove('selected'));
  const card = document.getElementById('card-' + value);
  if (card) {
    card.classList.add('selected');
    card.querySelector('input[type=radio]').checked = true;
  }
  document.getElementById('min-rr-row').style.display = value === 'min_rr' ? 'block' : 'none';
}
```

In `loadSettings()`, after the line that sets `setting-categories`, add:

```js
selectStrategy(s.bet_strategy || 'contrarian');
document.getElementById('setting-min-rr-ratio').value = s.min_rr_ratio ?? 0.25;
```

In `saveSettings()`, inside the payload object sent to `/api/settings`, add:

```js
bet_strategy: document.querySelector('input[name="bet_strategy"]:checked')?.value || 'contrarian',
min_rr_ratio: parseFloat(document.getElementById('setting-min-rr-ratio').value) || 0.25,
```

- [ ] **Step 4: Run the full test suite**

```bash
cd /Users/pkhaninejad/Desktop/apps/Claude-trade-bot && .venv/bin/python -m pytest prediction_bot/tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add prediction_bot/src/dashboard/templates/dashboard.html
git commit -m "feat(prediction-bot): add bet strategy selector UI with risk/reward explainer"
```

---

## Task 6: Open a PR

- [ ] **Step 1: Push branch and open PR**

```bash
git push -u origin feat/bet-strategy-selector
gh pr create \
  --title "feat(prediction-bot): bet strategy selector (contrarian / Kelly / Min R:R)" \
  --body "$(cat <<'EOF'
## Summary
- Adds `BET_STRATEGY` and `MIN_RR_RATIO` to settings
- Scanner picks the correct side per strategy (contrarian flips to low-prob, min_rr enforces a reward-to-risk gate)
- Paper trader uses Kelly fraction for position sizing when strategy is `kelly`
- Dashboard gains a 3-card radio selector with an amber callout explaining why high win-rate ≠ profit

## Test plan
- [ ] `pytest prediction_bot/tests/` passes
- [ ] Switch to Contrarian, save, trigger a cycle — verify trades show the low-prob side
- [ ] Switch to Min R:R with ratio 0.25, save — verify markets priced above ~$0.80 are skipped
- [ ] Switch to Kelly, save — verify small-edge candidates get smaller allocations than flat 10%
EOF
)"
```
