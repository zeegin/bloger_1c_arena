from __future__ import annotations

from typing import Sequence

from app.domain import Channel, FavoriteChannelInfo
from app.domain.rating.repositories import ChannelsRepository
from app.infrastructure.mappers import channel_from_row, favorite_channel_from_row

from .database import SQLiteDatabase


class SQLiteChannelsRepository(ChannelsRepository):
    def __init__(self, db: SQLiteDatabase):
        self._db = db

    async def get(self, channel_id: int) -> Channel:
        async with self._db.connect() as conn:
            cur = await conn.execute(
                """
                SELECT id, title, tg_url, description, image_url, rating, games, wins, losses
                FROM channels
                WHERE id=?
                """,
                (channel_id,),
            )
            row = await cur.fetchone()
        if not row:
            raise ValueError("Channel not found")
        return channel_from_row(dict(row))

    async def list_top(self, limit: int) -> Sequence[Channel]:
        async with self._db.connect() as conn:
            cur = await conn.execute(
                """
                SELECT id, title, tg_url, description, image_url, rating, games, wins, losses
                FROM channels
                ORDER BY rating DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cur.fetchall()
        return [channel_from_row(dict(row)) for row in rows]

    async def list_all(self) -> Sequence[Channel]:
        async with self._db.connect() as conn:
            cur = await conn.execute(
                """
                SELECT id, title, tg_url, description, image_url, rating, games, wins, losses
                FROM channels
                ORDER BY rating DESC
                """
            )
            rows = await cur.fetchall()
        return [channel_from_row(dict(row)) for row in rows]

    async def list_favorites(self) -> Sequence[FavoriteChannelInfo]:
        async with self._db.connect() as conn:
            cur = await conn.execute(
                """
                SELECT c.id, c.title, c.tg_url, COUNT(*) AS fans
                FROM users u
                JOIN channels c ON c.id = u.favorite_channel_id
                GROUP BY c.id
                ORDER BY fans DESC, c.title COLLATE NOCASE ASC
                """
            )
            rows = await cur.fetchall()
        return [favorite_channel_from_row(dict(row)) for row in rows]

    async def add_or_update(
        self,
        *,
        tg_url: str,
        title: str,
        description: str,
        image_url: str,
    ) -> None:
        async with self._db.connect() as conn:
            await conn.execute(
                """
                INSERT INTO channels(tg_url, title, description, image_url)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(tg_url) DO UPDATE SET
                  title=excluded.title,
                  description=excluded.description,
                  image_url=excluded.image_url
                """,
                (tg_url, title, description, image_url),
            )
            await conn.commit()

    async def delete_not_in(self, allowed_urls: set[str]) -> int:
        placeholders = ",".join("?" for _ in allowed_urls)
        query = (
            f"DELETE FROM channels WHERE tg_url NOT IN ({placeholders})"
            if allowed_urls
            else "DELETE FROM channels"
        )
        params = tuple(allowed_urls)
        async with self._db.connect() as conn:
            cur = await conn.execute(query, params)
            await conn.commit()
            return cur.rowcount
