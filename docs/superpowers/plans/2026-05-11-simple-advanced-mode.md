# Simple / Advanced Dashboard Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Simple / Advanced mode toggle to `dashboard.html` so non-technical users land in a plain-English view by default, with a first-run modal and persistent header toggle to switch modes.

**Architecture:** Pure client-side, single HTML file. Mode is stored in `localStorage` (`pk_mode`: `"simple"` | `"advanced"`). CSS classes on `<html>` (`html.mode-simple` / `html.mode-advanced`) show/hide sections marked with `data-mode` attributes. No backend changes, no new API endpoints, no new files.

**Tech Stack:** Vanilla JS, CSS custom properties (Pacekeeper design tokens already in the file), `localStorage`, existing `/api/status` + `/api/positions` + `/api/signals` + `/api/trades` endpoints.

---

## File Structure

**One file modified only:**
- `src/dashboard/templates/dashboard.html` — all CSS, HTML, and JS changes go here

> No new files are created. Post-merge follow-up: extract CSS and JS to separate static files once the file exceeds 1400 lines.

---

## Task 1: Create feature branch

**Files:**
- No file changes — branch setup only

- [ ] **Step 1: Create and switch to feature branch**

```bash
git checkout -b feat/simple-advanced-mode
```

Expected: `Switched to a new branch 'feat/simple-advanced-mode'`

- [ ] **Step 2: Verify clean working tree**

```bash
git status
```

Expected: `nothing to commit, working tree clean`

---

## Task 2: Add CSS — mode visibility + toggle pill

**Files:**
- Modify: `src/dashboard/templates/dashboard.html` — append to existing `<style>` block (after line 451, before closing `</style>`)

- [ ] **Step 1: Add mode-visibility rules and all Simple-mode component styles**

Open `src/dashboard/templates/dashboard.html`. Find the closing `</style>` tag (line 452). Insert the following block immediately before it:

