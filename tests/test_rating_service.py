import unittest

from app.application.queries.rating import RatingQueryService
from app.domain.models import Channel, DeathmatchStats, RatingStats
from app.domain.rating import RatingService


def make_channel(idx: int, title: str, *, rating: float = 1500.0, games: int = 10, wins: int = 5) -> Channel:
    return Channel(
        id=idx,
        title=title,
        tg_url=f"https://t.me/{title.lower()}",
        description="",
        image_url="",
        rating=rating,
        games=games,
        wins=wins,
        losses=max(0, games - wins),
    )


class FakeChannelsRepo:
    def __init__(self):
        self.top = []
        self.all = []
        self.favorites = []

    async def list_top(self, limit: int):
        return list(self.top[:limit])

    async def list_all(self):
        return list(self.all)

    async def list_favorites(self):
        return list(self.favorites)


class FakeStatsRepo:
    def __init__(self):
        self.rating_stats_value = RatingStats(games=0, players=0)
        self.dm_stats_value = DeathmatchStats(games=0, players=0)

    async def rating_stats(self):
        return self.rating_stats_value

    async def deathmatch_stats(self):
        return self.dm_stats_value


class RatingServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.channels = FakeChannelsRepo()
        self.stats = FakeStatsRepo()
        self.service = RatingService(self.channels, self.stats)
        self.queries = RatingQueryService(self.service)

    async def test_top_listing_returns_entries_and_stats(self):
        self.channels.top = [make_channel(1, "Alpha"), make_channel(2, "Beta")]
        self.stats.rating_stats_value = RatingStats(games=42, players=10)

        listing = await self.queries.top_listing(limit=5)

        self.assertIsNotNone(listing)
        self.assertEqual(len(listing.entries), 2)
        self.assertEqual(listing.stats.games, 42)

    async def test_weighted_top_sorts_by_win_rate(self):
        alpha = make_channel(1, "Alpha", games=10, wins=9)
        beta = make_channel(2, "Beta", games=20, wins=5)
        self.channels.all = [beta, alpha]

        entries = await self.queries.weighted_top()

        self.assertEqual(entries[0].title, "Alpha")
        self.assertAlmostEqual(entries[0].rate_percent, 90.0)

    async def test_favorites_summary_none_when_no_favorites(self):
        summary = await self.queries.favorites_summary()
        self.assertIsNone(summary)

    async def test_list_top_channels_exposes_raw_channels(self):
        ch = make_channel(1, "Alpha")
        self.channels.top = [ch]

        result = await self.service.list_top_channels(5)

        self.assertEqual(result, [ch])
