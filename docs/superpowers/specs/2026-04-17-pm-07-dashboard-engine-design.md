# Ticket 7: Dashboard + Engine Integration — Design Spec

**Date:** 2026-04-17
**Status:** Draft
**Master Spec:** [prediction-market-bot-design.md](2026-04-17-prediction-market-bot-design.md)
**Depends on:** Tickets 1–6

---

## Goal

Wire everything together: PredictionEngine orchestrates the scan→evaluate→trade cycle, FastAPI dashboard displays results, SSE pushes real-time updates. The dashboard shows previous execution results on load.

---

## New File: `prediction_bot/src/bot/engine.py`

### Class: `PredictionEngine`

```python
class PredictionEngine:
    def __init__(self):
        self.settings = pm_settings
        self.polymarket = PolymarketClient() if settings.POLYMARKET_ENABLED else None
        self.kalshi = KalshiClient() if settings.KALSHI_ENABLED else None
        self.paper_trader = PaperTrader(ResultStore(settings.PM_DB_PATH), settings)
        self.status = PMBotStatus(...)
        self._running = False
        self._scan_history: list[dict] = []  # last 50 scan results (in-memory)

    async def start(self):
        """Initialize paper trader (loads previous results), then loop."""
        await self.paper_trader.initialize()  # prints previous results
        self._running = True
        while self._running:
            try:
                await self._cycle()
            except Exception as e:
                logger.error(f"Cycle error: {e}")
            await asyncio.sleep(self.settings.SCAN_INTERVAL_SECONDS)

    async def _cycle(self):
        """
        1. Settle open paper trades (check resolutions)
        2. Scan markets (both platforms)
        3. Evaluate candidates via LLM
        4. Place paper trades on edge candidates
        5. Update status + broadcast SSE
        """
        # Step 1: Settle
        await self.paper_trader.settle_open_trades(self.polymarket, self.kalshi)

        # Step 2: Scan
        candidates = await scan_markets(self.polymarket, self.kalshi, self.settings)
        logger.info(f"Scanner found {len(candidates)} candidates")

        # Step 3: Evaluate
        if candidates:
            evaluated = await evaluate_candidates(candidates, self.settings)
            logger.info(f"Evaluator found {len(evaluated)} with edge")
        else:
            evaluated = []

        # Step 4: Paper trade
        trades_placed = 0
        for candidate in evaluated:
            trade = await self.paper_trader.place_paper_trade(candidate)
            if trade:
                trades_placed += 1
                logger.info(f"Paper trade: {trade.side} {trade.market_question[:60]} @ ${trade.entry_price:.2f}")

        # Step 5: Update status
        stats = await self.paper_trader.store.get_stats()
        self.status.open_trades = stats["open_trades"]
        self.status.bankroll = stats["bankroll"]
        self.status.total_pnl = stats["total_pnl"]
        self.status.win_rate = stats["win_rate"]
        self.status.last_scan = datetime.now()
        self.status.next_scan = datetime.now() + timedelta(seconds=self.settings.SCAN_INTERVAL_SECONDS)

        # Record scan
        self._scan_history.append({
            "timestamp": datetime.now().isoformat(),
            "candidates_found": len(candidates),
            "edges_found": len(evaluated),
            "trades_placed": trades_placed,
        })
        if len(self._scan_history) > 50:
            self._scan_history = self._scan_history[-50:]

        # Broadcast
        await broadcast_sse({"type": "cycle_complete", "status": self.status.model_dump()})

    def stop(self):
        self._running = False

    def toggle(self):
        self.status.enabled = not self.status.enabled
```

---

## New File: `prediction_bot/src/dashboard/app.py`

### FastAPI Application

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(engine.start())
    yield
    engine.stop()
    task.cancel()

