import unittest
from typing import Callable
from unittest.mock import patch

from app.domain.arena import PairingPolicy
from app.domain.shared.models import Channel


def make_channel(idx: int, title: str, rating: float = 1500.0) -> Channel:
    return Channel(
        id=idx,
        title=title,
        tg_url=f"https://t.me/{title.lower()}",
        description="",
        image_url="",
        rating=rating,
        games=10,
        wins=5,
        losses=5,
    )


class FakePairingRepo:
    def __init__(self):
        self.pool: list[Channel] = []
        self.closest: dict[int, list[Channel]] = {}
        self.seen_pairs: set[tuple[int, int, int]] = set()
        self.marked_pairs: list[tuple[int, int, int]] = []
        self.has_seen_override: Callable[[int, int, int], bool] | None = None
        self.has_seen_calls: list[tuple[int, int, int]] = []

    async def fetch_low_game_pool(self, limit: int):
        return list(self.pool[:limit])

    async def fetch_closest(self, channel_id: int, rating: float, limit: int):
        return list(self.closest.get(channel_id, [])[:limit])

    async def has_seen_pair(self, user_id: int, a_id: int, b_id: int):
        self.has_seen_calls.append((user_id, a_id, b_id))
        if self.has_seen_override:
            return self.has_seen_override(user_id, a_id, b_id)
        return (user_id, a_id, b_id) in self.seen_pairs

    async def mark_seen(self, user_id: int, a_id: int, b_id: int):
        self.marked_pairs.append((user_id, a_id, b_id))
        self.seen_pairs.add((user_id, a_id, b_id))


class PairingPolicyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.repo = FakePairingRepo()
        self.policy = PairingPolicy(repo=self.repo)

    async def test_returns_none_when_pool_too_small(self):
        result = await self.policy.get_pair(user_id=42)
        self.assertIsNone(result)

    async def test_returns_unseen_pair_and_marks_it(self):
        a = make_channel(1, "Alpha")
        b = make_channel(2, "Beta")
        self.repo.pool = [a, b]
        self.repo.closest = {1: [b], 2: [a]}

        with patch("app.domain.arena.services.pairing_policy.random.choice", side_effect=lambda seq: seq[0]):
            pair = await self.policy.get_pair(user_id=7)

        self.assertEqual(pair, (a, b))
        self.assertEqual(self.repo.marked_pairs, [(7, 1, 2)])

    async def test_fallback_after_retries_returns_pair(self):
        a = make_channel(1, "Alpha")
        b = make_channel(2, "Beta")
        self.repo.pool = [a, b]
        self.repo.closest = {1: [b], 2: [a]}
        self.repo.has_seen_override = lambda *_: True

        with patch("app.domain.arena.services.pairing_policy.random.choice", side_effect=lambda seq: seq[0]):
            pair = await self.policy.get_pair(user_id=9)

        self.assertEqual(pair, (a, b))
        self.assertEqual(self.repo.marked_pairs[-1], (9, 1, 2))
        self.assertGreaterEqual(len(self.repo.has_seen_calls), 30)

    async def test_fallback_returns_none_when_no_candidates(self):
        a = make_channel(1, "Alpha")
        self.repo.pool = [a, make_channel(3, "Gamma")]
        self.repo.closest = {1: []}
        self.repo.has_seen_override = lambda *_: True

        with patch("app.domain.arena.services.pairing_policy.random.choice", side_effect=lambda seq: seq[0]):
            result = await self.policy.get_pair(user_id=12)

        self.assertIsNone(result)
