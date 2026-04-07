# Multi-Model LLM Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded Anthropic/Claude integration with a LiteLLM-backed system supporting anthropic, openai, gemini, ollama, deepseek, and qwen — switchable live from the dashboard with credentials persisted to a gitignored `credentials.json`.

**Architecture:** A new `src/bot/llm_config.py` module owns `ProviderConfig` (dataclass) and load/save logic. `strategy.py` becomes provider-agnostic by replacing the `anthropic` SDK with `litellm.completion()`. `TradingEngine` holds the active config and exposes `update_provider_config()` for the dashboard to call live. Two new API endpoints (`GET/POST /api/llm/config`) serve the dashboard panel.

**Tech Stack:** `litellm>=1.40.0`, existing FastAPI + Pydantic stack, vanilla JS in dashboard template.

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `src/bot/llm_config.py` | ProviderConfig dataclass, load/save, provider defaults |
| Create | `tests/test_llm_config.py` | Unit tests for llm_config |
| Modify | `src/bot/strategy.py` | Replace anthropic → litellm, ClaudeStrategy → AIStrategy |
| Modify | `tests/test_strategy.py` | Update mocks from anthropic client to litellm.completion |
| Modify | `src/config/settings.py` | Add per-provider API key / URL fields |
| Modify | `src/bot/engine.py` | Use AIStrategy, load/hold ProviderConfig, add update_provider_config |
| Modify | `src/dashboard/app.py` | Add GET/POST /api/llm/config endpoints |
| Modify | `src/dashboard/templates/dashboard.html` | Add LLM Settings panel, fix Start button await |
| Modify | `requirements.txt` | Add litellm |
| Modify | `.gitignore` | Add credentials.json |

---

## Task 1: Branch setup — add litellm + gitignore credentials.json

**Files:**
- Modify: `requirements.txt`
- Modify: `.gitignore`

- [ ] **Step 1: Add litellm to requirements.txt**

Open `requirements.txt` and add after the `anthropic` line:
```
litellm>=1.40.0
```

- [ ] **Step 2: Add credentials.json to .gitignore**

Open `.gitignore` and add under the `# Environment` section:
```
credentials.json
```

- [ ] **Step 3: Install litellm**

```bash
.venv/bin/pip install litellm>=1.40.0
```

Expected: installs successfully, no conflict with existing packages.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt .gitignore
git commit -m "chore: add litellm dependency and gitignore credentials.json"
```

---

## Task 2: Create `src/bot/llm_config.py`

**Files:**
- Create: `src/bot/llm_config.py`

- [ ] **Step 1: Write the file**

Create `src/bot/llm_config.py` with this exact content:

```python
"""
Provider configuration for the LLM strategy layer.

Loads from credentials.json (gitignored) at project root.
Falls back to .env settings if the file is absent or malformed.
"""

import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path

logger = logging.getLogger(__name__)

CREDENTIALS_FILE = Path("credentials.json")

