from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import NamedTuple

import aiosqlite

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS shadow_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id TEXT NOT NULL,
    trade_ref TEXT NOT NULL,
    direction TEXT NOT NULL DEFAULT 'long',
    entry_price REAL NOT NULL,
    quantity REAL NOT NULL,
    cost REAL NOT NULL,
    exit_price REAL,
    pnl REAL,
    status TEXT NOT NULL DEFAULT 'open',
    opened_at TEXT NOT NULL,
    closed_at TEXT
);

CREATE TABLE IF NOT EXISTS shadow_equity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id TEXT NOT NULL,
    balance REAL NOT NULL,
    timestamp TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_shadow_strategy ON shadow_trades(strategy_id);
CREATE INDEX IF NOT EXISTS idx_shadow_equity_strategy ON shadow_equity(strategy_id);
"""


class EquityPoint(NamedTuple):
    timestamp: datetime
    balance: float


class StrategyStats(NamedTuple):
    total_pnl: float
    win_rate: float
    roi: float
    open_count: int
    settled_count: int


class ShadowPortfolio:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.executescript(_SCHEMA)
            await db.commit()

    async def seed_bankroll(self, strategy_id: str, initial_balance: float) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO shadow_equity (strategy_id, balance, timestamp) VALUES (?, ?, ?)",
                (strategy_id, initial_balance, datetime.now(UTC).isoformat()),
            )
            await db.commit()

    async def open_trade(
        self,
        strategy_id: str,
        trade_ref: str,
        entry_price: float,
        quantity: float,
        *,
        direction: str = "long",
    ) -> int:
        cost = entry_price * quantity
        async with aiosqlite.connect(self.db_path) as db:
            balance = await self._get_balance(db, strategy_id)
            cur = await db.execute(
                """INSERT INTO shadow_trades
                   (strategy_id, trade_ref, direction, entry_price, quantity, cost, opened_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    strategy_id, trade_ref, direction,
                    entry_price, quantity, cost,
                    datetime.now(UTC).isoformat(),
                ),
            )
            trade_id = cur.lastrowid
            await db.execute(
                "INSERT INTO shadow_equity (strategy_id, balance, timestamp) VALUES (?, ?, ?)",
                (strategy_id, balance - cost, datetime.now(UTC).isoformat()),
            )
            await db.commit()
        return trade_id

    async def close_trade(self, trade_id: int, exit_price: float) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT strategy_id, entry_price, quantity, direction FROM shadow_trades WHERE id = ?",
                (trade_id,),
            ) as cur:
                row = await cur.fetchone()
            if row is None:
                raise ValueError(f"trade {trade_id} not found")
            strategy_id = row["strategy_id"]
            entry_price = row["entry_price"]
            quantity = row["quantity"]
            direction = row["direction"]
            pnl = (
                (exit_price - entry_price) * quantity
                if direction == "long"
                else (entry_price - exit_price) * quantity
            )
            cost = entry_price * quantity
            balance = await self._get_balance(db, strategy_id)
            await db.execute(
                """UPDATE shadow_trades
                   SET exit_price = ?, pnl = ?, status = 'closed', closed_at = ?
                   WHERE id = ?""",
                (exit_price, pnl, datetime.now(UTC).isoformat(), trade_id),
            )
            await db.execute(
                "INSERT INTO shadow_equity (strategy_id, balance, timestamp) VALUES (?, ?, ?)",
                (strategy_id, balance + cost + pnl, datetime.now(UTC).isoformat()),
            )
            await db.commit()

    async def equity_curve(self, strategy_id: str) -> list[EquityPoint]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT timestamp, balance FROM shadow_equity WHERE strategy_id = ? ORDER BY id ASC",
                (strategy_id,),
            ) as cur:
                rows = await cur.fetchall()
        return [EquityPoint(datetime.fromisoformat(r[0]), r[1]) for r in rows]

    async def stats(self, strategy_id: str) -> StrategyStats:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT pnl, status FROM shadow_trades WHERE strategy_id = ?",
                (strategy_id,),
            ) as cur:
                rows = await cur.fetchall()
        total_pnl = 0.0
        wins = 0
        settled = 0
        open_count = 0
        for pnl, status in rows:
            if status == "open":
                open_count += 1
            else:
                settled += 1
                if pnl is not None:
                    total_pnl += pnl
                    if pnl > 0:
                        wins += 1
        win_rate = wins / settled if settled else 0.0
        curve = await self.equity_curve(strategy_id)
        initial = curve[0].balance if curve else 0.0
        roi = total_pnl / initial if initial else 0.0
        return StrategyStats(
            total_pnl=total_pnl,
            win_rate=win_rate,
            roi=roi,
            open_count=open_count,
            settled_count=settled,
        )

    async def _get_balance(self, db: aiosqlite.Connection, strategy_id: str) -> float:
        async with db.execute(
            "SELECT balance FROM shadow_equity WHERE strategy_id = ? ORDER BY id DESC LIMIT 1",
            (strategy_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            raise ValueError(f"No bankroll seeded for strategy {strategy_id!r}")
        return row[0]
