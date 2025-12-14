from __future__ import annotations

from typing import Sequence

from app.domain import Channel
from app.domain.arena.repositories import PairingRepository
from app.infrastructure.mappers import channel_from_row

from .database import SQLiteDatabase
from ..metrics import metrics


class SQLitePairingRepository(PairingRepository):
    def __init__(self, db: SQLiteDatabase):
        self._db = db

    @metrics.wrap_async("db:pairing.low_game_pool", source="database")
    async def fetch_low_game_pool(self, limit: int) -> Sequence[Channel]:
        async with self._db.connect() as conn:
            cur = await conn.execute(
                """
                SELECT id, title, tg_url, description, image_url, rating, games, wins, losses
                FROM channels
                ORDER BY games ASC, RANDOM()
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cur.fetchall()
        return [channel_from_row(dict(r)) for r in rows]

    @metrics.wrap_async("db:pairing.fetch_closest", source="database")
    async def fetch_closest(self, channel_id: int, rating: float, limit: int) -> Sequence[Channel]:
        async with self._db.connect() as conn:
            cur = await conn.execute(
                """
                SELECT id, title, tg_url, description, image_url, rating, games, wins, losses
                FROM channels
                WHERE id != ?
                ORDER BY ABS(rating - ?) ASC
                LIMIT ?
                """,
                (channel_id, rating, limit),
            )
            rows = await cur.fetchall()
        return [channel_from_row(dict(r)) for r in rows]

    @metrics.wrap_async("db:pairing.has_seen_pair", source="database")
    async def has_seen_pair(self, user_id: int, a_id: int, b_id: int) -> bool:
        x, y = (a_id, b_id) if a_id < b_id else (b_id, a_id)
        async with self._db.connect() as conn:
            cur = await conn.execute(
                "SELECT 1 FROM user_pair_seen WHERE user_id=? AND channel_a_id=? AND channel_b_id=?",
                (user_id, x, y),
            )
            row = await cur.fetchone()
        return row is not None

    @metrics.wrap_async("db:pairing.mark_seen", source="database")
    async def mark_seen(self, user_id: int, a_id: int, b_id: int) -> None:
        x, y = (a_id, b_id) if a_id < b_id else (b_id, a_id)
        async with self._db.connect() as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO user_pair_seen(user_id, channel_a_id, channel_b_id) VALUES(?, ?, ?)",
                (user_id, x, y),
            )
            await conn.commit()
