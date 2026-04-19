# Ticket 6: Paper Trader + Result Store — Design Spec

**Date:** 2026-04-17
**Status:** Draft
**Master Spec:** [prediction-market-bot-design.md](2026-04-17-prediction-market-bot-design.md)
**Depends on:** Ticket 1 (scaffold)

---

## Goal

Paper trading system with SQLite persistence. Tracks virtual trades, settles them when markets resolve, maintains bankroll history. On startup, loads and displays all previous results.

---

## New File: `prediction_bot/src/data/result_store.py`

### Class: `ResultStore`

```python
class ResultStore:
    """SQLite-backed persistence for paper trades and bankroll."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize(self):
        """Create tables if not exist. Called once on startup."""

    async def add_trade(self, trade: PaperTrade) -> int:
        """Insert a new paper trade. Returns trade ID."""

    async def get_open_trades(self) -> list[PaperTrade]:
        """Fetch all trades with status='OPEN'."""

    async def settle_trade(self, trade_id: int, won: bool):
        """
        Settle a paper trade:
        - won=True: exit_price=1.0, pnl = (1.0 - entry_price) * quantity
        - won=False: exit_price=0.0, pnl = -entry_price * quantity
        Update bankroll snapshot.
        """

    async def expire_trade(self, trade_id: int):
        """Mark trade as EXPIRED (market expired without resolution). pnl = 0."""

    async def get_bankroll(self) -> float:
        """Get current virtual bankroll balance."""

    async def get_stats(self) -> dict:
        """
        Returns:
        {
            'total_trades': int,
            'open_trades': int,
            'won': int,
            'lost': int,
            'expired': int,
            'win_rate': float | None,
            'total_pnl': float,
            'roi': float,
            'bankroll': float,
            'best_trade': PaperTrade | None,
            'worst_trade': PaperTrade | None,
            'avg_edge': float,
            'pnl_by_category': {'crypto': float, 'sports': float, 'politics': float},
            'pnl_by_platform': {'polymarket': float, 'kalshi': float},
        }
        """

    async def get_recent_trades(self, limit: int = 50) -> list[PaperTrade]:
        """Fetch recent trades ordered by created_at DESC."""

    async def get_bankroll_history(self, limit: int = 100) -> list[BankrollSnapshot]:
        """Bankroll over time for charting."""
```

### SQLite Schema

```sql
CREATE TABLE IF NOT EXISTS paper_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    market_id TEXT NOT NULL,
    market_question TEXT NOT NULL,
    category TEXT NOT NULL,
    side TEXT NOT NULL,
    entry_price REAL NOT NULL,
    quantity REAL NOT NULL,
    cost REAL NOT NULL,
    confidence REAL NOT NULL,
    reasoning TEXT,
    status TEXT NOT NULL DEFAULT 'OPEN',
    exit_price REAL,
    pnl REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at TEXT,
    resolution_source TEXT
);

CREATE TABLE IF NOT EXISTS bankroll_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    balance REAL NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    trade_id INTEGER REFERENCES paper_trades(id)
);

CREATE INDEX IF NOT EXISTS idx_trades_status ON paper_trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_created ON paper_trades(created_at);
```

---

## New File: `prediction_bot/src/bot/paper_trader.py`

### Class: `PaperTrader`

```python
class PaperTrader:
    """Manages paper trading logic on top of ResultStore."""

    def __init__(self, store: ResultStore, settings: PredictionBotSettings):
        self.store = store
        self.settings = settings

    async def initialize(self):
        """Initialize store, load bankroll. Print previous results summary."""
        await self.store.initialize()
        stats = await self.store.get_stats()
        if stats["total_trades"] > 0:
            self._print_results_summary(stats)

    async def place_paper_trade(self, candidate: MarketCandidate) -> PaperTrade | None:
        """
        Place a paper trade if:
        1. Bankroll has sufficient funds
        2. Open positions < MAX_OPEN_POSITIONS
        3. Not already holding this market
        Returns the PaperTrade or None if rejected.
        """

    async def settle_open_trades(
        self,
        polymarket: PolymarketClient | None,
        kalshi: KalshiClient | None,
    ):
        """
        Check each open trade's market status.
        If resolved → settle (won/lost).
        If expired past end_date + 24h grace → mark expired.
        """

    def _calculate_quantity(self, candidate: MarketCandidate) -> float:
        """
        Allocate from virtual bankroll:
        - max_allocation = bankroll * MAX_POSITION_PCT
        - quantity = max_allocation / entry_price
        - Round to whole contracts
        """

    def _print_results_summary(self, stats: dict):
        """Log previous execution results on startup."""
        logger.info("=" * 60)
        logger.info("PREVIOUS RESULTS SUMMARY")
        logger.info(f"  Total trades: {stats['total_trades']}")
        logger.info(f"  Win rate: {stats['win_rate']:.1%}" if stats['win_rate'] else "  Win rate: N/A")
        logger.info(f"  Total P&L: ${stats['total_pnl']:.2f}")
        logger.info(f"  ROI: {stats['roi']:.1%}")
        logger.info(f"  Current bankroll: ${stats['bankroll']:.2f}")
        logger.info(f"  By category: {stats['pnl_by_category']}")
        logger.info("=" * 60)
```

### Trade Lifecycle

```
1. Scanner finds candidates → Evaluator assigns probabilities → Edge detected
2. PaperTrader.place_paper_trade(candidate)
   → Check bankroll, position limits, no duplicate market
   → Calculate quantity from bankroll allocation
   → Insert into SQLite via ResultStore
   → Deduct cost from bankroll
3. Each cycle: PaperTrader.settle_open_trades()
   → For each open trade, check market resolution status
   → If resolved: settle (won/lost), credit/debit bankroll
   → If past expiry + grace period: mark expired, refund cost
```

### Startup Flow

```
PredictionEngine.__init__()
  → ResultStore(db_path)
  → PaperTrader(store, settings)
  → await paper_trader.initialize()
      → Creates tables if first run
      → Loads stats
      → If previous trades exist:
          → Prints full results summary to log
          → Shows: trades, win rate, P&L, ROI, bankroll, by-category breakdown
```

---

## Testing

`prediction_bot/tests/test_paper_trader.py`:

- `test_place_trade_success` — trade placed, bankroll deducted
- `test_place_trade_insufficient_funds` — rejected when bankroll too low
- `test_place_trade_max_positions` — rejected when at position limit
- `test_place_trade_duplicate_market` — rejected for same market_id
- `test_settle_trade_won` — bankroll credited, status=WON
- `test_settle_trade_lost` — bankroll debited, status=LOST
- `test_expire_trade` — cost refunded, status=EXPIRED
- `test_startup_summary` — previous results logged on init

`prediction_bot/tests/test_result_store.py`:

- `test_create_tables` — schema created on first init
- `test_add_and_fetch_trade` — round-trip persistence
- `test_get_open_trades` — only OPEN status returned
- `test_settle_trade` — status + pnl updated correctly
- `test_get_stats` — aggregates computed correctly
- `test_bankroll_history` — snapshots tracked over time
- `test_pnl_by_category` — category breakdown correct

---

## Acceptance Criteria

- [ ] SQLite database created on first run
- [ ] Paper trades persisted across restarts
- [ ] Bankroll tracked with snapshots
- [ ] Trades settled when markets resolve
- [ ] Startup displays previous results summary
- [ ] Position limits and duplicate checks enforced
- [ ] Stats computed: win rate, P&L, ROI, by-category, by-platform
