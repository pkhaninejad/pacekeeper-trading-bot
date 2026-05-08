# CFD Account Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `T212_ACCOUNT_TYPE=cfd` support so the bot routes to CFD API paths and allows SHORT signals, while preserving the existing Invest/ISA behaviour under the default `invest` mode.

**Architecture:** A single `T212_ACCOUNT_TYPE` setting drives two concerns: (1) which API path prefix `client.py` uses (`/equity` vs `/cfd`), and (2) whether `RiskManager` blocks SHORT signals. `BotStatus` gains an `account_type` field so the dashboard can display a badge.

**Tech Stack:** Python 3.14, Pydantic v2, FastAPI, httpx, pytest

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/config/settings.py` | Modify | Add `T212_ACCOUNT_TYPE` field and `account_path_prefix` property |
| `src/api/client.py` | Modify | Use `settings.account_path_prefix` instead of hardcoded `/equity` |
| `src/bot/risk_manager.py` | Modify | Conditionally allow SHORT when `T212_ACCOUNT_TYPE=cfd` |
| `src/api/models.py` | Modify | Add `account_type` field to `BotStatus` |
| `src/bot/engine.py` | Modify | Populate `status.account_type` on init |
| `src/dashboard/templates/dashboard.html` | Modify | Add account-type badge next to env badge |
| `.env.example` | Modify | Document `T212_ACCOUNT_TYPE` |
| `tests/test_settings.py` | Modify | Assert `account_path_prefix` returns correct values |
| `tests/test_risk_manager.py` | Modify | Add CFD SHORT-allowed and invest SHORT-blocked tests |

---

## Task 1: Extend Settings with `T212_ACCOUNT_TYPE`

**Files:**
- Modify: `src/config/settings.py`
- Modify: `tests/test_settings.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_settings.py  (append to existing file)

from src.config.settings import Settings

def test_default_account_type_is_invest():
    s = Settings()
    assert s.T212_ACCOUNT_TYPE == "invest"

def test_account_path_prefix_invest():
    s = Settings(T212_ACCOUNT_TYPE="invest")
    assert s.account_path_prefix == "/equity"

def test_account_path_prefix_cfd():
    s = Settings(T212_ACCOUNT_TYPE="cfd")
    assert s.account_path_prefix == "/cfd"
```

- [ ] **Step 2: Run test to verify it fails**

```
.venv/bin/python -m pytest tests/test_settings.py::test_default_account_type_is_invest tests/test_settings.py::test_account_path_prefix_invest tests/test_settings.py::test_account_path_prefix_cfd -v
```

Expected: FAIL — `T212_ACCOUNT_TYPE` does not exist on `Settings`

- [ ] **Step 3: Add the field and property to `src/config/settings.py`**

After `T212_ENV` line (line 10), add:

```python
T212_ACCOUNT_TYPE: Literal["invest", "cfd"] = "invest"
```

After the `t212_base_url` property (after line 66), add:

```python
@property
def account_path_prefix(self) -> str:
    return "/equity" if self.T212_ACCOUNT_TYPE == "invest" else "/cfd"
```

- [ ] **Step 4: Run tests to verify they pass**

```
.venv/bin/python -m pytest tests/test_settings.py -v
```

Expected: all settings tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/config/settings.py tests/test_settings.py
git commit -m "feat: add T212_ACCOUNT_TYPE setting with account_path_prefix"
```

---

## Task 2: Parameterise API Paths in `client.py`

**Files:**
- Modify: `src/api/client.py`

The client currently hardcodes `/equity/` in every path. Replace with `settings.account_path_prefix`.

> **Note:** Trading212 CFD API path prefix (`/cfd`) must be verified against the live CFD documentation before go-live. The prefix used here mirrors the pattern described in the issue. If the actual prefix differs (e.g. `/trading`), update `settings.account_path_prefix` accordingly — no other file needs changing.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_client.py  (append to existing file — or add a new class)

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import httpx
from src.api.client import Trading212Client
from src.config.settings import Settings

