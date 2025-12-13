import unittest

from app.application.presenters import BotPresenter
from app.application.workflow import BotWorkflow
from app.domain.arena import DuelPair
from app.domain.deathmatch import (
    DeathmatchRound,
    DeathmatchStartResult,
    DeathmatchStartStatus,
    DeathmatchVoteResult,
    DeathmatchVoteStatus,
)
from app.domain.models import Channel, DeathmatchStats, FavoriteChannelInfo, RatingStats
from app.domain.players import RewardGrant
from app.application.queries.rating import FavoritesSummary, OrderedListing, TopEntry, TopListing, WeightedEntry


def make_channel(
    idx: int,
    title: str,
    *,
    rating: float = 1500.0,
    games: int = 10,
    description: str = "",
) -> Channel:
    return Channel(
        id=idx,
        title=title,
        tg_url=f"https://t.me/{title.lower()}",
        description=description,
        image_url="",
        rating=rating,
        games=games,
        wins=games // 2,
        losses=games // 2,
    )


def to_top_entry(channel: Channel) -> TopEntry:
    return TopEntry(
        title=channel.title,
        tg_url=channel.tg_url,
        rating=channel.rating,
        games=channel.games,
        wins=channel.wins,
    )


class FakeArena:
    def __init__(self):
        self.duel: DuelPair | None = None
        self.rating_label = "1200-1400"
        self.apply_result = True
        self.prepare_calls: list[int] = []
        self.apply_calls: list[tuple[int, str, int, int, str]] = []
        self.rating_range_calls: list[tuple[float, float]] = []

    async def prepare_duel(self, user_id: int):
        self.prepare_calls.append(user_id)
        return self.duel

    async def apply_vote(self, user_id: int, token: str, a_id: int, b_id: int, winner: str):
        self.apply_calls.append((user_id, token, a_id, b_id, winner))
        return self.apply_result

    def rating_range(self, a_rating: float, b_rating: float) -> str:
        self.rating_range_calls.append((a_rating, b_rating))
        return self.rating_label


class FakeRating:
    def __init__(self):
        self.top_listing_result = None
        self.ordered_listing_result = None
        self.weighted_entries = []
        self.favorites_summary_result = None
        self.last_top_limit: int | None = None
        self.last_ordered_limit: int | None = None
        self.weighted_limit: int | None = None

    async def top_listing(self, limit: int):
        self.last_top_limit = limit
        return self.top_listing_result

    async def ordered_listing(self, limit: int = 100):
        self.last_ordered_limit = limit
        return self.ordered_listing_result

    async def weighted_top(self, limit: int = 100):
        self.weighted_limit = limit
        return list(self.weighted_entries)

    async def favorites_summary(self):
        return self.favorites_summary_result


class FakePlayers:
    def __init__(self):
        self.favorite_channel: Channel | None = None
        self.classic_games = 0
        self.reward_stage = 0
        self.last_claim_thresholds = None

    async def get_favorite_channel(self, user_id: int):
        return self.favorite_channel

    async def get_classic_game_count(self, user_id: int):
        return self.classic_games

    async def get_reward_stage(self, user_id: int):
        return self.reward_stage

    async def set_reward_stage(self, user_id: int, stage: int):
        self.reward_stage = stage

    async def claim_reward(self, user_id: int, thresholds):
        self.last_claim_thresholds = thresholds
        for threshold in thresholds:
            if self.reward_stage >= threshold.limit:
                continue
            if self.classic_games >= threshold.limit:
                self.reward_stage = threshold.limit
                return RewardGrant(games=self.classic_games, url=threshold.url)
        return None


class FakeDeathmatch:
    def __init__(self):
        self._min_games = 3
        self.start_result = DeathmatchStartResult(status=DeathmatchStartStatus.NOT_ENOUGH_CHANNELS)
        self.vote_result = DeathmatchVoteResult(status=DeathmatchVoteStatus.STATE_MISSING)
        self.start_calls: list[int] = []
        self.vote_calls: list[tuple[int, str, int, int, str]] = []

    @property
    def min_classic_games(self):
        return self._min_games

    @min_classic_games.setter
    def min_classic_games(self, value: int):
        self._min_games = value

    async def request_start(self, user_id: int):
        self.start_calls.append(user_id)
        return self.start_result

    async def process_vote(self, user_id: int, token: str, a_id: int, b_id: int, winner: str):
        self.vote_calls.append((user_id, token, a_id, b_id, winner))
        return self.vote_result


class BotWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.arena = FakeArena()
        self.rating_queries = FakeRating()
        self.players = FakePlayers()
        self.deathmatch = FakeDeathmatch()
        presenter = BotPresenter()
        self.workflow = BotWorkflow(
            arena=self.arena,
            rating_queries=self.rating_queries,
            players=self.players,
            deathmatch=self.deathmatch,
            presenter=presenter,
            top_limit=5,
        )

    async def test_duel_page_renders_channels_and_buttons(self):
        channel_a = make_channel(1, "Alpha", description="Desc A")
        channel_b = make_channel(2, "Beta", description="Desc B")
        self.arena.duel = DuelPair(channel_a=channel_a, channel_b=channel_b, token="token123", rating_band="1200-1400")

        page = await self.workflow.duel_page(user_id=10)

        self.assertIn("Alpha", page.text)
        self.assertIn("Beta", page.text)
        self.assertIn(self.arena.rating_label, page.text)
        self.assertEqual(len(page.media), 1)
        self.assertEqual(page.media[0].channels, (channel_a, channel_b))
        self.assertEqual(page.buttons[0][0].callback_data, f"vote:token123:{channel_a.id}:{channel_b.id}:A")

    async def test_duel_page_requires_two_channels(self):
        self.arena.duel = None

        page = await self.workflow.duel_page(user_id=3)

        self.assertIn("Нужно минимум 2 канала", page.text)
        self.assertEqual(page.buttons[0][0].callback_data, "menu:play")

    async def test_top_page_includes_stats_and_navigation_buttons(self):
        channel_a = make_channel(1, "Alpha")
        channel_b = make_channel(2, "Beta")
        entries = [to_top_entry(channel_a), to_top_entry(channel_b)]
        stats = RatingStats(games=42, players=11)
        self.rating_queries.top_listing_result = TopListing(entries=entries, stats=stats)

        page = await self.workflow.top_page()

        self.assertIn("Alpha", page.text)
        self.assertIn("Beta", page.text)
        self.assertIn("42", page.text)
        self.assertIn("11", page.text)
        self.assertEqual(self.rating_queries.last_top_limit, self.workflow.top_limit)
        self.assertEqual(page.buttons[0][0].callback_data, "top:100")
        self.assertEqual(page.buttons[1][0].callback_data, "top:winrate")
        self.assertEqual(page.buttons[-1][0].callback_data, "menu:deathmatch")

    async def test_favorites_page_lists_fans_and_user_favorite(self):
        favorite_info = FavoriteChannelInfo(id=5, title="Gamma", tg_url="https://t.me/gamma", fans=12)
        self.rating_queries.favorites_summary_result = FavoritesSummary(
            favorites=[favorite_info],
            stats=DeathmatchStats(games=7, players=2),
        )
        self.players.favorite_channel = make_channel(99, "PersonalFav")

        page = await self.workflow.favorites_page(user_id=50)

        self.assertIn("Gamma", page.text)
        self.assertIn("12", page.text)
        self.assertIn("Твой любимчик", page.text)

    async def test_process_vote_rejects_duplicate_tokens(self):
        self.arena.apply_result = False

        page = await self.workflow.process_vote(1, token="token", a_id=1, b_id=2, winner="A")

        self.assertIn("Голос уже учтён", page.text)
        self.assertEqual(len(self.arena.apply_calls), 1)

    async def test_process_vote_returns_new_duel_after_success(self):
        channel_a = make_channel(1, "Alpha")
        channel_b = make_channel(2, "Beta")
        self.arena.duel = DuelPair(channel_a=channel_a, channel_b=channel_b, token="fresh", rating_band="1000-1200")
        self.arena.apply_result = True

        page = await self.workflow.process_vote(15, token="token", a_id=1, b_id=2, winner="A")

        self.assertEqual(self.arena.apply_calls[-1], (15, "token", 1, 2, "A"))
        self.assertIn("Alpha", page.text)
        self.assertEqual(page.media[0].channels, (channel_a, channel_b))

    async def test_process_vote_returns_reward_page_when_threshold_reached(self):
        self.workflow.reward_350_url = "https://secret/350"
        self.players.classic_games = 350
        self.players.reward_stage = 0
        self.arena.apply_result = True

        page = await self.workflow.process_vote(20, token="token", a_id=1, b_id=2, winner="A")

        self.assertIn("секретный подарок", page.text.lower())
        self.assertIn("https://secret/350", page.text)
        self.assertEqual(self.players.reward_stage, 350)
        self.assertEqual(self.arena.prepare_calls, [])

    async def test_process_vote_skips_reward_if_url_missing(self):
        self.workflow.reward_350_url = None
        self.players.classic_games = 350
        self.players.reward_stage = 0
        channel_a = make_channel(1, "Alpha")
        channel_b = make_channel(2, "Beta")
        self.arena.duel = DuelPair(channel_a=channel_a, channel_b=channel_b, token="fresh", rating_band="1000-1200")
        self.arena.apply_result = True

        page = await self.workflow.process_vote(21, token="token", a_id=1, b_id=2, winner="B")

        self.assertNotIn("секретный подарок", page.text.lower())
        self.assertEqual(self.players.reward_stage, 0)
        self.assertIn("Alpha", page.text)
        self.assertEqual(page.media[0].channels, (channel_a, channel_b))

    async def test_start_deathmatch_requires_more_games(self):
        self.deathmatch.min_classic_games = 10
        self.deathmatch.start_result = DeathmatchStartResult(
            status=DeathmatchStartStatus.NEED_CLASSIC_GAMES,
            remaining_games=3,
        )

        page = await self.workflow.start_deathmatch(user_id=88)

        self.assertIn("осталось сыграть", page.text.lower())
        self.assertIn("3", page.text)

    async def test_process_deathmatch_vote_finished_announces_champion(self):
        champion = make_channel(7, "Omega")
        self.deathmatch.vote_result = DeathmatchVoteResult(
            status=DeathmatchVoteStatus.FINISHED,
            champion=champion,
        )

        page = await self.workflow.process_deathmatch_vote(9, token="dm", a_id=1, b_id=2, winner="A")

        self.assertIn("Deathmatch завершён", page.text)
        self.assertIn("Omega", page.text)

    async def test_process_deathmatch_vote_next_round_builds_page(self):
        champion = make_channel(1, "Champion", description="Strong")
        contender = make_channel(2, "Challenger", description="Brave")
        round_info = DeathmatchRound(current=champion, opponent=contender, token="round1", initial=False)
        self.deathmatch.vote_result = DeathmatchVoteResult(
            status=DeathmatchVoteStatus.NEXT_ROUND,
            round=round_info,
        )

        page = await self.workflow.process_deathmatch_vote(5, token="dm", a_id=1, b_id=2, winner="A")

        self.assertIn("Deathmatch продолжается", page.text)
        self.assertIn("Challenger", page.text)
        self.assertEqual(len(page.media), 1)
        self.assertEqual(page.media[0].channels, (champion, contender))

    async def test_weighted_top_page_sorts_by_win_rate(self):
        self.rating_queries.weighted_entries = [
            WeightedEntry(title="Alpha", tg_url="https://t.me/alpha", wins=9, games=10, rate_percent=90.0),
            WeightedEntry(title="Beta", tg_url="https://t.me/beta", wins=9, games=30, rate_percent=30.0),
        ]

        page = await self.workflow.weighted_top_page()

        self.assertIn("на отношении побед к играм", page.text.lower())
        first_entry = page.text.splitlines()[3]
        self.assertIn("Alpha", first_entry)
        self.assertIn("%", first_entry)
        self.assertEqual(page.buttons[0][0].callback_data, "top:back")


if __name__ == "__main__":
    unittest.main()
