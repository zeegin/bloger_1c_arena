from __future__ import annotations

from typing import Optional

from app.domain import Channel
from app.domain.players.repositories import PlayersRepository
from app.infrastructure.mappers import channel_from_row

from .database import SQLiteDatabase
from ..metrics import metrics


class SQLitePlayersRepository(PlayersRepository):
    def __init__(self, db: SQLiteDatabase):
        self._db = db

    @metrics.wrap_async("db:players.upsert", source="database")
    async def upsert(self, tg_user_id: int, username: Optional[str], first_name: Optional[str]) -> int:
        async with self._db.connect() as conn:
            await conn.execute(
                """
                INSERT INTO users(tg_user_id, username, first_name)
                VALUES(?, ?, ?)
                ON CONFLICT(tg_user_id) DO UPDATE SET
                  username=excluded.username,
                  first_name=excluded.first_name
                """,
                (tg_user_id, username, first_name),
            )
            await conn.commit()
            cur = await conn.execute("SELECT id FROM users WHERE tg_user_id=?", (tg_user_id,))
            row = await cur.fetchone()
        return int(row["id"])

    @metrics.wrap_async("db:players.classic_games", source="database")
    async def get_classic_games(self, user_id: int) -> int:
        async with self._db.connect() as conn:
            cur = await conn.execute("SELECT classic_games FROM users WHERE id=?", (user_id,))
            row = await cur.fetchone()
        if not row:
            return 0
        value = row["classic_games"]
        return int(value) if value is not None else 0

    @metrics.wrap_async("db:players.draw_count", source="database")
    async def get_draw_count(self, user_id: int) -> int:
        async with self._db.connect() as conn:
            cur = await conn.execute(
                "SELECT COUNT(*) AS c FROM votes WHERE user_id=? AND winner_channel_id IS NULL",
                (user_id,),
            )
            row = await cur.fetchone()
        return int(row["c"])

    @metrics.wrap_async("db:players.set_favorite", source="database")
    async def set_favorite(self, user_id: int, channel_id: Optional[int]) -> None:
        async with self._db.connect() as conn:
            await conn.execute(
                "UPDATE users SET favorite_channel_id=? WHERE id=?",
                (channel_id, user_id),
            )
            await conn.commit()

    @metrics.wrap_async("db:players.get_favorite", source="database")
    async def get_favorite(self, user_id: int) -> Optional[Channel]:
        async with self._db.connect() as conn:
            cur = await conn.execute(
                """
                SELECT c.id, c.title, c.tg_url, c.description, c.image_url, c.rating, c.games, c.wins, c.losses
                FROM users u
                JOIN channels c ON c.id = u.favorite_channel_id
                WHERE u.id=? AND u.favorite_channel_id IS NOT NULL
                """,
                (user_id,),
            )
            row = await cur.fetchone()
        return channel_from_row(dict(row)) if row else None

    @metrics.wrap_async("db:players.reward_stage", source="database")
    async def get_reward_stage(self, user_id: int) -> int:
        async with self._db.connect() as conn:
            cur = await conn.execute("SELECT reward_stage FROM users WHERE id=?", (user_id,))
            row = await cur.fetchone()
        return int(row["reward_stage"]) if row and row["reward_stage"] is not None else 0

    @metrics.wrap_async("db:players.set_reward_stage", source="database")
    async def set_reward_stage(self, user_id: int, stage: int) -> None:
        async with self._db.connect() as conn:
            await conn.execute(
                "UPDATE users SET reward_stage=? WHERE id=?",
                (stage, user_id),
            )
            await conn.commit()

    @metrics.wrap_async("db:players.dm_unlocked", source="database")
    async def is_deathmatch_unlocked(self, user_id: int) -> bool:
        async with self._db.connect() as conn:
            cur = await conn.execute("SELECT deathmatch_unlocked FROM users WHERE id=?", (user_id,))
            row = await cur.fetchone()
        if not row:
            return False
        return bool(row["deathmatch_unlocked"])

    @metrics.wrap_async("db:players.mark_dm_unlocked", source="database")
    async def mark_deathmatch_unlocked(self, user_id: int) -> None:
        async with self._db.connect() as conn:
            await conn.execute(
                "UPDATE users SET deathmatch_unlocked=1 WHERE id=?",
                (user_id,),
            )
            await conn.commit()

    @metrics.wrap_async("db:players.dm_games", source="database")
    async def get_deathmatch_games(self, user_id: int) -> int:
        async with self._db.connect() as conn:
            cur = await conn.execute(
                "SELECT COUNT(*) AS c FROM deathmatch_votes WHERE user_id=?",
                (user_id,),
            )
            row = await cur.fetchone()
        return int(row["c"])

    @metrics.wrap_async("db:players.dm_games_count", source="database")
    async def get_deathmatch_game_count(self, user_id: int) -> int:
        return await self.get_deathmatch_games(user_id)

    @metrics.wrap_async("db:players.rating_unlocked", source="database")
    async def has_rating_unlocked(self, user_id: int) -> bool:
        async with self._db.connect() as conn:
            cur = await conn.execute("SELECT rating_unlocked FROM users WHERE id=?", (user_id,))
            row = await cur.fetchone()
        if not row:
            return False
        return bool(row["rating_unlocked"])

    @metrics.wrap_async("db:players.mark_rating_unlocked", source="database")
    async def mark_rating_unlocked(self, user_id: int) -> None:
        async with self._db.connect() as conn:
            await conn.execute(
                "UPDATE users SET rating_unlocked=1 WHERE id=?",
                (user_id,),
            )
            await conn.commit()