@pytest.mark.asyncio
async def test_get_cash_uses_account_path_prefix():
    """Client must call the path derived from account_path_prefix, not hardcoded /equity."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.is_error = False
    mock_response.json.return_value = {
        "free": 1000.0, "total": 2000.0, "ppl": 0.0,
        "result": 0.0, "invested": 1000.0, "pieCash": 0.0,
    }

    with patch("src.config.settings.settings") as mock_settings:
        mock_settings.account_path_prefix = "/equity"
        mock_settings.t212_base_url = "https://demo.trading212.com/api/v0"
        mock_settings.T212_API_KEY = "key"
        mock_settings.T212_API_SECRET = "secret"

        client = Trading212Client()
        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value=mock_response)

        await client.get_cash()
        called_path = client._client.get.call_args[0][0]
        assert called_path == "/equity/account/cash"
```

- [ ] **Step 2: Run test to verify it fails or passes baseline**

```
.venv/bin/python -m pytest tests/test_api_client.py::test_get_cash_uses_account_path_prefix -v
```

- [ ] **Step 3: Update `src/api/client.py` — replace every hardcoded `/equity/` prefix**

In `__init__`, import settings and store the prefix:

```python
# In Trading212Client.__init__ (after self._base = ...)
self._api_prefix = settings.account_path_prefix
```

Then replace every occurrence of `"/equity/` with `f"{self._api_prefix}/` using the mapping below:

| Old string | New string |
|-----------|-----------|
| `"/equity/account/info"` | `f"{self._api_prefix}/account/info"` |
| `"/equity/account/cash"` | `f"{self._api_prefix}/account/cash"` |
| `"/equity/portfolio"` | `f"{self._api_prefix}/portfolio"` |
| `f"/equity/portfolio/{ticker}"` | `f"{self._api_prefix}/portfolio/{ticker}"` |
| `"/equity/orders"` | `f"{self._api_prefix}/orders"` |
| `"/equity/orders/market"` | `f"{self._api_prefix}/orders/market"` |
| `"/equity/orders/limit"` | `f"{self._api_prefix}/orders/limit"` |
| `"/equity/orders/stop"` | `f"{self._api_prefix}/orders/stop"` |
| `f"/equity/orders/{order_id}"` | `f"{self._api_prefix}/orders/{order_id}"` |
| `"/equity/metadata/instruments"` | `f"{self._api_prefix}/metadata/instruments"` |
| `f"/equity/history/orders/{ticker}"` | `f"{self._api_prefix}/history/orders/{ticker}"` |

- [ ] **Step 4: Run all API client tests**

```
.venv/bin/python -m pytest tests/test_api_client.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/api/client.py tests/test_api_client.py
git commit -m "feat: replace hardcoded /equity prefix with dynamic account_path_prefix"
```

---

## Task 3: Allow SHORT Signals in CFD Mode

**Files:**
- Modify: `src/bot/risk_manager.py`
- Modify: `tests/test_risk_manager.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_risk_manager.py  (append inside or after TestValidate class)

class TestCFDShortSupport:
    def test_short_blocked_in_invest_mode(self, monkeypatch):
        monkeypatch.setattr("src.bot.risk_manager.settings.T212_ACCOUNT_TYPE", "invest")
        rm = RiskManager()
        signal = make_signal(action="BUY", direction="SHORT", confidence=0.8)
        approved, reason = rm.validate(signal, [], make_cash())
        assert approved is False
        assert "Short selling is not supported" in reason

    def test_short_allowed_in_cfd_mode(self, monkeypatch):
        monkeypatch.setattr("src.bot.risk_manager.settings.T212_ACCOUNT_TYPE", "cfd")
        rm = RiskManager()
        signal = make_signal(action="BUY", direction="SHORT", confidence=0.8)
        approved, reason = rm.validate(signal, [], make_cash())
        assert approved is True
        assert reason == "Approved"
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv/bin/python -m pytest tests/test_risk_manager.py::TestCFDShortSupport -v
```

Expected: `test_short_allowed_in_cfd_mode` FAIL — SHORT still blocked unconditionally

- [ ] **Step 3: Update the SHORT block in `src/bot/risk_manager.py` lines 73–75**

Replace:

```python
        # Equity accounts on Trading212 do not support opening short positions.
        if signal.direction == "SHORT":
            return False, f"Short selling is not supported for {normalized_ticker}"
```

With:

```python
        # Equity (Invest/ISA) accounts do not support short positions; CFD accounts do.
        if signal.direction == "SHORT" and settings.T212_ACCOUNT_TYPE != "cfd":
            logger.info("Short signal blocked for %s — account type is not CFD", normalized_ticker)
            return False, f"Short selling is not supported for {normalized_ticker}"
```

- [ ] **Step 4: Run all risk manager tests**

```
.venv/bin/python -m pytest tests/test_risk_manager.py -v
```

Expected: all PASS (no existing test should break — the invest path is unchanged)

- [ ] **Step 5: Commit**

```bash
git add src/bot/risk_manager.py tests/test_risk_manager.py
git commit -m "feat: allow SHORT signals when T212_ACCOUNT_TYPE=cfd"
```

---

## Task 4: Surface `account_type` in `BotStatus` and Engine

**Files:**
- Modify: `src/api/models.py`
- Modify: `src/bot/engine.py`
- Modify: `tests/test_models.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_models.py  (append)

from src.api.models import BotStatus

def test_bot_status_has_account_type_field():
    s = BotStatus(enabled=True)
    assert hasattr(s, "account_type")
    assert s.account_type == "invest"      # default

def test_bot_status_cfd_account_type():
    s = BotStatus(enabled=True, account_type="cfd")
    assert s.account_type == "cfd"
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv/bin/python -m pytest tests/test_models.py::test_bot_status_has_account_type_field tests/test_models.py::test_bot_status_cfd_account_type -v
```

Expected: FAIL — `BotStatus` has no `account_type` field

- [ ] **Step 3: Add `account_type` to `BotStatus` in `src/api/models.py`**

In the `BotStatus` class (after `environment: str = "demo"` line ~122), add:

```python
account_type: str = "invest"
```

- [ ] **Step 4: Populate `account_type` in `src/bot/engine.py`**

In `TradingEngine.__init__` where `self.status = BotStatus(...)` is set (line 49), add `account_type=settings.T212_ACCOUNT_TYPE` to the constructor call:

```python
self.status = BotStatus(
    enabled=settings.BOT_ENABLED,
    environment=settings.T212_ENV,
    account_type=settings.T212_ACCOUNT_TYPE,
)
```

- [ ] **Step 5: Run all model and engine tests**

```
.venv/bin/python -m pytest tests/test_models.py tests/test_engine_close.py tests/test_engine_outcomes.py -v
```

Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/api/models.py src/bot/engine.py tests/test_models.py
git commit -m "feat: add account_type to BotStatus and populate from settings"
```

---

## Task 5: Dashboard Account-Type Badge

**Files:**
- Modify: `src/dashboard/templates/dashboard.html`

- [ ] **Step 1: Add CSS for the new badge**

Find the `.regime-badge` style block (around line 61). After it, add:

```css
    .acct-badge {
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 11px;
        font-weight: 600;
        background: rgba(88,166,255,.15);
        color: #58a6ff;
    }
    .acct-badge.cfd { background: rgba(210,153,34,.15); color: var(--yellow); }
```

- [ ] **Step 2: Add the HTML badge element**

Find the header badge row (around line 295):

```html
    <span class="env-badge" id="env-badge">DEMO</span>
    <span class="market-badge" id="market-badge">CLOSED</span>
    <span class="regime-badge" id="regime-badge" style="display:none"></span>
```

Add after `regime-badge`:

```html
    <span class="acct-badge" id="acct-badge">INVEST</span>
```

- [ ] **Step 3: Wire the badge in the JS `updateStatus` function**

Find the block that updates `env-badge` and `market-badge` (around line 543). After the `regime-badge` update block, add:

```javascript
      const ab = document.getElementById('acct-badge');
      if (ab) {
        const acct = (s.account_type || 'invest').toUpperCase();
        ab.textContent = acct;
        ab.className = 'acct-badge' + (s.account_type === 'cfd' ? ' cfd' : '');
      }
```

- [ ] **Step 4: Manual smoke test**

Start the bot with `T212_ACCOUNT_TYPE=invest` (default) and verify the badge shows `INVEST` in blue.  
If you can run with `T212_ACCOUNT_TYPE=cfd`, verify it shows `CFD` in yellow.

- [ ] **Step 5: Commit**

```bash
git add src/dashboard/templates/dashboard.html
git commit -m "feat: add account-type badge to dashboard header"
```

---

## Task 6: Update `.env.example`

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Add the new variable under `T212_ENV`**

Find the line `T212_ENV=demo` and add after it:

```
# "invest" (default) = Invest/ISA account — long-only
# "cfd"              = CFD account — supports long AND short positions
T212_ACCOUNT_TYPE=invest
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: document T212_ACCOUNT_TYPE in .env.example"
```

---

## Task 7: Full Test Suite Pass

- [ ] **Step 1: Run the full test suite**

```
.venv/bin/python -m pytest tests/ -v
```

Expected: all tests PASS, no regressions.

- [ ] **Step 2: If any tests fail, diagnose and fix**

Common failure: a test that patches `settings` directly in `risk_manager` — ensure the monkeypatch attribute path matches `src.bot.risk_manager.settings.T212_ACCOUNT_TYPE`.

- [ ] **Step 3: Final commit if any fixups were needed**

```bash
git add -p   # stage only fixup changes
git commit -m "fix: address test regressions from CFD support"
```

---

## Self-Review Checklist

### Spec Coverage

| Acceptance criterion | Task |
|---------------------|------|
| `T212_ACCOUNT_TYPE` env var in settings | Task 1 |
| Client routes to correct API paths | Task 2 |
| SHORT signals allowed when `T212_ACCOUNT_TYPE=cfd` | Task 3 |
| SHORT block kept for invest mode with log message | Task 3 |
| Dashboard badge shows account type | Task 5 |
| `.env.example` / README updated | Task 6 |

> **README note:** The issue mentions updating README with CFD setup instructions. Add a short "CFD Mode" section to README.md after completing the above tasks. This is a documentation-only step: explain that CFD requires a separate Trading212 CFD account, that the same API key pair is used, and that `T212_ACCOUNT_TYPE=cfd` enables SHORT signals.

### Known Assumption to Verify

The CFD API path prefix is assumed to be `/cfd`. Before merging, confirm against the Trading212 CFD API documentation that account info, portfolio, and order endpoints are under `/cfd/...`. If the prefix is different (e.g. `/trading`), update only `settings.account_path_prefix` — no other file changes are required.
