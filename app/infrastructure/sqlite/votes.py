from __future__ import annotations

from typing import Optional

from app.domain import Channel
from app.domain.arena.repositories import VotesRepository

from .database import SQLiteDatabase
from ..metrics import metrics


class SQLiteVotesRepository(VotesRepository):
    def __init__(self, db: SQLiteDatabase):
        self._db = db

    @metrics.wrap_async("db:votes.record_vote", source="database")
    async def record_vote(
        self,
        *,
        user_id: int,
        channel_a_before: Channel,
        channel_b_before: Channel,
        channel_a_after: Channel,
        channel_b_after: Channel,
        winner_channel_id: Optional[int],
        draw: bool,
    ) -> None:
        async with self._db.connect() as conn:
            await conn.execute("BEGIN IMMEDIATE;")
            await conn.execute(
                """
                INSERT INTO votes(
                  user_id, channel_a_id, channel_b_id, winner_channel_id,
                  rating_a_before, rating_b_before, rating_a_after, rating_b_after
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    channel_a_before.id,
                    channel_b_before.id,
                    winner_channel_id,
                    channel_a_before.rating,
                    channel_b_before.rating,
                    channel_a_after.rating,
                    channel_b_after.rating,
                ),
            )

            await conn.execute(
                """
                UPDATE channels
                SET rating=?, games=?, wins=?, losses=?
                WHERE id=?
                """,
                (
                    channel_a_after.rating,
                    channel_a_after.games,
                    channel_a_after.wins,
                    channel_a_after.losses,
                    channel_a_after.id,
                ),
            )
            await conn.execute(
                """
                UPDATE channels
                SET rating=?, games=?, wins=?, losses=?
                WHERE id=?
                """,
                (
                    channel_b_after.rating,
                    channel_b_after.games,
                    channel_b_after.wins,
                    channel_b_after.losses,
                    channel_b_after.id,
                ),
            )
            await conn.commit()
