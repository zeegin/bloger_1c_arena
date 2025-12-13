import unittest

from app.application.presenters import BotPresenter
from app.application.queries.rating import FavoritesSummary, TopEntry, TopListing, WeightedEntry
from app.domain.arena import DuelPair
from app.domain.deathmatch import DeathmatchRound
from app.domain.models import Channel, DeathmatchStats, FavoriteChannelInfo, RatingStats


def make_channel(idx: int, title: str, description: str = "") -> Channel:
    return Channel(
        id=idx,
        title=title,
        tg_url=f"https://t.me/{title.lower()}",
        description=description,
        image_url="",
        rating=1500.0,
        games=10,
        wins=5,
        losses=5,
    )


class BotPresenterTests(unittest.TestCase):
    def setUp(self):
        self.presenter = BotPresenter()

    def test_duel_page_renders_rating_band(self):
        duel = DuelPair(
            channel_a=make_channel(1, "Alpha", "Desc A"),
            channel_b=make_channel(2, "Beta", "Desc B"),
            token="token123",
            rating_band="1200-1400",
        )

        page = self.presenter.duel_page(duel)

        self.assertIn("1200-1400", page.text)
        self.assertIn("Alpha", page.text)
        self.assertIn("Beta", page.text)

    def test_top_page_displays_entries_and_stats(self):
        listing = TopListing(
            entries=[
                TopEntry(title="Alpha", tg_url="https://a", rating=1500, games=10, wins=5),
                TopEntry(title="Beta", tg_url="https://b", rating=1400, games=20, wins=8),
            ],
            stats=RatingStats(games=30, players=11),
        )

        page = self.presenter.top_page(listing)

        self.assertIn("Alpha", page.text)
        self.assertIn("Beta", page.text)
        self.assertIn("30", page.text)
        self.assertIn("11", page.text)

    def test_weighted_page_lists_percentages(self):
        entries = [
            WeightedEntry(title="Alpha", tg_url="https://a", wins=9, games=10, rate_percent=90.0),
            WeightedEntry(title="Beta", tg_url="https://b", wins=5, games=20, rate_percent=25.0),
        ]

        page = self.presenter.weighted_top_page(entries)

        self.assertIn("90.0%", page.text)
        self.assertIn("Alpha", page.text)

    def test_favorites_page_shows_stats_and_user_favorite(self):
        summary = FavoritesSummary(
            favorites=[FavoriteChannelInfo(id=1, title="Alpha", tg_url="https://a", fans=3)],
            stats=DeathmatchStats(games=5, players=2),
        )
        user_favorite = make_channel(7, "Beta")

        page = self.presenter.favorites_page(summary, user_favorite)

        self.assertIn("Alpha", page.text)
        self.assertIn("Beta", page.text)
        self.assertIn("5", page.text)

    def test_deathmatch_round_template(self):
        round_info = DeathmatchRound(
            current=make_channel(1, "Champion", "Strong"),
            opponent=make_channel(2, "Challenger", "Brave"),
            token="round1",
            initial=False,
        )

        page = self.presenter.deathmatch_round_page(round_info)

        self.assertIn("Deathmatch продолжается", page.text)
        self.assertIn("Challenger", page.text)
        self.assertEqual(len(page.media), 1)
