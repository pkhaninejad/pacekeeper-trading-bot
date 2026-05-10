# Design: Simple / Advanced Dashboard Mode (Issue #84)

**Date:** 2026-05-11  
**Status:** Approved  
**Milestone:** Sellable v1 (Desktop Binary)

---

## Goal

Reduce cognitive overload for non-technical users by introducing a **Simple** view (default for first-time users) alongside the existing **Advanced** view. Users must be able to start, pause, and monitor the bot without reading any documentation.

---

## Acceptance Criteria

- Simple mode is default for first-time users (detected via `localStorage`).
- Core user can start, pause, and monitor the bot without docs.
- Human-readable activity stream replaces log jargon in the primary view.
- Mode persists across page reloads.
- Mode can be changed at any time from the header.

---

## Approach

**Pure client-side, single HTML file.** No backend changes, no new API endpoints, no new templates. Mode is stored in `localStorage` under the key `pk_mode` (`"simple"` | `"advanced"`). CSS class toggling on `<body>` shows/hides sections instantly with no page reload.

Rationale: the beginner additions are self-contained and additive. The Advanced view is untouched. Splitting the file is deferred to a follow-up PR if the file exceeds 1400 lines.

---

## Mode Storage & First-Run Detection

- Key: `localStorage.getItem('pk_mode')` → `"simple"` | `"advanced"`
- **First visit** (key absent): show the first-run modal. User picks a mode. Modal saves the choice and closes. Never shown again.
- **Returning visit** (key present): apply mode on page load via an inline `<script>` at the top of `<body>` that sets the body class synchronously — prevents any flash of wrong content.
- Pressing Escape or clicking the modal backdrop saves `"simple"` (safe default) and closes.

---

## First-Run Modal

Shown once, centered with a semi-transparent backdrop (`rgba(10,37,64,0.45)`).

**Content:**
- Heading: "Welcome to Pacekeeper"
- Subtext: "How would you like to see your dashboard? You can change this any time from the header."
- Two side-by-side cards:
  - **Simple view** (🟢) — pre-selected, cobalt highlight border, "Default · Recommended" badge. Copy: "Plain-English status, your investments at a glance, and easy controls. No jargon."
  - **Advanced view** (📊) — unselected by default. Copy: "Full indicators, signal tables, trade log, and all technical data."
- Single CTA: "Get started" button — saves the selected card's mode and dismisses the modal.
- Clicking a card selects it (highlighted border); clicking again on the already-selected card does nothing.

---

## Header Toggle

A pill toggle inserted in the header between the INVEST account badge and the status dot.

**Structure:**
```html
<div id="mode-toggle">
  <button data-mode="simple">Simple</button>
  <button data-mode="advanced">Advanced</button>
</div>
```

**Visual states:**
- Active segment uses a filled pill: Simple → cobalt (`#1E5BFF`, white text); Advanced → ink (`#0A2540`, white text).
- Inactive segment is unstyled muted text on the pill container background.
- 120ms transition on the active pill (Pacekeeper fast timing, `cubic-bezier(.2,.8,.2,1)`).

**Behaviour:** Clicking either segment immediately toggles `body.mode-simple` / `body.mode-advanced`, updates the pill, and saves to `localStorage`.

---

## CSS Architecture

Two classes on `<html>` drive all visibility (applied to `<html>` not `<body>` so the flash-prevention script can set them before `<body>` renders):

```css
html.mode-simple   [data-mode="advanced"] { display: none; }
html.mode-advanced [data-mode="simple"]   { display: none; }
```

Section wrappers carry `data-mode="simple"` or `data-mode="advanced"`. Shared sections (header, KPI cards, P&L chart) carry no `data-mode` attribute and are always visible.

---

## Simple Mode Layout

Sections in order (top → bottom):

### 1. KPI Cards (shared, always visible — labels renamed)

| Old label | New label |
|---|---|
| Free Cash | Available Cash |
| Total Value | Portfolio Value |
| Overall PnL | Today's Gain / Loss |
| Open Positions | (unchanged) |
| Trades Today | (unchanged) |
| Signals Generated | Hidden in Simple mode — technical metric not relevant to non-technical users |

### 2. Status Cards (Simple only)

Three cards in a 3-column grid, each with a coloured background:

| Card | Background | Copy pattern |
|---|---|---|
| What is the bot doing? | Cobalt soft (`#E1EAFF`, border `#1E5BFF`) | "Watching markets · next check in N min" / "Bot is paused" |
| Is everything healthy? | Sage soft (`#DCEBE2`, border `#2C7A4B`) | "✓ All systems running · N positions open · $X cash" / error message if unhealthy |
| What happens next? | Neutral (`#F5F7FA`, border `#E3E8EF`) | "Market opens [day] [time] · bot will scan N stocks" / "Market is open · bot watching" |