# Default model string and base_url per provider.
# base_url is empty for cloud providers; non-empty for local/compatible endpoints.
PROVIDER_DEFAULTS: dict[str, dict] = {
    "anthropic": {"model": "claude-sonnet-4-6", "base_url": ""},
    "openai":    {"model": "gpt-4o",            "base_url": ""},
    "gemini":    {"model": "gemini/gemini-2.0-flash", "base_url": ""},
    "ollama":    {"model": "ollama/llama3.2",    "base_url": "http://localhost:11434"},
    "deepseek":  {"model": "deepseek/deepseek-chat", "base_url": ""},
    "qwen":      {"model": "openai/qwen-turbo",  "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
}

SUPPORTED_PROVIDERS = list(PROVIDER_DEFAULTS.keys())


@dataclass
class ProviderConfig:
    provider: str   # one of SUPPORTED_PROVIDERS
    model: str      # litellm model string, e.g. "gpt-4o" or "ollama/llama3.2"
    api_key: str    # empty string for Ollama (no key needed)
    base_url: str   # non-empty for Ollama and Qwen; empty for other cloud providers


def load_provider_config() -> ProviderConfig:
    """Read credentials.json; fall back to .env/settings defaults if absent or malformed."""
    from src.config.settings import settings

    if CREDENTIALS_FILE.exists():
        try:
            data = json.loads(CREDENTIALS_FILE.read_text())
            return ProviderConfig(
                provider=data.get("provider", "anthropic"),
                model=data.get("model", settings.CLAUDE_MODEL),
                api_key=data.get("api_key", settings.ANTHROPIC_API_KEY),
                base_url=data.get("base_url", ""),
            )
        except Exception as e:
            logger.warning("credentials.json malformed (%s) — using .env defaults", e)

    return ProviderConfig(
        provider="anthropic",
        model=settings.CLAUDE_MODEL,
        api_key=settings.ANTHROPIC_API_KEY,
        base_url="",
    )


def save_provider_config(config: ProviderConfig) -> None:
    """Write provider config to credentials.json."""
    CREDENTIALS_FILE.write_text(json.dumps(asdict(config), indent=2))
```

- [ ] **Step 2: Verify the module imports cleanly**

```bash
.venv/bin/python -c "from src.bot.llm_config import load_provider_config, SUPPORTED_PROVIDERS; print(SUPPORTED_PROVIDERS)"
```

Expected output: `['anthropic', 'openai', 'gemini', 'ollama', 'deepseek', 'qwen']`

- [ ] **Step 3: Commit**

```bash
git add src/bot/llm_config.py
git commit -m "feat: add llm_config module with ProviderConfig and credentials.json persistence"
```

---

## Task 3: Tests for `llm_config.py`

**Files:**
- Create: `tests/test_llm_config.py`

- [ ] **Step 1: Write the test file**

Create `tests/test_llm_config.py`:

```python
"""Tests for src/bot/llm_config.py."""

import json
import pytest
from pathlib import Path
from src.bot.llm_config import ProviderConfig, load_provider_config, save_provider_config


@pytest.fixture(autouse=True)
def patch_credentials_file(tmp_path, monkeypatch):
    """Redirect CREDENTIALS_FILE to a temp path for every test."""
    creds = tmp_path / "credentials.json"
    monkeypatch.setattr("src.bot.llm_config.CREDENTIALS_FILE", creds)
    return creds


class TestLoadProviderConfig:
    def test_falls_back_to_anthropic_when_file_absent(self):
        config = load_provider_config()
        assert config.provider == "anthropic"

    def test_falls_back_when_file_is_malformed_json(self, patch_credentials_file):
        patch_credentials_file.write_text("not { valid json }")
        config = load_provider_config()
        assert config.provider == "anthropic"

    def test_loads_saved_provider(self, patch_credentials_file):
        patch_credentials_file.write_text(json.dumps({
            "provider": "openai",
            "model": "gpt-4o",
            "api_key": "sk-test",
            "base_url": "",
        }))
        config = load_provider_config()
        assert config.provider == "openai"
        assert config.model == "gpt-4o"
        assert config.api_key == "sk-test"

    def test_loads_ollama_with_base_url(self, patch_credentials_file):
        patch_credentials_file.write_text(json.dumps({
            "provider": "ollama",
            "model": "ollama/llama3.2",
            "api_key": "",
            "base_url": "http://localhost:11434",
        }))
        config = load_provider_config()
        assert config.provider == "ollama"
        assert config.base_url == "http://localhost:11434"
        assert config.api_key == ""


class TestSaveProviderConfig:
    def test_writes_valid_json(self, patch_credentials_file):
        config = ProviderConfig(
            provider="deepseek",
            model="deepseek/deepseek-chat",
            api_key="ds-key",
            base_url="",
        )
        save_provider_config(config)
        data = json.loads(patch_credentials_file.read_text())
        assert data["provider"] == "deepseek"
        assert data["model"] == "deepseek/deepseek-chat"
        assert data["api_key"] == "ds-key"
        assert data["base_url"] == ""

    def test_roundtrip(self, patch_credentials_file):
        original = ProviderConfig(
            provider="gemini",
            model="gemini/gemini-2.0-flash",
            api_key="gm-key",
            base_url="",
        )
        save_provider_config(original)
        loaded = load_provider_config()
        assert loaded.provider == original.provider
        assert loaded.model == original.model
        assert loaded.api_key == original.api_key
```

- [ ] **Step 2: Run the tests**

```bash
.venv/bin/python -m pytest tests/test_llm_config.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_llm_config.py
git commit -m "test: add unit tests for llm_config load/save"
```

---

## Task 4: Refactor `src/bot/strategy.py` — replace anthropic with litellm

**Files:**
- Modify: `src/bot/strategy.py`

- [ ] **Step 1: Replace the import block and class**

In `src/bot/strategy.py`, replace:
```python
import anthropic
from src.config.settings import settings
from src.api.models import Position, CashInfo, TradeSignal, Instrument
from src.bot.price_feed import get_price_summary
from src.data.earnings_calendar import EarningsInfo
from src.data.news_feed import NewsItem
```

With:
```python
import litellm
from src.config.settings import settings
from src.api.models import Position, CashInfo, TradeSignal, Instrument
from src.bot.llm_config import ProviderConfig
from src.bot.price_feed import get_price_summary
from src.data.earnings_calendar import EarningsInfo
from src.data.news_feed import NewsItem
```

- [ ] **Step 2: Replace the `ClaudeStrategy` class**

Replace the entire `ClaudeStrategy` class (lines 237–295) with:

```python
class AIStrategy:
    """LLM-powered trading strategy. Provider-agnostic via LiteLLM."""

    def generate_signals(
        self,
        positions: list[Position],
        cash: CashInfo,
        watchlist: list[str],
        instruments: list[Instrument],
        provider_config: "ProviderConfig | None" = None,
        earnings_info: dict[str, "EarningsInfo"] | None = None,
        news_data: dict[str, list["NewsItem"]] | None = None,
        outcome_log: list | None = None,
    ) -> list[TradeSignal]:
        """Call the configured LLM provider and parse trade signals."""
        if provider_config is None:
            from src.bot.llm_config import load_provider_config
            provider_config = load_provider_config()

        price_data = get_price_summary(watchlist)
        user_prompt = _build_market_context(
            positions, cash, watchlist, instruments, price_data,
            earnings_info, news_data, outcome_log,
        )

        logger.info("Calling %s/%s for trading signals...", provider_config.provider, provider_config.model)
        try:
            response = litellm.completion(
                model=provider_config.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                api_key=provider_config.api_key or None,
                api_base=provider_config.base_url or None,
                max_tokens=2048,
            )
            raw = response.choices[0].message.content.strip()
            logger.debug("LLM raw response: %s", raw)

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
            logger.error("Failed to parse LLM response as JSON: %s", e)
            return []
        except Exception as e:
            logger.error("LLM API error: %s", e)
            return []
```

- [ ] **Step 3: Verify the module imports cleanly**

```bash
.venv/bin/python -c "from src.bot.strategy import AIStrategy; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add src/bot/strategy.py
git commit -m "feat: replace anthropic SDK with litellm in strategy, rename to AIStrategy"
```

---

## Task 5: Update `tests/test_strategy.py`

**Files:**
- Modify: `tests/test_strategy.py`

The existing tests mock `strategy._client` (the anthropic client). We need to mock `litellm.completion` instead, and import `AIStrategy` instead of `ClaudeStrategy`.

- [ ] **Step 1: Replace the import line**

Replace:
```python
from src.bot.strategy import _build_market_context, ClaudeStrategy
```

With:
```python
from src.bot.strategy import _build_market_context, AIStrategy
from src.bot.llm_config import ProviderConfig
```

- [ ] **Step 2: Replace the `TestGenerateSignals` class**

Replace the entire `TestGenerateSignals` class with:

```python
def _make_config() -> ProviderConfig:
    return ProviderConfig(provider="anthropic", model="claude-sonnet-4-6", api_key="test-key", base_url="")


def _mock_litellm(text: str):
    """Return a MagicMock that looks like a litellm completion response."""
    from unittest.mock import MagicMock
    resp = MagicMock()
    resp.choices[0].message.content = text
    return resp


class TestGenerateSignals:
    def test_valid_json_array_parsed(self):
        payload = json.dumps([{
            "ticker": "AAPL", "action": "BUY", "direction": "LONG",
            "confidence": 0.85, "reasoning": "bullish", "order_type": "MARKET",
        }])
        with patch("src.bot.strategy.litellm.completion", return_value=_mock_litellm(payload)):
            signals = AIStrategy().generate_signals([], make_cash(), ["AAPL"], [], provider_config=_make_config())
        assert len(signals) == 1
        assert signals[0].ticker == "AAPL"
        assert signals[0].confidence == 0.85

    def test_single_dict_wrapped_in_list(self):
        payload = json.dumps({
            "ticker": "TSLA", "action": "SELL", "direction": "CLOSE",
            "confidence": 0.9, "reasoning": "take profit", "order_type": "MARKET",
        })
        with patch("src.bot.strategy.litellm.completion", return_value=_mock_litellm(payload)):
            signals = AIStrategy().generate_signals([], make_cash(), ["TSLA"], [], provider_config=_make_config())
        assert len(signals) == 1
        assert signals[0].ticker == "TSLA"

    def test_markdown_code_fence_stripped(self):
        payload = "```json\n" + json.dumps([{
            "ticker": "NVDA", "action": "BUY", "direction": "LONG",
            "confidence": 0.75, "reasoning": "gpu demand", "order_type": "MARKET",
        }]) + "\n```"
        with patch("src.bot.strategy.litellm.completion", return_value=_mock_litellm(payload)):
            signals = AIStrategy().generate_signals([], make_cash(), ["NVDA"], [], provider_config=_make_config())
        assert len(signals) == 1
        assert signals[0].ticker == "NVDA"

    def test_invalid_json_returns_empty(self):
        with patch("src.bot.strategy.litellm.completion", return_value=_mock_litellm("not valid json")):
            signals = AIStrategy().generate_signals([], make_cash(), ["AAPL"], [], provider_config=_make_config())
        assert signals == []

    def test_malformed_signal_skipped(self):
        payload = json.dumps([
            {"ticker": "AAPL", "action": "BUY", "direction": "LONG",
             "confidence": 0.8, "reasoning": "ok", "order_type": "MARKET"},
            {"this": "is", "missing": "required fields"},
        ])
        with patch("src.bot.strategy.litellm.completion", return_value=_mock_litellm(payload)):
            signals = AIStrategy().generate_signals([], make_cash(), ["AAPL"], [], provider_config=_make_config())
        assert len(signals) == 1

    def test_api_exception_returns_empty(self):
        with patch("src.bot.strategy.litellm.completion", side_effect=Exception("API down")):
            signals = AIStrategy().generate_signals([], make_cash(), ["AAPL"], [], provider_config=_make_config())
        assert signals == []

    def test_multiple_signals_returned(self):
        payload = json.dumps([
            {"ticker": "AAPL", "action": "BUY", "direction": "LONG",
             "confidence": 0.8, "reasoning": "momentum", "order_type": "MARKET"},
            {"ticker": "TSLA", "action": "BUY", "direction": "SHORT",
             "confidence": 0.7, "reasoning": "overbought", "order_type": "MARKET"},
        ])
        with patch("src.bot.strategy.litellm.completion", return_value=_mock_litellm(payload)):
            signals = AIStrategy().generate_signals([], make_cash(), ["AAPL", "TSLA"], [], provider_config=_make_config())
        assert len(signals) == 2
        assert {s.ticker for s in signals} == {"AAPL", "TSLA"}

    def test_uses_provider_config_model(self):
        config = ProviderConfig(provider="openai", model="gpt-4o", api_key="sk-test", base_url="")
        payload = json.dumps([{
            "ticker": "AAPL", "action": "HOLD", "direction": "LONG",
            "confidence": 0.5, "reasoning": "uncertain", "order_type": "MARKET",
        }])
        with patch("src.bot.strategy.litellm.completion", return_value=_mock_litellm(payload)) as mock_call:
            AIStrategy().generate_signals([], make_cash(), ["AAPL"], [], provider_config=config)
        mock_call.assert_called_once()
        call_kwargs = mock_call.call_args
        assert call_kwargs.kwargs["model"] == "gpt-4o"
        assert call_kwargs.kwargs["api_key"] == "sk-test"
```

- [ ] **Step 3: Add missing import at top of test file**

Ensure `from unittest.mock import MagicMock, patch` is present in the imports block (replace existing `from unittest.mock import MagicMock, patch`).

- [ ] **Step 4: Run the strategy tests**

```bash
.venv/bin/python -m pytest tests/test_strategy.py -v
```

Expected: all tests pass (the `TestBuildMarketContext`, `TestEarningsPromptInjection`, `TestNewsPromptInjection`, `TestPerformanceSummaryInjection` classes are unchanged and should still pass; `TestGenerateSignals` is replaced and should pass too).

- [ ] **Step 5: Commit**

```bash
git add tests/test_strategy.py
git commit -m "test: update strategy tests to mock litellm.completion, use AIStrategy"
```

---

## Task 6: Update `src/config/settings.py` — add provider fields

**Files:**
- Modify: `src/config/settings.py`

- [ ] **Step 1: Add per-provider fields after the `ANTHROPIC_API_KEY` line**

In `src/config/settings.py`, replace the Anthropic block:
```python
    # Anthropic
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-sonnet-4-6"
```

With:
```python
    # Anthropic (default provider)
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-sonnet-4-6"

    # Additional LLM provider keys (used as fallback if credentials.json absent)
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""
    QWEN_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"
```

- [ ] **Step 2: Verify settings still load cleanly**

```bash
.venv/bin/python -c "from src.config.settings import settings; print(settings.OLLAMA_BASE_URL)"
```

Expected: `http://localhost:11434`

- [ ] **Step 3: Run settings tests**

```bash
.venv/bin/python -m pytest tests/test_settings.py -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add src/config/settings.py
git commit -m "feat: add per-provider API key fields to settings"
```

---

## Task 7: Update `src/bot/engine.py` — use AIStrategy and ProviderConfig

**Files:**
- Modify: `src/bot/engine.py`

- [ ] **Step 1: Update imports**

Replace:
```python
from src.bot.strategy import ClaudeStrategy
```

With:
```python
from src.bot.strategy import AIStrategy
from src.bot.llm_config import ProviderConfig, load_provider_config
```

- [ ] **Step 2: Update `__init__` to use AIStrategy and load config**

Replace:
```python
        self.strategy = ClaudeStrategy()
```

With:
```python
        self.strategy = AIStrategy()
        self._provider_config: ProviderConfig = load_provider_config()
```

- [ ] **Step 3: Add `update_provider_config` method after `toggle()`**

After the `toggle` method (around line 89), add:

```python
    def update_provider_config(self, config: ProviderConfig) -> None:
        """Hot-swap the LLM provider. Takes effect on the next trading cycle."""
        self._provider_config = config
        logger.info("Provider config updated: %s/%s", config.provider, config.model)
```

- [ ] **Step 4: Pass provider_config into generate_signals in `_cycle()`**

Replace:
```python
            signals = self.strategy.generate_signals(
                positions, cash, settings.WATCHLIST, instruments, earnings_info, news_data,
                outcome_log=self.outcome_log,
            )
```

With:
```python
            signals = self.strategy.generate_signals(
                positions, cash, settings.WATCHLIST, instruments,
                provider_config=self._provider_config,
                earnings_info=earnings_info,
                news_data=news_data,
                outcome_log=self.outcome_log,
            )
```

- [ ] **Step 5: Verify engine imports cleanly**

```bash
.venv/bin/python -c "from src.bot.engine import TradingEngine; print('ok')"
```

Expected: `ok`

- [ ] **Step 6: Run all tests to confirm nothing broken**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/bot/engine.py
git commit -m "feat: wire AIStrategy and ProviderConfig into TradingEngine"
```

---

## Task 8: Add LLM config API endpoints to `src/dashboard/app.py`

**Files:**
- Modify: `src/dashboard/app.py`

- [ ] **Step 1: Add imports at the top of app.py**

After the existing imports, add:
```python
from pydantic import BaseModel
from src.bot.llm_config import (
    ProviderConfig, load_provider_config, save_provider_config,
    SUPPORTED_PROVIDERS, PROVIDER_DEFAULTS,
)
```

- [ ] **Step 2: Add the request model and two endpoints**

Add these after the `trigger_cycle` endpoint (after line 181):

```python
# ─── LLM provider config ──────────────────────────────────────────────────────

class LLMConfigRequest(BaseModel):
    provider: str
    model: str
    api_key: str
    base_url: str = ""


@app.get("/api/llm/config", tags=["Bot"])
async def get_llm_config():
    """Return the active LLM provider config (API key masked)."""
    config = engine._provider_config
    masked_key = ""
    if config.api_key:
        visible = config.api_key[:8] if len(config.api_key) >= 8 else config.api_key
        masked_key = visible + "****"
    return {
        "provider": config.provider,
        "model": config.model,
        "api_key": masked_key,
        "base_url": config.base_url,
        "supported_providers": SUPPORTED_PROVIDERS,
        "provider_defaults": PROVIDER_DEFAULTS,
    }


@app.post("/api/llm/config", tags=["Bot"])
async def set_llm_config(req: LLMConfigRequest):
    """Update the active LLM provider. Persists to credentials.json."""
    if req.provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported provider '{req.provider}'. Choose from: {SUPPORTED_PROVIDERS}",
        )
    config = ProviderConfig(
        provider=req.provider,
        model=req.model,
        api_key=req.api_key,
        base_url=req.base_url,
    )
    save_provider_config(config)
    engine.update_provider_config(config)
    return {"ok": True}
