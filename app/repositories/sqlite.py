from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Sequence, Optional

import aiosqlite
from aiosqlite import OperationalError

from ..domain import (
    Channel,
    DeathmatchState,
    DeathmatchStats,
    FavoriteChannelInfo,
    RatingStats,
)
from ..domain.value_objects import VoteToken
from ..domain.repositories import (
    ChannelsRepository,
    DeathmatchRepository,
    PairingRepository,
    PlayersRepository,
    StatsRepository,
    VoteTokensRepository,
    VotesRepository,
)
from ..infrastructure.mappers import (
    channel_from_row,
    deathmatch_state_from_row,
    deathmatch_stats_from_row,
    favorite_channel_from_row,
    rating_stats_from_row,
    serialize_deathmatch_state,
)

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tg_user_id INTEGER UNIQUE NOT NULL,
  username TEXT,
  first_name TEXT,
  is_admin INTEGER NOT NULL DEFAULT 0,
  favorite_channel_id INTEGER,
  created_at TEXT DEFAULT (datetime('now')),
  FOREIGN KEY(favorite_channel_id) REFERENCES channels(id)
);

CREATE TABLE IF NOT EXISTS channels (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tg_url TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  image_url TEXT NOT NULL DEFAULT '',
  rating REAL NOT NULL DEFAULT 1500,
  games INTEGER NOT NULL DEFAULT 0,
  wins INTEGER NOT NULL DEFAULT 0,
  losses INTEGER NOT NULL DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS votes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  channel_a_id INTEGER NOT NULL,
  channel_b_id INTEGER NOT NULL,
  winner_channel_id INTEGER,
  rating_a_before REAL NOT NULL,
  rating_b_before REAL NOT NULL,
  rating_a_after REAL NOT NULL,
  rating_b_after REAL NOT NULL,
  created_at TEXT DEFAULT (datetime('now')),
  FOREIGN KEY(user_id) REFERENCES users(id),
  FOREIGN KEY(channel_a_id) REFERENCES channels(id),
  FOREIGN KEY(channel_b_id) REFERENCES channels(id)
);

CREATE TABLE IF NOT EXISTS user_pair_seen (
  user_id INTEGER NOT NULL,
  channel_a_id INTEGER NOT NULL,
  channel_b_id INTEGER NOT NULL,
  seen_at TEXT DEFAULT (datetime('now')),
  PRIMARY KEY (user_id, channel_a_id, channel_b_id)
);

CREATE INDEX IF NOT EXISTS idx_channels_rating ON channels(rating DESC);
CREATE INDEX IF NOT EXISTS idx_votes_user_time ON votes(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS deathmatch_state (
  user_id INTEGER PRIMARY KEY,
  champion_id INTEGER,
  seen_ids TEXT NOT NULL DEFAULT '[]',
  remaining_ids TEXT NOT NULL DEFAULT '[]',
  updated_at TEXT DEFAULT (datetime('now')),
  FOREIGN KEY(user_id) REFERENCES users(id),
  FOREIGN KEY(champion_id) REFERENCES channels(id)
);

CREATE TABLE IF NOT EXISTS deathmatch_votes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  champion_id INTEGER,
  channel_a_id INTEGER NOT NULL,
  channel_b_id INTEGER NOT NULL,
  winner_channel_id INTEGER NOT NULL,
  created_at TEXT DEFAULT (datetime('now')),
  FOREIGN KEY(user_id) REFERENCES users(id),
  FOREIGN KEY(channel_a_id) REFERENCES channels(id),
  FOREIGN KEY(channel_b_id) REFERENCES channels(id),
  FOREIGN KEY(winner_channel_id) REFERENCES channels(id)
);

