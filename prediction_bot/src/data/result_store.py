"""aiosqlite persistence for paper trades and bankroll."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

import aiosqlite

from prediction_bot.src.api.models import BankrollSnapshot, PaperTrade

logger = logging.getLogger(__name__)

_SCHEMA = """
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
    created_at TEXT NOT NULL,
    end_date TEXT,
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
"""


class ResultStore:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(_SCHEMA)
            # migrate: add end_date if missing from older DB
            async with db.execute("PRAGMA table_info(paper_trades)") as cur:
                cols = {row[1] async for row in cur}
            if "end_date" not in cols:
                await db.execute("ALTER TABLE paper_trades ADD COLUMN end_date TEXT")
            await db.commit()

    async def add_trade(self, trade: PaperTrade, initial_bankroll: float | None = None) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """INSERT INTO paper_trades
                   (platform, market_id, market_question, category, side, entry_price,
                    quantity, cost, confidence, reasoning, created_at, end_date)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    trade.platform, trade.market_id, trade.market_question,
                    trade.category, trade.side, trade.entry_price,
                    trade.quantity, trade.cost, trade.confidence,
                    trade.reasoning, trade.created_at.isoformat(),
                    trade.end_date.isoformat() if trade.end_date else None,
                ),
            )
            trade_id = cur.lastrowid
            current = await self._get_bankroll_tx(db, initial_bankroll)
            new_balance = current - trade.cost
            await db.execute(
                "INSERT INTO bankroll_snapshots (balance, trade_id) VALUES (?, ?)",
                (new_balance, trade_id),
            )
            await db.commit()
        return trade_id

    async def _get_bankroll_tx(self, db: aiosqlite.Connection, initial: float | None) -> float:
        async with db.execute("SELECT balance FROM bankroll_snapshots ORDER BY id DESC LIMIT 1") as cur:
            row = await cur.fetchone()
        if row:
            return row[0]
        return initial or 1000.0

    async def get_open_trades(self) -> list[PaperTrade]:
        return await self._fetch_trades("WHERE status = 'OPEN'")

    async def settle_trade(self, trade_id: int, won: bool):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT entry_price, quantity, cost FROM paper_trades WHERE id=?", (trade_id,)
            ) as cur:
                row = await cur.fetchone()
            if not row:
                return
            entry_price, quantity, cost = row
            pnl = (1.0 - entry_price) * quantity if won else (-entry_price * quantity)
            status = "WON" if won else "LOST"
            exit_price = 1.0 if won else 0.0
            await db.execute(
                "UPDATE paper_trades SET status=?, exit_price=?, pnl=?, resolved_at=? WHERE id=?",
                (status, exit_price, pnl, datetime.now(UTC).isoformat(), trade_id),
            )
            current = await self._get_bankroll_tx(db, None)
            await db.execute(
                "INSERT INTO bankroll_snapshots (balance, trade_id) VALUES (?, ?)",
                (current + cost + pnl, trade_id),
            )
            await db.commit()

    async def re_settle_expired(self, trade_id: int, won: bool):
        """Correct an EXPIRED trade to WON/LOST and adjust bankroll by the delta."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT entry_price, quantity, cost FROM paper_trades WHERE id=? AND status='EXPIRED'",
                (trade_id,),
            ) as cur:
                row = await cur.fetchone()
            if not row:
                return
            entry_price, quantity, cost = row
            pnl = (1.0 - entry_price) * quantity if won else (-entry_price * quantity)
            status = "WON" if won else "LOST"
            await db.execute(
                "UPDATE paper_trades SET status=?, exit_price=?, pnl=?, resolved_at=?, resolution_source=? WHERE id=?",
                (status, 1.0 if won else 0.0, pnl, datetime.now(UTC).isoformat(), "re_settled", trade_id),
            )
            # expire_trade already refunded cost into bankroll; now apply only the pnl delta
            current = await self._get_bankroll_tx(db, None)
            await db.execute(
                "INSERT INTO bankroll_snapshots (balance, trade_id) VALUES (?, ?)",
                (current + pnl, trade_id),
            )
            await db.commit()

    async def expire_trade(self, trade_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT cost FROM paper_trades WHERE id=?", (trade_id,)
            ) as cur:
                row = await cur.fetchone()
            if not row:
                return
            cost = row[0]
            await db.execute(
                "UPDATE paper_trades SET status='EXPIRED', pnl=0, resolved_at=? WHERE id=?",
                (datetime.now(UTC).isoformat(), trade_id),
            )
            current = await self._get_bankroll_tx(db, None)
            await db.execute(
                "INSERT INTO bankroll_snapshots (balance, trade_id) VALUES (?, ?)",
                (current + cost, trade_id),
            )
            await db.commit()

    async def get_bankroll(self) -> float:
        async with aiosqlite.connect(self.db_path) as db:
            return await self._get_bankroll_tx(db, None)

    async def get_stats(self) -> dict:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT status, SUM(pnl), COUNT(*) FROM paper_trades GROUP BY status"
            ) as cur:
                rows = await cur.fetchall()

        counts: dict[str, int] = {"WON": 0, "LOST": 0, "EXPIRED": 0, "OPEN": 0}
        pnl_total = 0.0
        for status, pnl_sum, cnt in rows:
            counts[status] = cnt
            if pnl_sum:
                pnl_total += pnl_sum

        total = sum(counts.values())
        settled = counts["WON"] + counts["LOST"]
        win_rate = counts["WON"] / settled if settled > 0 else None
        bankroll = await self.get_bankroll()

        return {
            "total_trades": total,
            "open_trades": counts["OPEN"],
            "won": counts["WON"],
            "lost": counts["LOST"],
            "expired": counts["EXPIRED"],
            "win_rate": win_rate,
            "total_pnl": pnl_total,
            "roi": pnl_total / 1000.0 if total > 0 else 0.0,
            "bankroll": bankroll,
        }

    async def get_recent_trades(self, limit: int = 50) -> list[PaperTrade]:
        return await self._fetch_trades(f"ORDER BY created_at DESC LIMIT {limit}")

    async def get_bankroll_history(self, limit: int = 100) -> list[BankrollSnapshot]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                f"SELECT id, balance, timestamp, trade_id FROM bankroll_snapshots ORDER BY id DESC LIMIT {limit}"
            ) as cur:
                rows = await cur.fetchall()
        return [
            BankrollSnapshot(id=r[0], balance=r[1], timestamp=datetime.fromisoformat(r[2]), trade_id=r[3])
            for r in rows
        ]

    async def _fetch_trades(self, where_clause: str) -> list[PaperTrade]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                f"""SELECT id, platform, market_id, market_question, category, side,
                           entry_price, quantity, cost, confidence, reasoning,
                           status, exit_price, pnl, created_at, end_date, resolved_at, resolution_source
                    FROM paper_trades {where_clause}"""
            ) as cur:
                rows = await cur.fetchall()
        return [
            PaperTrade(
                id=r[0], platform=r[1], market_id=r[2], market_question=r[3],
                category=r[4], side=r[5], entry_price=r[6], quantity=r[7],
                cost=r[8], confidence=r[9], reasoning=r[10], status=r[11],
                exit_price=r[12], pnl=r[13],
                created_at=datetime.fromisoformat(r[14]),
                end_date=datetime.fromisoformat(r[15]) if r[15] else None,
                resolved_at=datetime.fromisoformat(r[16]) if r[16] else None,
                resolution_source=r[17],
            )
            for r in rows
        ]