```

- [ ] **Step 3: Verify app imports cleanly**

```bash
.venv/bin/python -c "from src.dashboard.app import app; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add src/dashboard/app.py
git commit -m "feat: add GET/POST /api/llm/config endpoints for runtime provider switching"
```

---

## Task 9: Dashboard UI — LLM Settings panel + Start button fix

**Files:**
- Modify: `src/dashboard/templates/dashboard.html`

### Part A — CSS (add to the `<style>` block)

- [ ] **Step 1: Add LLM panel CSS**

Inside the `<style>` block, before the closing `</style>` tag, add:

```css
    /* ── LLM Settings panel ── */
    .llm-panel {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px 20px;
      margin-bottom: 24px;
    }
    .llm-panel h2 {
      font-size: 14px; font-weight: 600;
      margin-bottom: 12px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: .05em;
    }
    .llm-form {
      display: flex;
      gap: 10px;
      align-items: flex-end;
      flex-wrap: wrap;
    }
    .llm-form label { font-size: 11px; color: var(--muted); display: block; margin-bottom: 4px; text-transform: uppercase; letter-spacing:.04em; }
    .llm-form select, .llm-form input[type="text"] {
      background: var(--surface2);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 6px 10px;
      border-radius: 6px;
      font-size: 13px;
      min-width: 160px;
    }
    .llm-form input[type="text"] { min-width: 220px; }
    #llm-save-btn {
      background: var(--blue);
      border: none;
      color: #000;
      padding: 7px 16px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 13px;
      font-weight: 600;
    }
    #llm-save-btn:hover { opacity: .85; }
    #llm-toast {
      font-size: 12px;
      padding: 4px 10px;
      border-radius: 4px;
      display: none;
    }
    #llm-toast.ok  { background: rgba(63,185,80,.15); color: var(--green); display: inline-block; }
    #llm-toast.err { background: rgba(248,81,73,.15);  color: var(--red);   display: inline-block; }
