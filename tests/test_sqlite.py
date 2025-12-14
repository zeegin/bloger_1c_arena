import tempfile
from dataclasses import replace
from pathlib import Path

import unittest

from app.domain.shared.models import Channel
from app.domain.deathmatch.models import DeathmatchState
from app.infrastructure.sqlite import (
    SQLiteChannelsRepository,
    SQLiteDatabase,
    SQLiteDeathmatchRepository,
    SQLitePairingRepository,
    SQLitePlayersRepository,
    SQLiteStatsRepository,
    SQLiteVoteTokensRepository,
    SQLiteVotesRepository,
)
from app.infrastructure.mappers import channel_from_row


class SQLiteRepositoriesTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test.db"
        self.db = SQLiteDatabase(str(self.db_path))
        await self.db.init()
        self.channels = SQLiteChannelsRepository(self.db)
        self.players = SQLitePlayersRepository(self.db)
        self.stats = SQLiteStatsRepository(self.db)
        self.vote_tokens = SQLiteVoteTokensRepository(self.db)
        self.votes = SQLiteVotesRepository(self.db)
        self.deathmatch = SQLiteDeathmatchRepository(self.db)
        self.pairing = SQLitePairingRepository(self.db)

    async def asyncTearDown(self):
        self.tmpdir.cleanup()

    async def _insert_channel(self, title: str, url: str, *, rating: float = 1500.0, games: int = 0) -> Channel:
        await self.channels.add_or_update(tg_url=url, title=title, description="", image_url="")
        async with self.db.connect() as conn:
            await conn.execute(
                "UPDATE channels SET rating=?, games=? WHERE tg_url=?",
                (rating, games, url),
            )
            await conn.commit()
            cur = await conn.execute(
                """
                SELECT id, title, tg_url, description, image_url, rating, games, wins, losses
                FROM channels
                WHERE tg_url=?
                """,
                (url,),
            )
            row = await cur.fetchone()
        return channel_from_row(dict(row))

    async def _create_user(self, tg_id: int = 100) -> int:
        return await self.players.upsert(tg_user_id=tg_id, username="user", first_name="User")

    async def test_channels_add_get_and_delete(self):
        await self.channels.add_or_update(
            tg_url="https://t.me/alpha",
            title="Alpha",
            description="desc",
            image_url="img",
        )
        await self.channels.add_or_update(
            tg_url="https://t.me/beta",
            title="Beta",
            description="",
            image_url="",
        )

        listed = await self.channels.list_all()
        self.assertEqual(len(listed), 2)
        alpha = await self.channels.get(listed[0].id)
        self.assertEqual(alpha.title, listed[0].title)

        await self.channels.add_or_update(
            tg_url="https://t.me/alpha",
            title="Alpha Updated",
            description="new",
            image_url="img2",
        )
        updated = await self.channels.get(alpha.id)
        self.assertEqual(updated.title, "Alpha Updated")
        self.assertEqual(updated.description, "new")

        deleted = await self.channels.delete_not_in({"https://t.me/alpha"})
        self.assertEqual(deleted, 1)
        remaining = await self.channels.list_all()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].tg_url, "https://t.me/alpha")

    async def test_players_upsert_favorite_and_games(self):
        channel = await self._insert_channel("Alpha", "https://t.me/alpha")
        user_id = await self._create_user()
        same_user_id = await self.players.upsert(tg_user_id=100, username="new", first_name="Updated")
        self.assertEqual(user_id, same_user_id)

        self.assertEqual(await self.players.get_reward_stage(user_id), 0)
        await self.players.set_reward_stage(user_id, 350)
        self.assertEqual(await self.players.get_reward_stage(user_id), 350)
        self.assertFalse(await self.players.is_deathmatch_unlocked(user_id))
        await self.players.mark_deathmatch_unlocked(user_id)
        self.assertTrue(await self.players.is_deathmatch_unlocked(user_id))

        await self.players.set_favorite(user_id, channel.id)
        favorite = await self.players.get_favorite(user_id)
        self.assertEqual(favorite.id, channel.id)

        games = await self.players.get_classic_games(user_id)
        self.assertEqual(games, 0)

        opponent = await self._insert_channel("Beta", "https://t.me/beta")
        async with self.db.connect() as conn:
            await conn.execute(
                """
                INSERT INTO votes(
                  user_id, channel_a_id, channel_b_id, winner_channel_id,
                  rating_a_before, rating_b_before, rating_a_after, rating_b_after
                )
                VALUES(?, ?, ?, ?, 1500, 1500, 1510, 1490)
                """,
                (user_id, channel.id, opponent.id, channel.id),
            )
            await conn.commit()

        self.assertEqual(await self.players.get_classic_games(user_id), 1)
        self.assertEqual(await self.players.get_draw_count(user_id), 0)

        async with self.db.connect() as conn:
            await conn.execute(
                """
                INSERT INTO votes(
                  user_id, channel_a_id, channel_b_id, winner_channel_id,
                  rating_a_before, rating_b_before, rating_a_after, rating_b_after
                )
                VALUES(?, ?, ?, NULL, 1500, 1500, 1505, 1495)
                """,
                (user_id, channel.id, opponent.id),
            )
            await conn.execute(
                """
                INSERT INTO deathmatch_votes(user_id, champion_id, channel_a_id, channel_b_id, winner_channel_id)
                VALUES(?, ?, ?, ?, ?)
                """,
                (user_id, None, channel.id, opponent.id, channel.id),
            )
            await conn.commit()

        self.assertEqual(await self.players.get_draw_count(user_id), 1)
        self.assertEqual(await self.players.get_deathmatch_game_count(user_id), 1)

    async def test_stats_repository_counts_games_and_players(self):
        user_a = await self._create_user(100)
        user_b = await self._create_user(101)
        channel_a = await self._insert_channel("Alpha", "https://t.me/alpha")
        channel_b = await self._insert_channel("Beta", "https://t.me/beta")
        async with self.db.connect() as conn:
            for user_id in (user_a, user_b):
                await conn.execute(
                    """
                    INSERT INTO votes(
                      user_id, channel_a_id, channel_b_id, winner_channel_id,
                      rating_a_before, rating_b_before, rating_a_after, rating_b_after
                    )
                    VALUES(?, ?, ?, ?, 1500, 1500, 1510, 1490)
                    """,
                    (user_id, channel_a.id, channel_b.id, channel_a.id),
                )
            await conn.execute(
                """
                INSERT INTO deathmatch_votes(user_id, champion_id, channel_a_id, channel_b_id, winner_channel_id)
                VALUES(?, ?, ?, ?, ?), (?, ?, ?, ?, ?)
                """,
                (
                    user_a,
                    None,
                    channel_a.id,
                    channel_b.id,
                    channel_a.id,
                    user_b,
                    channel_b.id,
                    channel_a.id,
                    channel_b.id,
                    channel_b.id,
                ),
            )
            await conn.commit()

        rating_stats = await self.stats.rating_stats()
        self.assertEqual(rating_stats.games, 2)
        self.assertEqual(rating_stats.players, 2)

        deathmatch_stats = await self.stats.deathmatch_stats()
        self.assertEqual(deathmatch_stats.games, 2)
        self.assertEqual(deathmatch_stats.players, 2)

    async def test_vote_tokens_create_and_consume(self):
        user_id = await self._create_user()
        channel_a = await self._insert_channel("Alpha", "https://t.me/alpha")
        channel_b = await self._insert_channel("Beta", "https://t.me/beta")
        token = await self.vote_tokens.create(
            user_id,
            "classic",
            channel_a_id=channel_a.id,
            channel_b_id=channel_b.id,
        )
        self.assertTrue(
            await self.vote_tokens.consume(
                token,
                user_id=user_id,
                vote_type="classic",
                channel_a_id=channel_a.id,
                channel_b_id=channel_b.id,
            )
        )
        self.assertFalse(
            await self.vote_tokens.consume(
                token,
                user_id=user_id,
                vote_type="classic",
                channel_a_id=channel_a.id,
                channel_b_id=channel_b.id,
            )
        )
        swapped_attempt = await self.vote_tokens.create(
            user_id,
            "classic",
            channel_a_id=channel_a.id,
            channel_b_id=channel_b.id,
        )
        self.assertFalse(
            await self.vote_tokens.consume(
                swapped_attempt,
                user_id=user_id,
                vote_type="classic",
                channel_a_id=channel_b.id,
                channel_b_id=channel_a.id,
            )
        )
        active = await self.vote_tokens.get_active(user_id, "classic")
        self.assertIsNotNone(active)
        self.assertEqual(active.channel_a_id, channel_a.id)
        await self.vote_tokens.invalidate(user_id, "classic")
        self.assertIsNone(await self.vote_tokens.get_active(user_id, "classic"))

    async def test_votes_repository_records_and_updates_channels(self):
        channel_a = await self._insert_channel("Alpha", "https://t.me/alpha", rating=1500, games=10)
        channel_b = await self._insert_channel("Beta", "https://t.me/beta", rating=1500, games=8)
        user_id = await self._create_user()

        updated_a = replace(channel_a, rating=1512.0, games=11, wins=channel_a.wins + 1)
        updated_b = replace(channel_b, rating=1488.0, games=9, losses=channel_b.losses + 1)

        await self.votes.record_vote(
            user_id=user_id,
            channel_a_before=channel_a,
            channel_b_before=channel_b,
            channel_a_after=updated_a,
            channel_b_after=updated_b,
            winner_channel_id=channel_a.id,
            draw=False,
        )

        async with self.db.connect() as conn:
            cur = await conn.execute("SELECT COUNT(*) AS c FROM votes WHERE user_id=?", (user_id,))
            vote_count = (await cur.fetchone())["c"]
            cur = await conn.execute("SELECT rating, games FROM channels WHERE id=?", (channel_a.id,))
            a_row = await cur.fetchone()
            cur = await conn.execute("SELECT rating, games FROM channels WHERE id=?", (channel_b.id,))
            b_row = await cur.fetchone()

        self.assertEqual(vote_count, 1)
        self.assertAlmostEqual(a_row["rating"], 1512.0)
        self.assertEqual(a_row["games"], 11)
        self.assertAlmostEqual(b_row["rating"], 1488.0)
        self.assertEqual(b_row["games"], 9)

    async def test_deathmatch_repository_state_and_logs(self):
        user_id = await self._create_user()
        champion = await self._insert_channel("Alpha", "https://t.me/alpha")
        opponent = await self._insert_channel("Beta", "https://t.me/beta")
        state = DeathmatchState(
            user_id=user_id,
            champion_id=champion.id,
            seen_ids=(champion.id,),
            remaining_ids=(opponent.id,),
            rounds_played=0,
            round_total=1,
        )

        self.assertIsNone(await self.deathmatch.get_state(user_id))
        await self.deathmatch.save_state(state)
        loaded = await self.deathmatch.get_state(user_id)
        self.assertEqual(loaded.champion_id, champion.id)
        await self.deathmatch.delete_state(user_id)
        self.assertIsNone(await self.deathmatch.get_state(user_id))

        await self.deathmatch.log_vote(
            user_id=user_id,
            champion_id=champion.id,
            channel_a_id=champion.id,
            channel_b_id=opponent.id,
            winner_id=champion.id,
        )
        async with self.db.connect() as conn:
            cur = await conn.execute("SELECT COUNT(*) AS c FROM deathmatch_votes WHERE user_id=?", (user_id,))
            self.assertEqual((await cur.fetchone())["c"], 1)

    async def test_pairing_repository_fetches_and_tracks_pairs(self):
        channel_a = await self._insert_channel("Alpha", "https://t.me/alpha", games=1, rating=1400)
        channel_b = await self._insert_channel("Beta", "https://t.me/beta", games=5, rating=1500)
        channel_c = await self._insert_channel("Gamma", "https://t.me/gamma", games=2, rating=1405)

        pool = await self.pairing.fetch_low_game_pool(limit=2)
        self.assertEqual(len(pool), 2)

        closest = await self.pairing.fetch_closest(channel_a.id, channel_a.rating, limit=2)
        self.assertTrue(all(ch.id != channel_a.id for ch in closest))
        self.assertEqual(closest[0].id, channel_c.id)

        user_id = 999
        self.assertFalse(await self.pairing.has_seen_pair(user_id, channel_a.id, channel_b.id))
        await self.pairing.mark_seen(user_id, channel_b.id, channel_a.id)
        self.assertTrue(await self.pairing.has_seen_pair(user_id, channel_a.id, channel_b.id))
