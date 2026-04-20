# Dashboard Load Performance Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the prediction-bot dashboard HTML render in <300ms by removing SQLite calls from the `GET /` route and loading trades asynchronously after paint.

**Architecture:** `GET /` serves HTML immediately from `engine.status` (in-memory PMBotStatus). JS fetches `/api/trades` and `/api/trades/open` after `DOMContentLoaded` to populate the trades table and "if all win" card. SSE is deferred to `DOMContentLoaded` so it never blocks initial paint.

**Tech Stack:** FastAPI, Jinja2, aiosqlite, vanilla JS (EventSource, fetch)

---

## File Map

| File | Change |
|------|--------|
| `prediction_bot/src/dashboard/app.py` | Remove two `await` calls from `dashboard()`, drop `stats`/`trades` from template context |
| `prediction_bot/src/dashboard/templates/dashboard.html` | Use `status.*` for stat cards, async-load trades table and "if all win", defer SSE |

---

### Task 1: Remove SQLite calls from `GET /` route

**Files:**
- Modify: `prediction_bot/src/dashboard/app.py:110-124`

- [ ] **Step 1: Replace the `dashboard()` function**

Open `prediction_bot/src/dashboard/app.py`. Replace lines 110–124 with:

```python
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "status": engine.status,
            "interval_seconds": engine.settings.SCAN_INTERVAL_SECONDS,
        },
    )
```

The two removed lines were:
```python
stats = await engine.paper_trader.store.get_stats()
trades = await engine.paper_trader.store.get_recent_trades(limit=50)
```

- [ ] **Step 2: Verify the server starts without errors**

```bash
cd /Users/pkhaninejad/Desktop/apps/Claude-trade-bot
.venv/bin/python -c "from prediction_bot.src.dashboard.app import app; print('OK')"
```

Expected output: `OK`

- [ ] **Step 3: Commit**

```bash
git add prediction_bot/src/dashboard/app.py
git commit -m "fix(prediction-bot): remove SQLite awaits from GET / route

Serves dashboard from engine.status (in-memory) instead of hitting
aiosqlite on every page load. Fixes unresponsive refresh (issue #72).

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 2: Update Jinja template stat cards to use `status.*`

**Files:**
- Modify: `prediction_bot/src/dashboard/templates/dashboard.html:37-55`

The template currently references `stats.bankroll`, `stats.total_pnl`, `stats.win_rate`, `stats.won`, `stats.lost`, `stats.expired`, `stats.open_trades`. These must change to `status.*` fields. Note: `PMBotStatus` does not have `won`/`lost`/`expired` counts — those sub-counts are dropped (the win rate is still shown, just without the W/L/E breakdown).

- [ ] **Step 1: Replace the stats card block**

Replace lines 37–55 (the five stat cards: BANKROLL, TOTAL P&L, WIN RATE, OPEN TRADES, STATUS) with:

```html
  <div class="card">
    <div class="label">BANKROLL</div>
    <div class="value neutral" id="bankroll">${{ "%.2f"|format(status.bankroll) }}</div>
  </div>
  <div class="card">
    <div class="label">TOTAL P&amp;L</div>
    <div class="value {% if status.total_pnl >= 0 %}positive{% else %}negative{% endif %}" id="pnl">
      {% if status.total_pnl >= 0 %}+{% endif %}${{ "%.2f"|format(status.total_pnl) }}
    </div>
  </div>
  <div class="card">
    <div class="label">WIN RATE</div>
    <div class="value" id="winrate">
      {% if status.win_rate is not none %}{{ "%.1f"|format(status.win_rate * 100) }}%{% else %}&mdash;{% endif %}
    </div>
  </div>
  <div class="card">
    <div class="label">OPEN TRADES</div>
    <div class="value neutral" id="open-trades">{{ status.open_trades }}</div>
  </div>
  <div class="card">
    <div class="label">STATUS</div>
    <div class="value" id="bot-status">{{ "ON" if status.enabled else "OFF" }}</div>
    <button class="toggle-btn" onclick="toggleBot()">Toggle</button>
  </div>
