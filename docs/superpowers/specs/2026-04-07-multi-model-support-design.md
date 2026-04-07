# Multi-Model LLM Support Design

**Date:** 2026-04-07
**Issue:** [#53](https://github.com/pkhaninejad/Claude-trade-bot/issues/53) — allow app to use different models like ollama, gemini, qwen, deepseek and openai
**Branch:** `feat/multi-model-support`

---

## Summary

Replace the hardcoded Anthropic/Claude integration with a LiteLLM-backed provider system that supports multiple LLM providers switchable at runtime from the dashboard. Credentials persist in a gitignored `credentials.json` file and reset to `.env` defaults only if that file is absent.

---

## Provider Support

| Provider | LiteLLM prefix | Default model | Credential field |
|---|---|---|---|
| `anthropic` | `claude-sonnet-4-6` | `claude-sonnet-4-6` | API key |
| `openai` | `gpt-4o` | `gpt-4o` | API key |
| `gemini` | `gemini/gemini-2.0-flash` | `gemini/gemini-2.0-flash` | API key |
| `ollama` | `ollama/llama3.2` | `ollama/llama3.2` | Base URL |
| `deepseek` | `deepseek/deepseek-chat` | `deepseek/deepseek-chat` | API key |
| `qwen` | `openai/qwen-turbo` | `openai/qwen-turbo` | API key |

---

## Credentials File

`credentials.json` (gitignored) at project root:

```json
{
  "provider": "anthropic",
  "model": "claude-sonnet-4-6",
  "api_key": "sk-...",
  "base_url": ""
}
```

- Read on startup; falls back to `.env` values if file is absent.
- Written by `POST /api/llm/config` from the dashboard.
- `base_url` used only for Ollama (default: `http://localhost:11434`); empty for all others.
- Not committed to git (`.gitignore` entry added).

---

## Architecture

### New file: `src/bot/llm_config.py`

Owns `ProviderConfig` dataclass and two functions:
- `load_provider_config() -> ProviderConfig` — reads `credentials.json`, falls back to `.env`
- `save_provider_config(config: ProviderConfig)` — writes `credentials.json`

```python
@dataclass
class ProviderConfig:
    provider: str       # "anthropic" | "openai" | "gemini" | "ollama" | "deepseek" | "qwen"
    model: str
    api_key: str
    base_url: str       # non-empty only for ollama
```

### Modified: `src/bot/strategy.py`

- Rename `ClaudeStrategy` → `AIStrategy`
- Remove `anthropic` import; add `litellm` import
- `generate_signals()` accepts `provider_config: ProviderConfig` parameter
- Replace `self._client.messages.create(...)` with `litellm.completion(...)`

```python
response = litellm.completion(
    model=config.model,
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ],
    api_key=config.api_key or None,
    base_url=config.base_url or None,
    max_tokens=2048,
)
raw = response.choices[0].message.content.strip()
```

### Modified: `src/bot/engine.py`

- Load `ProviderConfig` on init via `load_provider_config()`
- Store as `self._provider_config: ProviderConfig`
- Pass to `AIStrategy.generate_signals()` each cycle
- Expose `update_provider_config(config: ProviderConfig)` method for dashboard to call live

### Modified: `src/config/settings.py`

- Add per-provider default model constants and API key fields for all providers:
  - `OPENAI_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `QWEN_API_KEY`
  - `OLLAMA_BASE_URL: str = "http://localhost:11434"`
- Keep `ANTHROPIC_API_KEY` and `CLAUDE_MODEL` for backwards compatibility

---

## Dashboard API

### `GET /api/llm/config`
Returns current provider config. API key is masked:
```json
{
  "provider": "anthropic",
  "model": "claude-sonnet-4-6",
  "api_key": "sk-ant-****",
  "base_url": ""
}
```

### `POST /api/llm/config`
Body: `{provider, model, api_key, base_url}`
- Validates provider is one of the supported values
- Saves to `credentials.json`
- Calls `engine.update_provider_config(config)` to apply immediately
- Returns `{"ok": true}`

---

## Dashboard UI

**LLM Settings panel** added to the dashboard (alongside bot controls):

- Provider `<select>` dropdown: anthropic | openai | gemini | ollama | deepseek | qwen
- Model text `<input>` — pre-filled with provider default on provider change, editable
- Credential `<input>`:
  - Label = "API Key" for cloud providers
  - Label = "Base URL" with default `http://localhost:11434` for Ollama
- Save button — POSTs to `/api/llm/config`, shows success/error toast

---

## Bot Start Fix

**Problem:** Start button on dashboard may not reliably reflect or change bot state.
**Fix:**
- Ensure `TradingEngine.start()` sets `self.is_running = True` before returning
- Ensure `TradingEngine.stop()` sets `self.is_running = False`
- `GET /api/status` returns `is_running` from engine state (not from settings)
- Dashboard Start button reads `is_running` from `/api/status` on page load and after toggle

---

## Dependencies

Add to `requirements.txt`:
```
litellm>=1.40.0
```

Remove (or make optional): direct `anthropic` SDK usage in strategy — LiteLLM bundles its own Anthropic transport.

---

## Error Handling

- If `credentials.json` is malformed on load, log a warning and fall back to `.env` defaults
- If `POST /api/llm/config` receives an unknown provider, return HTTP 422
- LiteLLM raises `litellm.exceptions.AuthenticationError` / `APIError` on provider errors — catch and return `[]` signals with an error log (same as current behaviour)

---

## Testing

- Unit test `load_provider_config()` with and without `credentials.json` present
- Unit test `save_provider_config()` writes correct JSON
- Unit test `AIStrategy.generate_signals()` with a mocked `litellm.completion` response
- Integration smoke test: swap provider to `ollama` via `POST /api/llm/config`, verify next cycle uses the new config