CREATE TABLE IF NOT EXISTS vote_tokens (
  token TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  vote_type TEXT NOT NULL,
  channel_a_id INTEGER NOT NULL,
  channel_b_id INTEGER NOT NULL,
  consumed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now')),
  consumed_at TEXT,
  FOREIGN KEY(user_id) REFERENCES users(id),
  FOREIGN KEY(channel_a_id) REFERENCES channels(id),
  FOREIGN KEY(channel_b_id) REFERENCES channels(id)
);
"""


class SQLiteDatabase:
    def __init__(self, path: str):
        self.path = path

    async def init(self) -> None:
        async with aiosqlite.connect(self.path) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.executescript(SCHEMA_SQL)
            await self._ensure_user_columns(conn)
            await self._ensure_channel_columns(conn)
            await self._ensure_deathmatch_columns(conn)
            await self._ensure_votes_table(conn)
            await self._ensure_vote_token_columns(conn)
            await conn.commit()

    async def _ensure_user_columns(self, conn: aiosqlite.Connection) -> None:
        for column, definition in (
            ("favorite_channel_id", "INTEGER"),
            ("is_admin", "INTEGER NOT NULL DEFAULT 0"),
            ("reward_stage", "INTEGER NOT NULL DEFAULT 0"),
        ):
            try:
                await conn.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")
            except OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise

    async def _ensure_channel_columns(self, conn: aiosqlite.Connection) -> None:
        for column in ("description", "image_url"):
            try:
                await conn.execute(f"ALTER TABLE channels ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
            except OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise

    async def _ensure_deathmatch_columns(self, conn: aiosqlite.Connection) -> None:
        for column in ("remaining_ids",):
            try:
                await conn.execute(f"ALTER TABLE deathmatch_state ADD COLUMN {column} TEXT NOT NULL DEFAULT '[]'")
            except OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise

    async def _ensure_votes_table(self, conn: aiosqlite.Connection) -> None:
        cur = await conn.execute("PRAGMA table_info(votes)")
        rows = await cur.fetchall()
        winner_col = next((row for row in rows if row["name"] == "winner_channel_id"), None)
        if winner_col and winner_col["notnull"]:
            await conn.execute("ALTER TABLE votes RENAME TO votes_old")
            await conn.execute(
                """
                CREATE TABLE votes (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  channel_a_id INTEGER NOT NULL,
                  channel_b_id INTEGER NOT NULL,
                  winner_channel_id INTEGER,
                  rating_a_before REAL NOT NULL,
                  rating_b_before REAL NOT NULL,
                  rating_a_after REAL NOT NULL,
                  rating_b_after REAL NOT NULL,
                  created_at TEXT DEFAULT (datetime('now')),
                  FOREIGN KEY(user_id) REFERENCES users(id),
                  FOREIGN KEY(channel_a_id) REFERENCES channels(id),
                  FOREIGN KEY(channel_b_id) REFERENCES channels(id)
                )
                """
            )
            await conn.execute(
                """
                INSERT INTO votes(
                  id, user_id, channel_a_id, channel_b_id,
                  winner_channel_id, rating_a_before, rating_b_before,
                  rating_a_after, rating_b_after, created_at
                )
                SELECT
                  id, user_id, channel_a_id, channel_b_id,
                  winner_channel_id, rating_a_before, rating_b_before,
                  rating_a_after, rating_b_after, created_at
                FROM votes_old
                """
            )
            await conn.execute("DROP TABLE votes_old")

    async def _ensure_vote_token_columns(self, conn: aiosqlite.Connection) -> None:
        for column in ("channel_a_id", "channel_b_id"):
            try:
                await conn.execute(
                    f"ALTER TABLE vote_tokens ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0"
                )
            except OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise

    @asynccontextmanager
    async def connect(self):
        conn = await aiosqlite.connect(self.path)
        conn.row_factory = aiosqlite.Row
        try:
            yield conn
        finally:
            await conn.close()


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


class SQLitePlayersRepository(PlayersRepository):
    def __init__(self, db: SQLiteDatabase):
        self._db = db

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

    async def get_classic_games(self, user_id: int) -> int:
        async with self._db.connect() as conn:
            cur = await conn.execute("SELECT COUNT(*) AS c FROM votes WHERE user_id=?", (user_id,))
            row = await cur.fetchone()
        return int(row["c"])

    async def set_favorite(self, user_id: int, channel_id: Optional[int]) -> None:
        async with self._db.connect() as conn:
            await conn.execute(
                "UPDATE users SET favorite_channel_id=? WHERE id=?",
                (channel_id, user_id),
            )
            await conn.commit()

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

    async def get_reward_stage(self, user_id: int) -> int:
        async with self._db.connect() as conn:
            cur = await conn.execute("SELECT reward_stage FROM users WHERE id=?", (user_id,))
            row = await cur.fetchone()
        return int(row["reward_stage"]) if row and row["reward_stage"] is not None else 0

    async def set_reward_stage(self, user_id: int, stage: int) -> None:
        async with self._db.connect() as conn:
            await conn.execute(
                "UPDATE users SET reward_stage=? WHERE id=?",
                (stage, user_id),
            )
            await conn.commit()


class SQLiteStatsRepository(StatsRepository):
    def __init__(self, db: SQLiteDatabase):
        self._db = db

    async def rating_stats(self) -> RatingStats:
        async with self._db.connect() as conn:
            cur = await conn.execute("SELECT COUNT(*) AS c FROM votes")
            games_row = await cur.fetchone()
            cur = await conn.execute("SELECT COUNT(*) AS c FROM users")
            users_row = await cur.fetchone()
        return rating_stats_from_row(
            {"games": games_row["c"], "players": users_row["c"]}
        )

    async def deathmatch_stats(self) -> DeathmatchStats:
        async with self._db.connect() as conn:
            cur = await conn.execute("SELECT COUNT(*) AS c FROM deathmatch_votes")
            games_row = await cur.fetchone()
            cur = await conn.execute("SELECT COUNT(DISTINCT user_id) AS c FROM deathmatch_votes")
            players_row = await cur.fetchone()
        return deathmatch_stats_from_row(
            {"games": games_row["c"], "players": players_row["c"]}
        )


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


class SQLiteVotesRepository(VotesRepository):
    def __init__(self, db: SQLiteDatabase):
        self._db = db

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


class SQLiteDeathmatchRepository(DeathmatchRepository):
    def __init__(self, db: SQLiteDatabase):
        self._db = db

    async def get_state(self, user_id: int) -> Optional[DeathmatchState]:
        async with self._db.connect() as conn:
            cur = await conn.execute(
                "SELECT user_id, champion_id, seen_ids, remaining_ids FROM deathmatch_state WHERE user_id=?",
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
                INSERT INTO deathmatch_state(user_id, champion_id, seen_ids, remaining_ids, updated_at)
                VALUES(?, ?, ?, ?, datetime('now'))
                ON CONFLICT(user_id) DO UPDATE SET
                  champion_id=excluded.champion_id,
                  seen_ids=excluded.seen_ids,
                  remaining_ids=excluded.remaining_ids,
                  updated_at=excluded.updated_at
                """,
                (state.user_id, state.champion_id, seen_payload, remaining_payload),
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


class SQLitePairingRepository(PairingRepository):
    def __init__(self, db: SQLiteDatabase):
        self._db = db

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

    async def has_seen_pair(self, user_id: int, a_id: int, b_id: int) -> bool:
        x, y = (a_id, b_id) if a_id < b_id else (b_id, a_id)
        async with self._db.connect() as conn:
            cur = await conn.execute(
                "SELECT 1 FROM user_pair_seen WHERE user_id=? AND channel_a_id=? AND channel_b_id=?",
                (user_id, x, y),
            )
            row = await cur.fetchone()
        return row is not None

    async def mark_seen(self, user_id: int, a_id: int, b_id: int) -> None:
        x, y = (a_id, b_id) if a_id < b_id else (b_id, a_id)
        async with self._db.connect() as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO user_pair_seen(user_id, channel_a_id, channel_b_id) VALUES(?, ?, ?)",
                (user_id, x, y),
            )
            await conn.commit()