```

### Part B — HTML (add panel after the KPI grid)

- [ ] **Step 2: Add the LLM Settings panel HTML**

After the closing `</div>` of the `.grid` (KPI cards, around line 257), add:

```html
    <!-- LLM Settings -->
    <div class="llm-panel">
      <h2>LLM Settings</h2>
      <div class="llm-form">
        <div>
          <label for="llm-provider">Provider</label>
          <select id="llm-provider">
            <option value="anthropic">Anthropic</option>
            <option value="openai">OpenAI</option>
            <option value="gemini">Gemini</option>
            <option value="ollama">Ollama</option>
            <option value="deepseek">DeepSeek</option>
            <option value="qwen">Qwen</option>
          </select>
        </div>
        <div>
          <label for="llm-model">Model</label>
          <input type="text" id="llm-model" placeholder="model name" />
        </div>
        <div id="llm-cred-wrap">
          <label for="llm-credential" id="llm-cred-label">API Key</label>
          <input type="text" id="llm-credential" placeholder="enter key" />
        </div>
        <button id="llm-save-btn">Save</button>
        <span id="llm-toast"></span>
      </div>
    </div>
```

### Part C — JavaScript

- [ ] **Step 3: Add LLM settings JS before the closing `</script>` tag**

Add before the closing `</script>` tag (before line 689):

```javascript
  // ── LLM Settings ─────────────────────────────────────────────────────────
  const PROVIDER_USES_URL = new Set(['ollama', 'qwen']);

  async function loadLLMConfig() {
    try {
      const cfg = await fetchJSON('/api/llm/config');
      const providerDefaults = cfg.provider_defaults || {};
      document.getElementById('llm-provider').value = cfg.provider;
      document.getElementById('llm-model').value = cfg.model;
      updateLLMCredField(cfg.provider, cfg.api_key, cfg.base_url);
      // Store defaults for provider-change pre-fill
      window._llmDefaults = providerDefaults;
    } catch(e) { console.warn('llm config load failed', e); }
  }

  function updateLLMCredField(provider, apiKey, baseUrl) {
    const label = document.getElementById('llm-cred-label');
    const input = document.getElementById('llm-credential');
    if (PROVIDER_USES_URL.has(provider)) {
      label.textContent = 'Base URL';
      input.placeholder = 'http://localhost:11434';
      input.value = baseUrl || '';
    } else {
      label.textContent = 'API Key';
      input.placeholder = 'enter API key';
      input.value = apiKey || '';
    }
  }

  document.getElementById('llm-provider').addEventListener('change', function() {
    const provider = this.value;
    const defaults = (window._llmDefaults || {})[provider] || {};
    document.getElementById('llm-model').value = defaults.model || '';
    updateLLMCredField(provider, '', defaults.base_url || '');
  });

  document.getElementById('llm-save-btn').addEventListener('click', async () => {
    const provider = document.getElementById('llm-provider').value;
    const model = document.getElementById('llm-model').value.trim();
    const credVal = document.getElementById('llm-credential').value.trim();
    const isUrl = PROVIDER_USES_URL.has(provider);
    const body = {
      provider,
      model,
      api_key: isUrl ? '' : credVal,
      base_url: isUrl ? credVal : '',
    };
    const toast = document.getElementById('llm-toast');
    try {
      const res = await fetch('/api/llm/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || res.statusText);
      }
      toast.textContent = 'Saved';
      toast.className = 'ok';
    } catch(e) {
      toast.textContent = `Error: ${e.message}`;
      toast.className = 'err';
    }
    setTimeout(() => { toast.className = ''; toast.textContent = ''; }, 3000);
  });

  loadLLMConfig();