```css
    /* ── Mode visibility ── */
    html.mode-simple   [data-mode="advanced"] { display: none; }
    html.mode-advanced [data-mode="simple"]   { display: none; }

    /* ── Mode toggle pill ── */
    #mode-toggle {
      display: inline-flex;
      border: 1px solid var(--rule);
      border-radius: 20px;
      background: var(--paper-3);
      padding: 2px;
      gap: 0;
    }
    #mode-toggle button {
      font-size: 11px;
      font-weight: 600;
      font-family: var(--sans);
      padding: 4px 12px;
      border-radius: 16px;
      border: none;
      background: transparent;
      color: var(--ink-3);
      cursor: pointer;
      transition: background var(--t-fast) var(--ease-out), color var(--t-fast) var(--ease-out);
    }
    #mode-toggle button.active-simple  { background: var(--accent); color: var(--paper); }
    #mode-toggle button.active-advanced { background: var(--ink);   color: var(--paper); }

    /* ── Status cards ── */
    .status-cards {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
      margin-bottom: 24px;
    }
    .status-card { border-radius: var(--r-3); padding: 14px 16px; border: 1px solid; }
    .status-card-label {
      font-size: 10px; font-weight: 700; text-transform: uppercase;
      letter-spacing: 0.06em; margin-bottom: 6px; font-family: var(--mono);
    }
    .status-card-value { font-weight: 600; font-size: 13px; color: var(--ink); }
    .status-card-sub   { font-size: 11px; color: var(--ink-2); margin-top: 3px; }
    .status-card.card-bot  { background: var(--accent-soft); border-color: var(--accent); }
    .status-card.card-bot  .status-card-label { color: var(--accent); }
    .status-card.card-health { background: var(--sage-soft); border-color: var(--sage); }
    .status-card.card-health .status-card-label { color: var(--sage); }
    .status-card.card-next { background: var(--paper-2); border-color: var(--rule); }
    .status-card.card-next .status-card-label { color: var(--ink-3); }

    /* ── My Investments ── */
    .investment-row {
      display: flex; justify-content: space-between; align-items: center;
      padding: 10px 12px;
      background: var(--paper-2); border: 1px solid var(--rule);
      border-radius: var(--r-2); margin-bottom: 6px;
    }
    .investment-ticker { font-weight: 700; color: var(--ink); }
    .investment-meta   { font-size: 11px; color: var(--ink-3); margin-left: 8px; }
    .investment-pnl    { font-weight: 600; font-family: var(--mono); font-variant-numeric: tabular-nums; }
    .investment-actions { display: flex; align-items: center; gap: 10px; }
    .sell-btn {
      font-size: 11px; background: var(--paper); border: 1px solid var(--rule-2);
      border-radius: var(--r-1); padding: 3px 10px; cursor: pointer;
      font-weight: 500; font-family: var(--sans);
      transition: background var(--t-fast) var(--ease-out);
    }
    .sell-btn:hover { background: var(--paper-3); }
    .investments-footer { text-align: right; margin-top: 6px; }
    .sell-all-btn {
      font-size: 11px; background: var(--crimson-soft); border: 1px solid var(--crimson);
      color: var(--crimson); border-radius: var(--r-1); padding: 4px 12px;
      cursor: pointer; font-weight: 600; font-family: var(--sans);
    }

    /* ── Recent Activity ── */
    .activity-list { display: flex; flex-direction: column; gap: 8px; }
    .activity-entry {
      display: flex; gap: 10px; align-items: flex-start;
      padding: 10px 12px; border-radius: var(--r-2); border: 1px solid;
    }
    .activity-entry.buy  { background: var(--sage-soft);    border-color: var(--sage); }
    .activity-entry.sell { background: var(--crimson-soft); border-color: var(--crimson); }
    .activity-entry.hold { background: var(--paper-2);      border-color: var(--rule); }
    .activity-emoji { font-size: 16px; flex-shrink: 0; line-height: 1.4; }
    .activity-title { font-weight: 600; color: var(--ink); font-size: 13px; }
    .activity-sub   { font-size: 11px; color: var(--ink-3); margin-top: 2px; }

    /* ── First-run modal ── */
    #mode-modal-backdrop {
      position: fixed; inset: 0;
      background: rgba(10,37,64,0.45);
      z-index: 100;
      display: flex; align-items: center; justify-content: center;
    }
    #mode-modal {
      background: var(--paper); border-radius: 10px; padding: 28px 32px;
      max-width: 440px; width: calc(100% - 48px);
      box-shadow: 0 8px 32px rgba(10,37,64,0.18);
    }
    #mode-modal h2 {
      font-size: 18px; font-weight: 700; color: var(--ink); margin-bottom: 6px;
      border: none; padding: 0; text-transform: none; letter-spacing: normal;
      font-family: var(--sans);
    }
    #mode-modal p { font-size: 13px; color: var(--ink-3); margin-bottom: 20px; line-height: 1.5; }
    .modal-cards { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px; }
    .modal-card {
      border: 2px solid var(--rule); border-radius: var(--r-3); padding: 16px;
      cursor: pointer; background: var(--paper-2);
      transition: border-color var(--t-fast) var(--ease-out), background var(--t-fast) var(--ease-out);
    }
    .modal-card.selected { border-color: var(--accent); background: var(--accent-soft); }
    .modal-card-icon  { font-size: 22px; margin-bottom: 6px; }
    .modal-card-title { font-weight: 700; color: var(--ink); margin-bottom: 4px; font-size: 14px; }
    .modal-card-desc  { font-size: 12px; color: var(--ink-3); line-height: 1.4; }
    .modal-badge {
      display: inline-block; margin-top: 8px; font-size: 10px;
      background: var(--accent); color: var(--paper);
      padding: 2px 8px; border-radius: 10px; font-weight: 600;
    }
    #modal-cta {
      width: 100%; background: var(--accent); color: var(--paper); border: none;
      border-radius: var(--r-2); padding: 11px; font-size: 14px; font-weight: 600;
      cursor: pointer; font-family: var(--sans);
      transition: opacity var(--t-fast) var(--ease-out);
    }
    #modal-cta:hover { opacity: 0.88; }
```