Status card copy is derived from the existing `/api/status` response — no new endpoints.

### 3. P&L Chart (shared, always visible)

Unchanged. The chart renders the same in both modes.

### 4. My Investments (Simple only)

Replaces the Open Positions table. One row per position:
- **Left:** Ticker (bold) + company name (muted) + share count
- **Right:** P&L in dollars and percentage (sage if positive, crimson if negative) + "Sell" button
- Below the list: "Sell everything" button (crimson-soft, same behaviour as existing Close All)

Data source: existing `/api/positions` endpoint. No new columns (no avg price, no order type, no direction badge).

### 5. Recent Activity (Simple only)

Replaces the Signals table and Trade Log. A vertical list of plain-English activity entries, newest first, capped at 20 items.

**Entry format:**
- 🟢 + bold sentence + muted timestamp/context line → for BUY actions
- 🔴 + bold sentence + muted timestamp/context line → for SELL actions
- ⏸ + bold sentence + muted timestamp/context line → for HOLD signals

**Copy templates (derived from `/api/signals` and `/api/trades`):**
- BUY: "Bought N shares of {TICKER} · ${price} each" / "AI spotted strong upward momentum · {time}"
- SELL: "Sold {TICKER} · took profit" or "Sold {TICKER} · stop-loss triggered" / "{time}"
- HOLD: "Decided to hold {TICKER}" / "Market conditions uncertain right now · {time}"

Entry background uses sage-soft for buys, crimson-soft for sells, paper-2 for holds.

### Sections hidden in Simple mode

- Market Indicators grid
- Recent Signals table
- Trade Log table
- LLM Settings panel

---

## Advanced Mode Layout

Identical to the current dashboard. Zero changes to existing sections, JS, or CSS for Advanced mode. The `data-mode="advanced"` wrapper is added around existing sections purely for the toggle mechanism.

---

## JavaScript Changes

1. **Flash-prevention inline script** — at the very top of `<body>`, before any content:
   ```js
   (function() {
     var m = localStorage.getItem('pk_mode') || 'simple';
     document.documentElement.classList.add('mode-' + m);
   })();
   ```
   (Applied to `<html>` via `document.documentElement` so it fires before `<body>` renders. Uses `classList.add` rather than `className =` to avoid clobbering any other classes on `<html>`.)

2. **`setMode(mode)`** — saves to `localStorage`, updates `<html>` class, updates toggle pill state.

3. **`buildActivityStream(signals, trades)`** — merges and sorts `/api/signals` + `/api/trades` by timestamp descending, maps each to a human-readable entry object, renders up to 20 into `#activity-stream`.

4. **`refreshSimple()`** — called inside the existing `refresh()` function (guarded by current mode check) to update status cards, My Investments rows, and the activity stream.

5. **First-run modal logic** — on `DOMContentLoaded`, if `localStorage.getItem('pk_mode')` is null, show the modal. Card click selects it. "Get started" calls `setMode(selected)` and hides modal.

---

## File Size Note

Current `dashboard.html` is 1053 lines. This PR will add approximately 350 lines (CSS + HTML + JS), reaching ~1400 lines. Per CLAUDE.md guidelines this is at the upper limit. A follow-up issue should extract CSS to `static/dashboard.css` and JS to `static/dashboard.js` — this PR does not do that split to keep scope contained.

---

## Testing Checklist

- [ ] First visit (no `localStorage`): modal appears, Simple is pre-selected.
- [ ] Picking Advanced in modal: saves `"advanced"`, closes modal, Advanced view renders.
- [ ] Reload after Simple choice: no modal, Simple view renders with no flash.
- [ ] Header toggle Simple → Advanced: switches instantly, saves, persists on reload.
- [ ] Header toggle Advanced → Simple: switches instantly, saves, persists on reload.
- [ ] Status cards reflect live `/api/status` data (bot paused/running, market open/closed).
- [ ] My Investments shows correct P&L colours (sage positive, crimson negative).
- [ ] Sell button on investment row closes position (same as existing close endpoint).
- [ ] Sell everything closes all positions (same as existing close-all endpoint).
- [ ] Activity stream shows ≤ 20 entries, newest first, correct emoji/colour per action.
- [ ] Advanced mode: all existing sections visible and unchanged.
- [ ] Escape key / backdrop click on modal saves Simple mode.
