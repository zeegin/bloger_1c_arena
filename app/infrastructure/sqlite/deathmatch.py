from __future__ import annotations

from typing import Optional

from app.domain import DeathmatchState
from app.domain.deathmatch.repositories import DeathmatchRepository
from app.infrastructure.mappers import (
    deathmatch_state_from_row,
    serialize_deathmatch_state,
)

from .database import SQLiteDatabase


class SQLiteDeathmatchRepository(DeathmatchRepository):
    def __init__(self, db: SQLiteDatabase):
        self._db = db

    async def get_state(self, user_id: int) -> Optional[DeathmatchState]:
        async with self._db.connect() as conn:
            cur = await conn.execute(
                """
                SELECT user_id, champion_id, seen_ids, remaining_ids, round_total, rounds_played
                FROM deathmatch_state
                WHERE user_id=?
                """,
                (user_id,),
            )
            row = await cur.fetchone()
        if not row:
            return None
        return deathmatch_state_from_row(dict(row))

    async def save_state(self, state: DeathmatchState) -> None:
        seen_payload, remaining_payload = serialize_deathmatch_state(state)
        async with self._db.connect() as conn:
            await conn.execute(
                """
                INSERT INTO deathmatch_state(
                  user_id, champion_id, seen_ids, remaining_ids, round_total, rounds_played, updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(user_id) DO UPDATE SET
                  champion_id=excluded.champion_id,
                  seen_ids=excluded.seen_ids,
                  remaining_ids=excluded.remaining_ids,
                  round_total=excluded.round_total,
                  rounds_played=excluded.rounds_played,
                  updated_at=excluded.updated_at
                """,
                (
                    state.user_id,
                    state.champion_id,
                    seen_payload,
                    remaining_payload,
                    state.round_total,
                    state.rounds_played,
                ),
            )
            await conn.commit()

    async def delete_state(self, user_id: int) -> None:
        async with self._db.connect() as conn:
            await conn.execute("DELETE FROM deathmatch_state WHERE user_id=?", (user_id,))
            await conn.commit()

    async def log_vote(
        self,
        *,
        user_id: int,
        champion_id: Optional[int],
        channel_a_id: int,
        channel_b_id: int,
        winner_id: int,
    ) -> None:
        async with self._db.connect() as conn:
            await conn.execute(
                """
                INSERT INTO deathmatch_votes(user_id, champion_id, channel_a_id, channel_b_id, winner_channel_id)
                VALUES(?, ?, ?, ?, ?)
                """,
                (user_id, champion_id, channel_a_id, channel_b_id, winner_id),
            )
            await conn.commit()