- [ ] **Step 2: Commit**

```bash
git add src/dashboard/templates/dashboard.html
git commit -m "feat(dashboard): add CSS for Simple/Advanced mode system"
```

---

## Task 3: Flash-prevention script + setMode() JS

**Files:**
- Modify: `src/dashboard/templates/dashboard.html`

- [ ] **Step 1: Add flash-prevention inline script**

Find the `<body>` opening tag (line 454). Immediately after `<body>`, insert:

```html
<script>
  (function() {
    var m = localStorage.getItem('pk_mode') || 'simple';
    document.documentElement.classList.add('mode-' + m);
  })();
</script>
```

This runs synchronously before any content renders, preventing a flash of the wrong mode.

- [ ] **Step 2: Add setMode() and initModeToggle() to the JS section**

Find the existing JS block (starts with `const fmt = ...`). Add the following at the very top of that `<script>` block, before `const fmt`:

```javascript
  // ── Mode management ──────────────────────────────────────────────────────────
  function setMode(m) {
    localStorage.setItem('pk_mode', m);
    document.documentElement.classList.remove('mode-simple', 'mode-advanced');
    document.documentElement.classList.add('mode-' + m);
    document.getElementById('mode-btn-simple').classList.toggle('active-simple', m === 'simple');
    document.getElementById('mode-btn-advanced').classList.toggle('active-advanced', m === 'advanced');
  }

  function initModeToggle() {
    const m = localStorage.getItem('pk_mode') || 'simple';
    document.getElementById('mode-btn-simple').classList.toggle('active-simple', m === 'simple');
    document.getElementById('mode-btn-advanced').classList.toggle('active-advanced', m === 'advanced');
  }

```

- [ ] **Step 3: Commit**

```bash
git add src/dashboard/templates/dashboard.html
git commit -m "feat(dashboard): add flash-prevention script and setMode() JS"
```

---

## Task 4: Header toggle HTML

**Files:**
- Modify: `src/dashboard/templates/dashboard.html` — header section

- [ ] **Step 1: Insert mode toggle into header**

Find this line in the header (around line 461):

```html
    <span class="status-dot" id="status-dot"></span>
```

Insert the toggle div immediately before it:

```html
    <div id="mode-toggle">
      <button id="mode-btn-simple" onclick="setMode('simple')">Simple</button>
      <button id="mode-btn-advanced" onclick="setMode('advanced')">Advanced</button>
    </div>
```

- [ ] **Step 2: Commit**

```bash
git add src/dashboard/templates/dashboard.html
git commit -m "feat(dashboard): add mode toggle pill to header"
```

---

## Task 5: Wrap existing Advanced-only sections + rename KPI labels

**Files:**
- Modify: `src/dashboard/templates/dashboard.html` — main content area

- [ ] **Step 1: Rename KPI card labels**

Find the three KPI card `<div class="label">` elements and update their text:

| Find | Replace with |
|------|--------------|
| `<div class="label">Free Cash</div>` | `<div class="label">Available Cash</div>` |
| `<div class="label">Total Value</div>` | `<div class="label">Portfolio Value</div>` |
| `<div class="label">Overall PnL</div>` | `<div class="label">Today's Gain / Loss</div>` |

- [ ] **Step 2: Hide "Signals Generated" KPI in Simple mode**

Find the Signals Generated card:

```html
      <div class="card">
        <div class="label">Signals Generated</div>
        <div class="value" id="kpi-signals">—</div>
      </div>
```

Wrap it:

```html
      <div data-mode="advanced">
        <div class="card">
          <div class="label">Signals Generated</div>
          <div class="value" id="kpi-signals">—</div>
        </div>
      </div>
```

- [ ] **Step 3: Wrap LLM Settings panel**

