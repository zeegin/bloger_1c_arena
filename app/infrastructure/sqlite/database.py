from __future__ import annotations

from contextlib import asynccontextmanager

import aiosqlite
from aiosqlite import OperationalError

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tg_user_id INTEGER UNIQUE NOT NULL,
  username TEXT,
  first_name TEXT,
  reward_stage INTEGER NOT NULL DEFAULT 0,
  deathmatch_unlocked INTEGER NOT NULL DEFAULT 0,
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
  round_total INTEGER NOT NULL DEFAULT 20,
  rounds_played INTEGER NOT NULL DEFAULT 0,
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
            ("deathmatch_unlocked", "INTEGER NOT NULL DEFAULT 0"),
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
        for column, definition in (
            ("remaining_ids", "TEXT NOT NULL DEFAULT '[]'"),
            ("round_total", "INTEGER NOT NULL DEFAULT 20"),
            ("rounds_played", "INTEGER NOT NULL DEFAULT 0"),
        ):
            try:
                await conn.execute(f"ALTER TABLE deathmatch_state ADD COLUMN {column} {definition}")
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