app = FastAPI(title="Prediction Market Bot", lifespan=lifespan)
```

### API Endpoints

| Endpoint | Method | Response |
|----------|--------|----------|
| `/api/status` | GET | PMBotStatus (enabled, bankroll, P&L, win rate, next scan) |
| `/api/bot/toggle` | POST | Toggle enabled state |
| `/api/stats` | GET | Full ResultStore stats (by category, platform, totals) |
| `/api/trades` | GET | Recent paper trades (limit param, default 50) |
| `/api/trades/open` | GET | Currently open paper trades |
| `/api/bankroll-history` | GET | Bankroll snapshots for charting |
| `/api/scans` | GET | Last 50 scan results (candidates found, edges, trades placed) |
| `/api/cycle` | POST | Manually trigger a scan cycle |
| `/api/stream` | GET | SSE feed for real-time updates |
| `/` | GET | Dashboard HTML page |

### Dashboard HTML

Single-page dashboard (same pattern as stock bot):

**Top Row — Status Cards:**
- Bankroll: $XXX.XX
- Total P&L: +$XX.XX (green/red)
- Win Rate: XX% (W-L-E)
- Open Trades: X

**Middle — Results Table:**
| Time | Market | Platform | Side | Entry | Status | P&L | Category |
|------|--------|----------|------|-------|--------|-----|----------|
| ... | Will BTC stay > $80k? | Polymarket | YES | $0.92 | WON ✅ | +$0.80 | Crypto |
| ... | Will Lakers win Game 5? | Polymarket | YES | $0.88 | LOST ❌ | -$8.80 | Sports |
| ... | Fed hold rates? | Kalshi | YES | $0.95 | OPEN ⏳ | — | Crypto |

**Bottom Left — Category Breakdown:**
- Crypto: +$XX.XX (X-X-X)
- Sports: +$XX.XX (X-X-X)
- Politics: +$XX.XX (X-X-X)

**Bottom Right — Bankroll Chart:**
- Line chart of bankroll over time (from bankroll_snapshots)

**Bottom — Scan History:**
- Last 10 scans: timestamp, candidates found, edges found, trades placed

### SSE Events

```json
{"type": "cycle_complete", "status": {...}}
{"type": "trade_placed", "trade": {...}}
{"type": "trade_settled", "trade": {...}, "pnl": ...}
```

---

## Modified File: `docker-compose.yml`

```yaml
services:
  trade-bot:
    # ... existing stock bot

  prediction-bot:
    build:
      context: .
      dockerfile: prediction_bot/Dockerfile
    restart: unless-stopped
    ports:
      - "4001:4001"
    env_file:
      - .env
    volumes:
      - ./prediction_bot/data:/app/prediction_bot/data  # persist SQLite
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:4001/api/status"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### New File: `prediction_bot/Dockerfile`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 4001
CMD ["python", "-m", "prediction_bot.main"]
```

---

## Startup Behavior

```
$ python -m prediction_bot.main

2026-04-17 10:00:00 [INFO] ============================================================
2026-04-17 10:00:00 [INFO] PREVIOUS RESULTS SUMMARY
2026-04-17 10:00:00 [INFO]   Total trades: 47
2026-04-17 10:00:00 [INFO]   Win rate: 72.3% (34W / 13L / 0E)
2026-04-17 10:00:00 [INFO]   Total P&L: +$127.40
2026-04-17 10:00:00 [INFO]   ROI: 12.7%
2026-04-17 10:00:00 [INFO]   Current bankroll: $1,127.40
2026-04-17 10:00:00 [INFO]   By category: crypto=+$68.20, sports=+$42.10, politics=+$17.10
2026-04-17 10:00:00 [INFO] ============================================================
2026-04-17 10:00:00 [INFO] Prediction Market Bot started on http://0.0.0.0:4001
2026-04-17 10:00:00 [INFO] Platforms: Polymarket=ON, Kalshi=OFF
2026-04-17 10:00:00 [INFO] Categories: crypto, sports, politics
2026-04-17 10:00:01 [INFO] Settling 3 open trades...
2026-04-17 10:00:02 [INFO]   SETTLED: "Will BTC stay > $80k this week?" → WON +$0.80
2026-04-17 10:00:03 [INFO] Scanner found 23 candidates
2026-04-17 10:00:05 [INFO] Evaluator found 4 with edge > 2%
2026-04-17 10:00:05 [INFO] Paper trade: YES "Will Lakers advance?" @ $0.93
2026-04-17 10:00:05 [INFO] Paper trade: NO "Will it rain in NYC tomorrow?" @ $0.91
```

---

## Testing

No new test file — integration is validated by running the bot. Individual component tests are in tickets 1–6.

Manual test plan:
1. Start bot with no previous data → clean start, $1000 bankroll
2. Wait for first cycle → candidates scanned, evaluated, trades placed
3. Restart bot → previous results displayed on startup
4. Open dashboard → see trades, P&L, bankroll chart
5. Trigger manual cycle → `/api/cycle` works
6. Toggle bot → `/api/bot/toggle` pauses/resumes scanning

---

## Acceptance Criteria

- [ ] Engine orchestrates full cycle: scan → evaluate → trade → settle
- [ ] Dashboard displays all results with live updates
- [ ] Previous results shown on startup (both log + dashboard)
- [ ] SSE pushes real-time updates to dashboard
- [ ] Docker Compose runs both bots independently
- [ ] Can run standalone: `python -m prediction_bot.main`