Find the line `    <div class="llm-panel">`. Add `    <div data-mode="advanced">` on the line immediately before it. Then find the matching closing `</div>` (the one that closes `llm-panel`) and add `    </div>` on the line immediately after it. Do not change any content inside `llm-panel`.

- [ ] **Step 4: Wrap Market Indicators section**

Find the `<div class="section">` that contains `<h2>Market Indicators</h2>`. Add `    <div data-mode="advanced">` on the line immediately before that `<div class="section">`. Then find the matching `</div>` that closes that section and add `    </div>` immediately after it. Do not change any content inside the section.

- [ ] **Step 5: Wrap Open Positions section**

Find the `<div class="section">` that contains `<h2>Open Positions</h2>` (it has a flex sub-div containing the heading and the Close All button). Add `    <div data-mode="advanced">` on the line immediately before that `<div class="section">`. Add `    </div>` on the line immediately after the section's closing `</div>`. Do not change any content inside the section.

- [ ] **Step 6: Wrap Recent Signals section**

Find the `<div class="section">` that contains `<h2>Recent Signals</h2>`. Add `    <div data-mode="advanced">` immediately before it and `    </div>` immediately after its closing `</div>`. Do not change any content inside.

- [ ] **Step 7: Wrap Trade Log section**

Find the `<div class="section">` that contains `<h2>Trade Log</h2>`. Add `    <div data-mode="advanced">` immediately before it and `    </div>` immediately after its closing `</div>`. Do not change any content inside.

- [ ] **Step 8: Commit**

```bash
git add src/dashboard/templates/dashboard.html
git commit -m "feat(dashboard): wrap advanced sections with data-mode attribute, rename KPI labels"
```

---

## Task 6: First-run modal HTML + JS

**Files:**
- Modify: `src/dashboard/templates/dashboard.html`

- [ ] **Step 1: Add modal HTML**

Find the opening `<main>` tag. Insert the modal immediately before it (between `</header>` and `<main>`):

```html
  <div id="mode-modal-backdrop" style="display:none" onclick="handleBackdropClick(event)">
    <div id="mode-modal">
      <h2>Welcome to Pacekeeper</h2>
      <p>How would you like to see your dashboard? You can change this any time from the header.</p>
      <div class="modal-cards">
        <div class="modal-card selected" data-mode="simple" onclick="selectModalCard(this)">
          <div class="modal-card-icon">🟢</div>
          <div class="modal-card-title">Simple view</div>
          <div class="modal-card-desc">Plain-English status, your investments at a glance, and easy controls. No jargon.</div>
          <span class="modal-badge">Default · Recommended</span>
        </div>
        <div class="modal-card" data-mode="advanced" onclick="selectModalCard(this)">
          <div class="modal-card-icon">📊</div>
          <div class="modal-card-title">Advanced view</div>
          <div class="modal-card-desc">Full indicators, signal tables, trade log, and all technical data.</div>
        </div>
      </div>
      <button id="modal-cta" onclick="dismissModal()">Get started</button>
    </div>
  </div>
```

- [ ] **Step 2: Add modal JS**

In the JS `<script>` block, add the following after `initModeToggle()`:

```javascript
  // ── First-run modal ───────────────────────────────────────────────────────────
  let _modalMode = 'simple';

  function selectModalCard(el) {
    document.querySelectorAll('.modal-card').forEach(c => c.classList.remove('selected'));
    el.classList.add('selected');
    _modalMode = el.dataset.mode;
  }

  function dismissModal() {
    setMode(_modalMode);
    document.getElementById('mode-modal-backdrop').style.display = 'none';
  }

  function handleBackdropClick(e) {
    if (e.target === document.getElementById('mode-modal-backdrop')) dismissModal();
  }

  function initModal() {
    if (!localStorage.getItem('pk_mode')) {
      document.getElementById('mode-modal-backdrop').style.display = 'flex';
    }
    document.addEventListener('keydown', function(e) {
      const backdrop = document.getElementById('mode-modal-backdrop');
      if (e.key === 'Escape' && backdrop.style.display !== 'none') dismissModal();
    });
  }

```