```

### Part D — Start button fix

- [ ] **Step 4: Fix the toggle button click handler to await refreshStatus**

Replace:
```javascript
  document.getElementById('toggle-btn').addEventListener('click', async () => {
    await fetch('/api/bot/toggle', { method: 'POST' });
    refreshStatus();
  });
```

With:
```javascript
  document.getElementById('toggle-btn').addEventListener('click', async () => {
    await fetch('/api/bot/toggle', { method: 'POST' });
    await refreshStatus();
  });
```

- [ ] **Step 5: Commit**

```bash
git add src/dashboard/templates/dashboard.html
git commit -m "feat: add LLM Settings panel to dashboard and fix toggle button await"
```

---

## Task 10: Full test run + push branch + open PR

- [ ] **Step 1: Run all tests**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all tests pass with no failures.

- [ ] **Step 2: Push branch**

```bash
git push -u origin feat/multi-model-support
```

- [ ] **Step 3: Open PR**

```bash
gh pr create \
  --title "feat: multi-model LLM support (litellm + runtime dashboard switching)" \
  --body "$(cat <<'EOF'
## Summary
- Replaces hardcoded Anthropic SDK with LiteLLM — supports anthropic, openai, gemini, ollama, deepseek, qwen
- Runtime provider/model switching from dashboard LLM Settings panel
- Credentials persisted to gitignored `credentials.json`; falls back to `.env` on first run
- Renames `ClaudeStrategy` → `AIStrategy` in `strategy.py`
- Fixes toggle button `await` so Start/Pause state updates reliably

## Test plan
- [ ] Run `pytest tests/ -v` — all pass
- [ ] Start server, open dashboard, verify LLM Settings panel appears
- [ ] Switch provider to OpenAI, save — verify `credentials.json` created with correct values
- [ ] Switch back to anthropic — verify trading cycle uses Claude again
- [ ] Click Pause Bot / Start Bot — verify button text updates immediately

Closes #53

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 4: Post PR link as comment on issue #53**

```bash
gh issue comment 53 --repo pkhaninejad/Claude-trade-bot --body "PR opened: $(gh pr view --json url -q .url)"
```