```

- [ ] **Step 2: Replace the "If All Win" card**

The old card (lines 75–82) used server-side `trades` loop. Replace it with a card that shows `—` initially and is populated by JS:

```html
  <div class="card">
    <div class="label">IF ALL WIN</div>
    <div class="value positive" id="if-all-win">—</div>
    <div style="font-size:0.7em;color:#8b949e;margin-top:4px">open trades only</div>
  </div>
```

Also remove the Jinja namespace block that preceded it (the `{% set total_if_win = namespace(value=0) %}` and `{% for t in trades %}...{% endfor %}` lines).

- [ ] **Step 3: Commit**

```bash
git add prediction_bot/src/dashboard/templates/dashboard.html
git commit -m "fix(prediction-bot): render stat cards from engine.status (in-memory)

Removes server-side trades loop and stats.* references. Cards now render
instantly from PMBotStatus fields. If-All-Win shows placeholder until
async JS fetch populates it.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Make trades table load asynchronously

**Files:**
- Modify: `prediction_bot/src/dashboard/templates/dashboard.html` — trades `<tbody>` and JS

- [ ] **Step 1: Replace trades `<tbody>` with loading placeholder**

Find the `<tbody>` inside the "Recent Trades" section (the `{% for t in trades %}...{% endfor %}` block) and replace the entire `<tbody>...</tbody>` with:

```html
    <tbody id="trades-tbody">
      <tr><td colspan="11" style="color:#8b949e;text-align:center">Loading…</td></tr>
    </tbody>
```

- [ ] **Step 2: Add `fetchTrades()` JS function**

In the `<script>` block, add this function before the existing `toggleBot()`:

```javascript
async function fetchTrades() {
  try {
    const resp = await fetch('/api/trades?limit=50');
    const trades = await resp.json();
    const tbody = document.getElementById('trades-tbody');
    if (!trades.length) {
      tbody.innerHTML = '<tr><td colspan="11" style="color:#8b949e;text-align:center">No trades yet</td></tr>';
      return;
    }
    tbody.innerHTML = trades.map(t => {
      const ifWin = (1.0 - t.entry_price) * t.quantity;
      const pnlStr = t.pnl != null
        ? `<span class="${t.pnl > 0 ? 'positive' : t.pnl < 0 ? 'negative' : ''}">${t.pnl > 0 ? '+' : ''}$${t.pnl.toFixed(2)}</span>`
        : '&mdash;';
      const dt = new Date(t.created_at);
      const dateStr = `${String(dt.getMonth()+1).padStart(2,'0')}/${String(dt.getDate()).padStart(2,'0')} ${String(dt.getHours()).padStart(2,'0')}:${String(dt.getMinutes()).padStart(2,'0')}`;
      const q = t.market_question.length > 55 ? t.market_question.slice(0,55) + '…' : t.market_question;
      const statusClass = t.status.toLowerCase();
      return `<tr>
        <td>${dateStr}</td>
        <td title="${t.market_question}">${q}</td>
        <td>${t.platform}</td>
        <td>${t.side}</td>
        <td>$${t.entry_price.toFixed(2)}</td>
        <td>${Math.round(t.quantity)}</td>
        <td>$${t.cost.toFixed(2)}</td>
        <td class="positive">+$${ifWin.toFixed(2)}</td>
        <td><span class="badge badge-${statusClass}">${t.status}</span></td>
        <td>${pnlStr}</td>
        <td>${t.category}</td>
      </tr>`;
    }).join('');
  } catch {
    document.getElementById('trades-tbody').innerHTML =
      '<tr><td colspan="11" style="color:#f85149;text-align:center">Error loading trades</td></tr>';
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add prediction_bot/src/dashboard/templates/dashboard.html
git commit -m "fix(prediction-bot): load trades table asynchronously after paint

Replaces server-side trades rendering with async JS fetch. Initial HTML
renders with Loading placeholder; table populates after DOMContentLoaded.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 4: Add `fetchIfAllWin()` and defer SSE + status fetch to `DOMContentLoaded`

**Files:**
- Modify: `prediction_bot/src/dashboard/templates/dashboard.html` — `<script>` block

- [ ] **Step 1: Add `fetchIfAllWin()` JS function**

In the `<script>` block, add after `fetchTrades()`:

```javascript
async function fetchIfAllWin() {
  try {
    const resp = await fetch('/api/trades/open');
    const trades = await resp.json();
    const total = trades.reduce((sum, t) => sum + (1.0 - t.entry_price) * t.quantity, 0);
    document.getElementById('if-all-win').textContent = '+$' + total.toFixed(2);
  } catch {
    // leave as —
  }
}
```

- [ ] **Step 2: Replace top-level SSE and status fetch with `DOMContentLoaded` block**

The current script has `const es = new EventSource('/api/stream');` and `fetch('/api/status')...` at the top level. Remove those and the `setInterval` countdown block. Replace them with a single `DOMContentLoaded` listener that wires everything up:

```javascript
document.addEventListener('DOMContentLoaded', () => {
  fetchTrades();
  fetchIfAllWin();

  fetch('/api/status').then(r => r.json()).then(s => {
    if (s.next_scan) nextScanAt = new Date(s.next_scan);
  });

  const es = new EventSource('/api/stream');
  es.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.type === 'cycle_complete') {
      const s = data.status;
      document.getElementById('bankroll').textContent = '$' + s.bankroll.toFixed(2);
      const pnlEl = document.getElementById('pnl');
      pnlEl.textContent = (s.total_pnl >= 0 ? '+' : '') + '$' + s.total_pnl.toFixed(2);
      pnlEl.className = 'value ' + (s.total_pnl >= 0 ? 'positive' : 'negative');
      document.getElementById('open-trades').textContent = s.open_trades;
      if (s.win_rate !== null) {
        document.getElementById('winrate').textContent = (s.win_rate * 100).toFixed(1) + '%';
      }
      if (s.next_scan) nextScanAt = new Date(s.next_scan);
      fetchTrades();
      fetchIfAllWin();
    }
  };

  setInterval(() => {
    if (!nextScanAt) return;
    const secs = Math.max(0, Math.round((nextScanAt - Date.now()) / 1000));
    const m = Math.floor(secs / 60), s = secs % 60;
    document.getElementById('countdown').textContent =
      secs === 0 ? 'scanning…' : (m > 0 ? m + 'm ' : '') + s + 's';
  }, 1000);
});
```

Note: `let nextScanAt = null;` stays at the top level (outside the listener) so the countdown `setInterval` can reference it.

- [ ] **Step 3: Verify final `<script>` block structure**

The complete `<script>` block should be:

```html
<script>
let nextScanAt = null;