- [ ] **Step 3: Commit**

```bash
git add src/dashboard/templates/dashboard.html
git commit -m "feat(dashboard): add first-run mode-selection modal"
```

---

## Task 7: Simple-mode HTML sections

**Files:**
- Modify: `src/dashboard/templates/dashboard.html` — inside `<main>`, before the P&L chart

- [ ] **Step 1: Add status cards + My Investments + Recent Activity HTML**

Inside `<main>`, after the KPI `.grid` div and before the existing LLM panel (which is now wrapped in `data-mode="advanced"`), insert:

```html
    <!-- Simple: Status cards -->
    <div data-mode="simple">
      <div class="status-cards">
        <div class="status-card card-bot">
          <div class="status-card-label">What is the bot doing?</div>
          <div class="status-card-value" id="sc-bot-value">—</div>
          <div class="status-card-sub" id="sc-bot-sub"></div>
        </div>
        <div class="status-card card-health">
          <div class="status-card-label">Is everything healthy?</div>
          <div class="status-card-value" id="sc-health-value">—</div>
          <div class="status-card-sub" id="sc-health-sub"></div>
        </div>
        <div class="status-card card-next">
          <div class="status-card-label">What happens next?</div>
          <div class="status-card-value" id="sc-next-value">—</div>
          <div class="status-card-sub" id="sc-next-sub"></div>
        </div>
      </div>
    </div>
```

After the P&L chart (`.chart-wrap`) and before the Market Indicators section (which is now wrapped in `data-mode="advanced"`), insert:

```html
    <!-- Simple: My Investments -->
    <div data-mode="simple" class="section">
      <h2>My Investments</h2>
      <div id="investments-body">
        <div style="color:var(--muted);text-align:center;font-size:13px">Loading…</div>
      </div>
      <div class="investments-footer">
        <button class="sell-all-btn" onclick="closeAllPositions()">Sell everything</button>
      </div>
    </div>

    <!-- Simple: Recent Activity -->
    <div data-mode="simple" class="section">
      <h2>Recent Activity</h2>
      <div class="activity-list" id="activity-list">
        <div style="color:var(--muted);font-size:13px">Loading…</div>
      </div>
    </div>
```

- [ ] **Step 2: Commit**

```bash
git add src/dashboard/templates/dashboard.html
git commit -m "feat(dashboard): add Simple-mode HTML scaffolds (status cards, investments, activity)"
```

---

## Task 8: refreshStatusCards() JS

**Files:**
- Modify: `src/dashboard/templates/dashboard.html` — JS section

- [ ] **Step 1: Add refreshStatusCards() function**

Find the existing `refreshStatus()` function. After it, insert:

```javascript
  function refreshStatusCards(s) {
    // What is the bot doing?
    const botVal = document.getElementById('sc-bot-value');
    const botSub = document.getElementById('sc-bot-sub');
    if (!s.enabled) {
      botVal.textContent = 'Bot is paused';
      botSub.textContent = 'Click "Resume Bot" to restart';
    } else {
      botVal.textContent = 'Watching markets';
      if (s.next_run) {
        const secsUntil = Math.max(0, Math.round((new Date(s.next_run) - Date.now()) / 1000));
        botSub.textContent = secsUntil < 60
          ? 'Next check in under a minute'
          : `Next check in ${Math.ceil(secsUntil / 60)} min`;
      } else {
        botSub.textContent = '';
      }
    }

    // Is everything healthy?
    const healthVal = document.getElementById('sc-health-value');
    const healthSub = document.getElementById('sc-health-sub');
    healthVal.textContent = '✓ All systems running';
    const posCount = s.open_positions ?? 0;
    healthSub.textContent = `${posCount} position${posCount !== 1 ? 's' : ''} open`;

    // What happens next?
    const nextVal = document.getElementById('sc-next-value');
    const nextSub = document.getElementById('sc-next-sub');
    if (s.market_open) {
      nextVal.textContent = 'Market is open';
      nextSub.textContent = 'Bot is watching for opportunities';
    } else if (s.next_market_open) {
      const d = new Date(s.next_market_open);
      const day = d.toLocaleDateString([], { weekday: 'short' });
      const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      nextVal.textContent = `Market opens ${day} ${time}`;
      nextSub.textContent = 'Bot will scan your watchlist';
    } else {
      nextVal.textContent = 'Market closed';
      nextSub.textContent = '';
    }
  }
```

