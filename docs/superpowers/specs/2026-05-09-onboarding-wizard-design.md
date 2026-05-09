# Onboarding Wizard — Design Spec

**Issue:** [#81 — First-run onboarding wizard for non-technical users](https://github.com/pkhaninejad/Claude-trade-bot/issues/81)
**Date:** 2026-05-09
**Milestone:** Sellable v1 (Desktop Binary)

---

## Goal

Guide new users through initial configuration without editing files manually. The bot must be fully runnable from a fresh install with no terminal interaction.

---

## Approach

Multi-step wizard rendered inside the existing Tauri desktop app (React). First-run is detected by the absence (or incompleteness) of `config.json` in the OS app-data directory. The wizard replaces the launcher UI until setup is complete, then transitions to the normal launcher. A Settings panel (gear icon) makes all fields editable post-setup.

No new processes, no routing library, no OS keychain dependency.

---

## Architecture

```
App.tsx boots
    ↓
invoke("load_config")
    ├── config.json missing or setup_complete=false → render <SetupWizard />
    └── config.json present and setup_complete=true → render <Launcher />

SetupWizard completes
    ↓
invoke("save_config", { config })   (setup_complete: true)
    ↓
render <Launcher />  (wizard unmounts, no reload)

Launcher "⚙ Settings" button
    ↓
render <SettingsPanel />  (modal, same Rust commands)

start_bot (Rust)
    ↓
load_config() → write ephemeral .env to project root → spawn Python
```

---

## New Tauri Commands (Rust)

| Command | Signature | Purpose |
|---------|-----------|---------|
| `load_config` | `() → Option<Config>` | Read `{app_data}/config.json`; null if absent |
| `save_config` | `(Config) → Result<()>` | Atomically write `{app_data}/config.json` |
| `test_t212_connection` | `(key, secret, env) → Result<String>` | Hit `GET /equity/account/info`; return balance or plain-English error |
| `test_ai_connection` | `(provider, key) → Result<String>` | Hit provider's test endpoint; return model name or plain-English error |

`start_bot` is extended to: call `load_config` → serialise to `.env` in project root → spawn Python (existing path unchanged).

---

## Config Schema

Stored at `{app_data_dir()}/config.json` (never inside the project repo):

```json
{
  "setup_complete": true,
  "setup_step": 5,
  "t212_api_key": "...",
  "t212_api_secret": "...",
  "t212_env": "demo",
  "t212_account_type": "invest",
  "ai_provider": "anthropic",
  "ai_api_key": "...",
  "stop_loss_pct": 0.02,
  "take_profit_pct": 0.04,
  "max_open_positions": 10,
  "max_position_size_pct": 0.05,
  "watchlist": ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN", "GOOGL", "META"]
}
```

A matching `Config` struct in Rust (serde Serialize/Deserialize) and a TypeScript interface in React mirror this schema exactly.

`settings.py` and the FastAPI backend are **unchanged** — they continue reading `.env` as before.

---

## Wizard Steps

Progress bar at top showing "Step N of 5".

### Step 1 — Welcome
- Friendly intro copy: "Let's get your trading bot set up. Takes about 5 minutes."
- No inputs. Single "Get Started" CTA.

### Step 2 — Trading 212 Connection
- `T212_API_KEY` text field — inline example: "Paste from Settings → API in the T212 app"
- `T212_API_SECRET` text field
- Mode toggle: **Demo** (paper money, pre-selected) | **Live** (real money, amber warning label)
- Account type toggle: **Invest** (pre-selected) | **CFD**
- "Test Connection" button → `test_t212_connection` → shows account balance or plain-English error
- Next button disabled until test passes

### Step 3 — AI Provider
- Provider selector: **Anthropic** (default) | OpenAI | Azure AI | Gemini | DeepSeek | Ollama (local)
- API key field (label updates with provider selection)
- Inline example per provider
- "Test Connection" button → `test_ai_connection` → shows model name or plain-English error
- Next button disabled until test passes

### Step 4 — Risk Profile
- Stop-loss % — slider + number input, default 2%, range 0.5–10%
- Take-profit % — slider + number input, default 4%, range 1–20%
- Max open positions — stepper, default 10, range 1–50
- Max position size % — slider, default 5%, range 1–20%
- No test button. Next always enabled.

### Step 5 — Watchlist
- Pre-checked default tickers: AAPL, TSLA, NVDA, MSFT, AMZN, GOOGL, META, AMD, JPM, V, UBER, PLTR
- User can deselect or add additional tickers via a text input
- "Finish Setup" CTA

### Done Screen
- Confirmation message. Auto-transitions to Launcher after 2 seconds.

---

## Resume Support

After each step's "Next", `save_config` is called with the fields collected so far, `setup_complete: false`, and `setup_step: N` (the step just completed). On re-open, `load_config` detects `setup_complete: false` and uses `setup_step` to jump directly to the next incomplete step, with already-saved fields pre-populated.

---

## Settings Panel (Post-Setup)

Gear icon (⚙) on the Launcher opens a modal overlay containing Step 2–5 forms pre-populated from `config.json`. Save button calls `save_config` and re-invokes `load_config` to refresh the launcher state. No need to restart already-running bots for risk/watchlist changes (they take effect on the next bot restart).

---

## Two-Phase Config

The wizard covers **essential fields only**. Advanced fields (Finnhub, news API, Kalshi, macro calendar, prediction market params) remain user-managed in `.env` for power users. The wizard never overwrites keys it doesn't own.

---

## Error Handling

Plain-English messages returned from Rust test commands:

| Condition | User-facing message |
|-----------|-------------------|
| T212 401 | "Invalid API key or secret — double-check them in the T212 app under Settings → API." |
| T212 403 | "Your account doesn't have API access enabled. Contact T212 support." |
| Network timeout | "Can't reach Trading 212. Check your internet connection and try again." |
| AI 401 | "Invalid API key — make sure you copied the full key including the prefix." |
| AI rate-limit | "Key is valid but rate-limited. Wait a moment and test again." |

Client-side validation before invoking Rust:
- API key fields: non-empty, whitespace-stripped
- Risk sliders: min/max enforced in UI; Rust validates range before writing
- Watchlist: at least one ticker required

---

## Testing

- **Rust unit tests**: `save_config`/`load_config` round-trip; `.env` generation correctness; range validation
- **React component tests (Vitest)**: step navigation; "Next" disabled until test passes; resume from partial config; settings panel pre-population
- **External API calls**: mocked in tests — no live T212/AI calls in CI

---

## Out of Scope (v1)

- Config schema migration between versions
- OS keychain / encrypted storage (can be added later)
- Advanced settings UI (news, Kalshi, macro calendar, prediction markets)
- Dark-mode theming of wizard screens
