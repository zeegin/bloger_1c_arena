from __future__ import annotations

import uuid

from app.domain.shared.models import ActiveVoteToken, VoteToken
from app.domain.shared.repositories import VoteTokensRepository

from .database import SQLiteDatabase


class SQLiteVoteTokensRepository(VoteTokensRepository):
    def __init__(self, db: SQLiteDatabase):
        self._db = db

    async def create(self, user_id: int, vote_type: str, *, channel_a_id: int, channel_b_id: int) -> VoteToken:
        token = uuid.uuid4().hex
        async with self._db.connect() as conn:
            await conn.execute(
                """
                INSERT INTO vote_tokens(token, user_id, vote_type, channel_a_id, channel_b_id)
                VALUES(?, ?, ?, ?, ?)
                """,
                (token, user_id, vote_type, channel_a_id, channel_b_id),
            )
            await conn.commit()
        return VoteToken(token)

    async def consume(
        self,
        token: VoteToken,
        *,
        user_id: int,
        vote_type: str,
        channel_a_id: int,
        channel_b_id: int,
    ) -> bool:
        async with self._db.connect() as conn:
            cur = await conn.execute(
                """
                UPDATE vote_tokens
                SET consumed=1, consumed_at=datetime('now')
                WHERE token=? AND consumed=0 AND user_id=? AND vote_type=? AND channel_a_id=? AND channel_b_id=?
                """,
                (token.value, user_id, vote_type, channel_a_id, channel_b_id),
            )
            await conn.commit()
            return cur.rowcount == 1

    async def get_active(self, user_id: int, vote_type: str) -> ActiveVoteToken | None:
        async with self._db.connect() as conn:
            cur = await conn.execute(
                """
                SELECT token, channel_a_id, channel_b_id
                FROM vote_tokens
                WHERE user_id=? AND vote_type=? AND consumed=0
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_id, vote_type),
            )
            row = await cur.fetchone()
        if not row:
            return None
        return ActiveVoteToken(
            token=VoteToken(row["token"]),
            channel_a_id=int(row["channel_a_id"]),
            channel_b_id=int(row["channel_b_id"]),
        )

    async def invalidate(self, user_id: int, vote_type: str) -> None:
        async with self._db.connect() as conn:
            await conn.execute(
                """
                UPDATE vote_tokens
                SET consumed=1, consumed_at=datetime('now')
                WHERE user_id=? AND vote_type=? AND consumed=0
                """,
                (user_id, vote_type),
            )
            await conn.commit()