- [ ] **Step 2: Call refreshStatusCards() from refreshStatus()**

Inside `refreshStatus()`, at the very end of the `try` block (after the `next-open-label` update), add:

```javascript
      refreshStatusCards(s);
```

- [ ] **Step 3: Commit**

```bash
git add src/dashboard/templates/dashboard.html
git commit -m "feat(dashboard): add refreshStatusCards() wired into refreshStatus()"
```

---

## Task 9: refreshInvestments() JS

**Files:**
- Modify: `src/dashboard/templates/dashboard.html` — JS section

- [ ] **Step 1: Add refreshInvestments() function**

After `refreshPositions()`, insert:

```javascript
  // ── Simple: My Investments ────────────────────────────────────────────────────
  async function refreshInvestments() {
    try {
      const raw = await fetchJSON('/api/positions');
      const data = (raw || []).filter(p => Math.abs(Number(p.quantity || 0)) > 1e-6);
      const body = document.getElementById('investments-body');
      if (!data.length) {
        body.innerHTML = '<p style="color:var(--ink-3);font-size:13px;text-align:center">No open positions</p>';
        return;
      }
      body.innerHTML = data.map(p => {
        const pnlPct = p.averagePrice
          ? ((p.currentPrice - p.averagePrice) / p.averagePrice * 100)
          : 0;
        const pnlSign = p.ppl >= 0 ? '+' : '';
        const pnlPctSign = pnlPct >= 0 ? '+' : '';
        const pnlCls = p.ppl >= 0 ? 'positive' : 'negative';
        const qty = Math.abs(p.quantity);
        const fmtQty = qty % 1 < 1e-6 ? String(Math.round(qty)) : fmt(qty, 4);
        const ticker = p.ticker.split('_')[0];
        return `<div class="investment-row">
          <div>
            <span class="investment-ticker">${ticker}</span>
            <span class="investment-meta">${fmtQty} share${qty !== 1 ? 's' : ''}</span>
          </div>
          <div class="investment-actions">
            <span class="investment-pnl ${pnlCls}">${pnlSign}$${fmt(p.ppl)} <span style="font-size:11px">(${pnlPctSign}${fmt(pnlPct, 2)}%)</span></span>
            <button class="sell-btn" onclick="closePosition('${p.ticker}')">Sell</button>
          </div>
        </div>`;
      }).join('');
    } catch(e) { console.warn('investments fetch failed', e); }
  }
```

- [ ] **Step 2: Commit**

```bash
git add src/dashboard/templates/dashboard.html
git commit -m "feat(dashboard): add refreshInvestments() for Simple mode positions view"
```

---

## Task 10: buildActivityStream() + refreshActivity() JS

**Files:**
- Modify: `src/dashboard/templates/dashboard.html` — JS section

- [ ] **Step 1: Add buildActivityStream() and refreshActivity()**

After `refreshInvestments()`, insert:

