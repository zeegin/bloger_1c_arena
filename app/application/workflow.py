from __future__ import annotations

from dataclasses import dataclass

from ..domain.arena import ArenaService
from ..domain.deathmatch import DeathmatchService, DeathmatchStartStatus, DeathmatchVoteStatus
from ..domain.players import PlayersService, RewardThreshold
from .queries.rating import RatingQueryService
from .pages import Page
from .presenters import BotPresenter


@dataclass
class BotWorkflow:
    arena: ArenaService
    rating_queries: RatingQueryService
    players: PlayersService
    deathmatch: DeathmatchService
    presenter: BotPresenter
    top_limit: int
    reward_350_url: str | None = None
    reward_700_url: str | None = None

    async def start_page(self) -> Page:
        return self.presenter.start_page()

    async def duel_page(self, user_id: int) -> Page:
        duel = await self.arena.prepare_duel(user_id)
        if not duel:
            return self.presenter.duel_unavailable()
        return self.presenter.duel_page(duel)

    async def top_page(self, user_id: int | None = None) -> Page:
        listing = await self.rating_queries.top_listing(self.top_limit)
        if not listing:
            return self.presenter.top_empty()
        player_stats = None
        if user_id is not None:
            games = await self.players.get_classic_game_count(user_id)
            draws = await self.players.get_draw_count(user_id)
            player_stats = {"classic_games": games, "draws": draws}
        return self.presenter.top_page(listing, player_stats=player_stats)

    async def top100_page(self) -> Page:
        ordered = await self.rating_queries.ordered_listing(100)
        if not ordered:
            return self.presenter.top_empty()
        return self.presenter.top100_page(ordered.entries, show_all=ordered.show_all)

    async def weighted_top_page(self) -> Page:
        entries = await self.rating_queries.weighted_top()
        if not entries:
            return self.presenter.weighted_top_empty()
        return self.presenter.weighted_top_page(entries)

    async def favorites_page(self, user_id: int) -> Page:
        summary = await self.rating_queries.favorites_summary()
        if not summary:
            return self.presenter.favorites_empty()
        favorite = await self.players.get_favorite_channel(user_id)
        dm_games = await self.players.get_deathmatch_game_count(user_id)
        return self.presenter.favorites_page(summary, favorite, player_dm_games=dm_games)

    async def start_deathmatch(self, user_id: int) -> Page:
        if await self.deathmatch.has_active_round(user_id):
            return self.presenter.deathmatch_resume_prompt()
        result = await self.deathmatch.request_start(user_id)
        if result.status == DeathmatchStartStatus.NEED_CLASSIC_GAMES:
            return self.presenter.deathmatch_need_classic_games(
                self.deathmatch.min_classic_games,
                result.remaining_games,
            )
        if result.status == DeathmatchStartStatus.NOT_ENOUGH_CHANNELS:
            return self.presenter.deathmatch_not_enough_channels()
        if not result.round:
            return self.presenter.deathmatch_error()
        return self.presenter.deathmatch_round_page(result.round)

    async def process_vote(self, user_id: int, token: str, a_id: int, b_id: int, winner: str) -> Page:
        success = await self.arena.apply_vote(user_id, token, a_id, b_id, winner)
        if not success:
            return self.presenter.duplicate_classic_vote()
        unlock_page = await self._maybe_deathmatch_unlock(user_id)
        if unlock_page:
            return unlock_page
        reward_page = await self._maybe_secret_reward(user_id)
        if reward_page:
            return reward_page
        return await self.duel_page(user_id)

    async def resume_deathmatch(self, user_id: int) -> Page:
        round_info = await self.deathmatch.resume_round(user_id)
        if round_info:
            return self.presenter.deathmatch_round_page(round_info)
        await self.deathmatch.reset(user_id)
        return await self.start_deathmatch(user_id)

    async def restart_deathmatch(self, user_id: int) -> Page:
        await self.deathmatch.reset(user_id)
        return await self.start_deathmatch(user_id)

    async def process_deathmatch_vote(self, user_id: int, token: str, a_id: int, b_id: int, winner: str) -> Page:
        result = await self.deathmatch.process_vote(user_id, token, a_id, b_id, winner)
        if result.status == DeathmatchVoteStatus.INVALID_TOKEN:
            return self.presenter.duplicate_deathmatch_vote()
        if result.status == DeathmatchVoteStatus.STATE_MISSING:
            return self.presenter.deathmatch_state_missing()
        if result.status == DeathmatchVoteStatus.FINISHED and result.champion:
            return self.presenter.deathmatch_finished(result.champion)
        if result.status == DeathmatchVoteStatus.NEXT_ROUND and result.round:
            return self.presenter.deathmatch_round_page(result.round)
        return self.presenter.deathmatch_round_stale()

    async def _maybe_secret_reward(self, user_id: int) -> Page | None:
        thresholds: list[RewardThreshold] = []
        if self.reward_350_url:
            thresholds.append(RewardThreshold(limit=350, url=self.reward_350_url))
        if self.reward_700_url:
            thresholds.append(RewardThreshold(limit=700, url=self.reward_700_url))
        if not thresholds:
            return None
        reward = await self.players.claim_reward(user_id, thresholds)
        if reward:
            return self.presenter.reward_page(reward.games, reward.url)
        return None

    async def _maybe_deathmatch_unlock(self, user_id: int) -> Page | None:
        min_games = self.deathmatch.min_classic_games
        if min_games <= 0:
            return None
        if await self.players.has_unlocked_deathmatch(user_id):
            return None
        games = await self.players.get_classic_game_count(user_id)
        if games < min_games:
            return None
        await self.players.mark_deathmatch_unlocked(user_id)
        return self.presenter.deathmatch_unlocked_page(games=games, min_games=min_games)
