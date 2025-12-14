from __future__ import annotations

from app.domain import DeathmatchStats, RatingStats
from app.domain.rating.repositories import StatsRepository
from app.infrastructure.mappers import deathmatch_stats_from_row, rating_stats_from_row

from .database import SQLiteDatabase
from ..metrics import metrics


class SQLiteStatsRepository(StatsRepository):
    def __init__(self, db: SQLiteDatabase):
        self._db = db

    @metrics.wrap_async("db:stats.rating", source="database")
    async def rating_stats(self) -> RatingStats:
        async with self._db.connect() as conn:
            cur = await conn.execute("SELECT COUNT(*) AS c FROM votes")
            games_row = await cur.fetchone()
            cur = await conn.execute("SELECT COUNT(*) AS c FROM users")
            users_row = await cur.fetchone()
        return rating_stats_from_row(
            {"games": games_row["c"], "players": users_row["c"]}
        )

    @metrics.wrap_async("db:stats.deathmatch", source="database")
    async def deathmatch_stats(self) -> DeathmatchStats:
        async with self._db.connect() as conn:
            cur = await conn.execute("SELECT COUNT(*) AS c FROM deathmatch_votes")
            games_row = await cur.fetchone()
            cur = await conn.execute("SELECT COUNT(DISTINCT user_id) AS c FROM deathmatch_votes")
            players_row = await cur.fetchone()
        return deathmatch_stats_from_row(
            {"games": games_row["c"], "players": players_row["c"]}
        )