```javascript
  // ── Simple: Recent Activity ───────────────────────────────────────────────────
  function buildActivityStream(signals, trades) {
    const entries = [];

    for (const t of trades) {
      const action = (t.action || '').toUpperCase();
      const ticker = (t.ticker || '').split('_')[0];
      const qty = Math.abs(t.quantity || 0);
      const fmtQty = qty % 1 < 1e-6 ? String(Math.round(qty)) : fmt(qty, 4);
      const reason = (t.reason || '').toLowerCase();
      const isTP = reason.includes('profit') || reason.includes('target') || reason.includes('take');
      const isSL = reason.includes('stop') || reason.includes('loss');

      if (action === 'BUY') {
        entries.push({
          ts: t.timestamp,
          emoji: '🟢', cls: 'buy',
          title: `Bought ${fmtQty} share${qty !== 1 ? 's' : ''} of ${ticker}`,
          sub: 'AI spotted a buying opportunity',
        });
      } else {
        entries.push({
          ts: t.timestamp,
          emoji: '🔴', cls: 'sell',
          title: `Sold ${ticker}`,
          sub: isTP ? 'Took profit' : isSL ? 'Stop-loss triggered' : t.reason || 'Sold position',
        });
      }
    }

    for (const s of signals) {
      if ((s.action || '').toUpperCase() === 'HOLD') {
        const ticker = (s.ticker || '').split('_')[0];
        const reasoning = s.reasoning ? s.reasoning.slice(0, 80) : 'Market conditions uncertain';
        entries.push({
          ts: s.timestamp,
          emoji: '⏸', cls: 'hold',
          title: `Decided to hold ${ticker}`,
          sub: reasoning,
        });
      }
    }

    entries.sort((a, b) => new Date(b.ts) - new Date(a.ts));
    return entries.slice(0, 20);
  }

  async function refreshActivity() {
    try {
      const [signals, trades] = await Promise.all([
        fetchJSON('/api/signals'),
        fetchJSON('/api/trades'),
      ]);
      const entries = buildActivityStream(signals || [], trades || []);
      const list = document.getElementById('activity-list');
      if (!entries.length) {
        list.innerHTML = '<div style="color:var(--ink-3);font-size:13px">No activity yet — waiting for first trading cycle</div>';
        return;
      }
      list.innerHTML = entries.map(e => `
        <div class="activity-entry ${e.cls}">
          <span class="activity-emoji">${e.emoji}</span>
          <div>
            <div class="activity-title">${e.title}</div>
            <div class="activity-sub">${e.sub} · ${fmtTime(e.ts)}</div>
          </div>
        </div>
      `).join('');
    } catch(e) { console.warn('activity fetch failed', e); }
  }
```

- [ ] **Step 2: Commit**

```bash
git add src/dashboard/templates/dashboard.html
git commit -m "feat(dashboard): add buildActivityStream() and refreshActivity() for Simple mode"
```

---

## Task 11: Wire refresh() with mode-guarded calls + init

**Files:**
- Modify: `src/dashboard/templates/dashboard.html` — JS section

- [ ] **Step 1: Replace refresh() with mode-aware version**

Find the existing `refresh()` function:

```javascript
  async function refresh() {
    await Promise.allSettled([
      refreshAccount(),
      refreshStatus(),
      refreshPnlChart(),
      refreshIndicators(),
      refreshPositions(),
      refreshSignals(),
      refreshTrades(),
    ]);
    document.getElementById('last-update').textContent = new Date().toLocaleTimeString();
  }
```

Replace it with:

```javascript
  async function refresh() {
    const mode = localStorage.getItem('pk_mode') || 'simple';
    const shared = [refreshAccount(), refreshStatus(), refreshPnlChart()];
    const modeSpecific = mode === 'simple'
      ? [refreshInvestments(), refreshActivity()]
      : [refreshIndicators(), refreshPositions(), refreshSignals(), refreshTrades()];
    await Promise.allSettled([...shared, ...modeSpecific]);
    document.getElementById('last-update').textContent = new Date().toLocaleTimeString();
  }
```

- [ ] **Step 2: Add initModeToggle() and initModal() to the init block**

Find the existing init block at the bottom of the script:

```javascript
  refresh();
  setInterval(refresh, 15000);
  connectSSE();
```

Replace with:

```javascript
  initModeToggle();
  initModal();
  refresh();
  setInterval(refresh, 15000);
  connectSSE();
```

- [ ] **Step 3: Commit**

