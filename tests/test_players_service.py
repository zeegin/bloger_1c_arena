import unittest

from app.domain.players import PlayersService, RewardGrant, RewardThreshold


class FakePlayersRepo:
    def __init__(self):
        self.games = {}
        self.draws = {}
        self.reward_stage = {}
        self.favorites = {}
        self.deathmatch_games = {}
        self.dm_unlocked = set()
        self.rating_unlocked = set()

    async def upsert(self, tg_user_id, username, first_name):
        return tg_user_id

    async def get_classic_games(self, user_id):
        return self.games.get(user_id, 0)

    async def get_draw_count(self, user_id):
        return self.draws.get(user_id, 0)

    async def get_favorite(self, user_id):
        return self.favorites.get(user_id)

    async def set_favorite(self, user_id, channel_id):
        self.favorites[user_id] = channel_id

    async def get_reward_stage(self, user_id):
        return self.reward_stage.get(user_id, 0)

    async def set_reward_stage(self, user_id, stage):
        self.reward_stage[user_id] = stage

    async def is_deathmatch_unlocked(self, user_id):
        return False

    async def mark_deathmatch_unlocked(self, user_id):
        pass

    async def get_deathmatch_games(self, user_id):
        return self.deathmatch_games.get(user_id, 0)

    async def is_deathmatch_unlocked(self, user_id):
        return user_id in self.dm_unlocked

    async def mark_deathmatch_unlocked(self, user_id):
        self.dm_unlocked.add(user_id)

    async def has_rating_unlocked(self, user_id):
        return user_id in self.rating_unlocked

    async def mark_rating_unlocked(self, user_id):
        self.rating_unlocked.add(user_id)


class PlayersServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.repo = FakePlayersRepo()
        self.service = PlayersService(self.repo)

    async def test_claim_reward_when_threshold_met(self):
        self.repo.games[1] = 400
        thresholds = [
            RewardThreshold(limit=350, url="https://350"),
            RewardThreshold(limit=700, url="https://700"),
        ]
        reward = await self.service.claim_reward(1, thresholds)
        self.assertIsInstance(reward, RewardGrant)
        self.assertEqual(reward.url, "https://350")
        self.assertEqual(self.repo.reward_stage[1], 350)

    async def test_claim_reward_skips_when_not_enough_games(self):
        self.repo.games[1] = 100
        thresholds = [RewardThreshold(limit=350, url="https://350")]
        reward = await self.service.claim_reward(1, thresholds)
        self.assertIsNone(reward)

    async def test_claim_reward_skips_when_already_claimed(self):
        self.repo.games[1] = 800
        self.repo.reward_stage[1] = 700
        thresholds = [RewardThreshold(limit=350, url="https://350"), RewardThreshold(limit=700, url="https://700")]
        reward = await self.service.claim_reward(1, thresholds)
        self.assertIsNone(reward)

    async def test_rating_unlocked_cached(self):
        self.assertFalse(await self.service.has_rating_unlocked(5))
        await self.service.mark_rating_unlocked(5)
        self.assertTrue(await self.service.has_rating_unlocked(5))
