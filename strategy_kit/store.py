from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import aiosqlite

from strategy_kit.models import StrategyDefinition

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS strategies (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    bot TEXT NOT NULL,
    params TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0
);
"""


class StrategyStore:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.executescript(_SCHEMA)
            async with db.execute("PRAGMA table_info(strategies)") as cur:
                cols = {row[1] async for row in cur}
            if "active" not in cols:
                await db.execute(
                    "ALTER TABLE strategies ADD COLUMN active INTEGER NOT NULL DEFAULT 1"
                )
            await db.commit()

    async def create(self, definition: StrategyDefinition) -> str:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO strategies (id, name, description, bot, params, created_at, archived)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    definition.id,
                    definition.name,
                    definition.description,
                    definition.bot,
                    json.dumps(definition.params),
                    definition.created_at.isoformat(),
                    int(definition.archived),
                ),
            )
            await db.commit()
        return definition.id

    async def get(self, id: str) -> StrategyDefinition | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM strategies WHERE id = ?", (id,)
            ) as cur:
                row = await cur.fetchone()
        if row is None:
            return None
        return _row_to_definition(row)

    async def list(
        self, bot: str, include_archived: bool = False, active_only: bool = False
    ) -> list[StrategyDefinition]:
        query = "SELECT * FROM strategies WHERE bot = ?"
        args: list = [bot]
        if not include_archived:
            query += " AND archived = 0"
        if active_only:
            query += " AND active = 1"
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, args) as cur:
                rows = await cur.fetchall()
        return [_row_to_definition(row) for row in rows]

    async def update(
        self,
        id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        params: dict | None = None,
    ) -> None:
        updates: list[str] = []
        vals: list = []
        if name is not None:
            updates.append("name = ?")
            vals.append(name)
        if description is not None:
            updates.append("description = ?")
            vals.append(description)
        if params is not None:
            updates.append("params = ?")
            vals.append(json.dumps(params))
        if not updates:
            return
        vals.append(id)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                f"UPDATE strategies SET {', '.join(updates)} WHERE id = ?", vals
            )
            await db.commit()

    async def archive(self, id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE strategies SET archived = 1 WHERE id = ?", (id,)
            )
            await db.commit()

    async def activate(self, id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE strategies SET active = 1 WHERE id = ?", (id,))
            await db.commit()

    async def deactivate(self, id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE strategies SET active = 0 WHERE id = ?", (id,))
            await db.commit()


def _row_to_definition(row: aiosqlite.Row) -> StrategyDefinition:
    return StrategyDefinition(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        bot=row["bot"],
        params=json.loads(row["params"] or "{}"),
        created_at=datetime.fromisoformat(row["created_at"]),
        archived=bool(row["archived"]),
    )