```bash
git add src/dashboard/templates/dashboard.html
git commit -m "feat(dashboard): wire mode-aware refresh() and init calls"
```

---

## Task 12: Manual verification

> No JS test infrastructure exists in this project. Verification is done by running the server and checking the acceptance criteria manually.

**Files:**
- No file changes

- [ ] **Step 1: Start the server**

```bash
.venv/bin/python main.py
```

Expected: `Uvicorn running on http://0.0.0.0:4000`

- [ ] **Step 2: First-visit modal**

Open a private/incognito browser window to `http://localhost:4000`.
- Modal appears with "Welcome to Pacekeeper"
- "Simple view" card is pre-selected (blue border + blue background)
- Clicking "Advanced view" card deselects Simple, selects Advanced
- Pressing Escape closes the modal (saves Simple as default)
- After closing, modal does not reappear on refresh

- [ ] **Step 3: Simple mode layout**

Verify the following are visible in Simple mode:
- KPI labels read "Available Cash", "Portfolio Value", "Today's Gain / Loss"
- Three status cards show (What is the bot doing / Is everything healthy / What happens next)
- P&L chart is visible
- "My Investments" section is visible
- "Recent Activity" section is visible

Verify the following are hidden:
- "Signals Generated" KPI card
- LLM Settings panel
- Market Indicators grid
- Open Positions table
- Recent Signals table
- Trade Log table

- [ ] **Step 4: Header toggle**

- Click "Advanced" in the header toggle → Advanced view renders, all hidden sections appear, Simple sections disappear
- Click "Simple" → Simple view restores
- Reload page → mode persists

- [ ] **Step 5: Status cards show live data**

With bot running: "What is the bot doing?" shows "Watching markets · Next check in N min"
With bot paused: shows "Bot is paused · Click 'Resume Bot' to restart"
When market closed: "What happens next?" shows the next market open day/time

- [ ] **Step 6: My Investments sell buttons**

If positions exist: click "Sell" on one → confirm dialog → position closes (calls existing `/api/positions/{ticker}/close` endpoint)
"Sell everything" → calls existing `closeAllPositions()` flow

- [ ] **Step 7: Advanced mode unchanged**

Switch to Advanced mode and verify all existing sections work identically to before this PR.

---

## Task 13: Open Pull Request

**Files:**
- No file changes

- [ ] **Step 1: Push branch**

```bash
git push -u origin feat/simple-advanced-mode
```

- [ ] **Step 2: Create PR linked to issue #84**

```bash
gh pr create \
  --title "feat: Simple/Advanced dashboard mode (closes #84)" \
  --body "$(cat <<'EOF'
## Summary
- Adds a Simple / Advanced mode toggle to the dashboard (pure client-side, `localStorage`-backed)
- First-run modal greets new users and defaults them to Simple view
- Simple view shows 3 status cards (What is the bot doing / healthy / next), My Investments list, and a plain-English Recent Activity stream
- Advanced view is the existing dashboard — zero functional changes
- Header pill toggle lets users switch modes at any time

## Design spec
[`docs/superpowers/specs/2026-05-11-beginner-advanced-mode-design.md`](docs/superpowers/specs/2026-05-11-beginner-advanced-mode-design.md)

## Test plan
- [ ] First visit (no localStorage): modal appears, Simple pre-selected
- [ ] Picking Advanced in modal: saves, closes, Advanced view renders
- [ ] Reload after Simple choice: no modal, Simple view renders with no flash
- [ ] Header toggle Simple ↔ Advanced: switches instantly, persists on reload
- [ ] Status cards reflect live `/api/status` (bot paused/running, market open/closed)
- [ ] My Investments shows correct P&L colours (sage positive, crimson negative)
- [ ] Sell / Sell everything buttons call existing position-close endpoints
- [ ] Activity stream shows ≤ 20 entries newest-first, correct emoji/colour
- [ ] Advanced mode: all existing sections visible and unchanged

Closes #84

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Verify PR URL is printed** and share it.