async function fetchTrades() { /* ... Task 3 code ... */ }
async function fetchIfAllWin() { /* ... Task 4 Step 1 code ... */ }

document.addEventListener('DOMContentLoaded', () => {
  /* ... Task 4 Step 2 code ... */
});

async function toggleBot() { /* ... existing code ... */ }
async function scanNow() { /* ... existing code ... */ }
async function setInterval_() { /* ... existing code ... */ }
</script>
```

- [ ] **Step 4: Commit**

```bash
git add prediction_bot/src/dashboard/templates/dashboard.html
git commit -m "fix(prediction-bot): defer SSE and async fetches to DOMContentLoaded

Moves EventSource open and status fetch inside DOMContentLoaded so they
never block initial paint. Refreshes trades+ifAllWin on each cycle_complete
SSE event. Closes #72.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 5: Manual verification

- [ ] **Step 1: Start the prediction bot**

```bash
cd /Users/pkhaninejad/Desktop/apps/Claude-trade-bot
.venv/bin/python prediction_bot/main.py
```

- [ ] **Step 2: Open dashboard and time initial load**

Open `http://localhost:4001` in a browser. The stat cards (BANKROLL, TOTAL P&L, WIN RATE, OPEN TRADES, STATUS) should render immediately with values. The trades table should show "Loading…" briefly then populate.

- [ ] **Step 3: Verify SSE doesn't block paint**

Open browser DevTools → Network tab. Confirm the `/api/stream` request starts after the page HTML is fully loaded (it should appear after `DOMContentLoaded` fires, not before).

- [ ] **Step 4: Verify trades load async**

In DevTools → Network, confirm `/api/trades` and `/api/trades/open` are fetched after the initial HTML response completes.

- [ ] **Step 5: Hard refresh**

Press Cmd+Shift+R. Page should appear immediately without hanging.
