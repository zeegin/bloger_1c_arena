from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence

from ...shared.models import Channel, VoteToken
from ..models import DeathmatchState
from ...shared.repositories import Randomizer
from ...players import PlayersService
from ...rating import RatingService
from ...rating.repositories import ChannelsRepository
from ...shared.repositories import VoteTokensRepository
from ..repositories import DeathmatchRepository


@dataclass(frozen=True)
class DeathmatchRound:
    current: Channel
    opponent: Channel
    token: str
    initial: bool
    number: int
    total: int


class DeathmatchStartStatus(Enum):
    OK = "ok"
    NEED_CLASSIC_GAMES = "need_classic_games"
    NOT_ENOUGH_CHANNELS = "not_enough_channels"


@dataclass(frozen=True)
class DeathmatchStartResult:
    status: DeathmatchStartStatus
    round: Optional[DeathmatchRound] = None
    remaining_games: int = 0


class DeathmatchVoteStatus(Enum):
    NEXT_ROUND = "next_round"
    INVALID_TOKEN = "invalid_token"
    STATE_MISSING = "state_missing"
    FINISHED = "finished"


@dataclass(frozen=True)
class DeathmatchVoteResult:
    status: DeathmatchVoteStatus
    round: Optional[DeathmatchRound] = None
    champion: Optional[Channel] = None


class DeathmatchService:
    """
    Отдельный bounded context для режима deathmatch.
    Держит состояние чемпионов и очередь претендентов независимо от транспорта.
    """

    MAX_ROUNDS = 20

    def __init__(
        self,
        *,
        min_classic_games: int,
        top_limit: int,
        rating_service: RatingService,
        players_service: PlayersService,
        channels_repo: ChannelsRepository,
        deathmatch_repo: DeathmatchRepository,
        vote_tokens: VoteTokensRepository,
        randomizer: Randomizer,
    ):
        self._min_classic_games = min_classic_games
        self._top_limit = top_limit
        self._ratings = rating_service
        self._players = players_service
        self._channels = channels_repo
        self._deathmatch_repo = deathmatch_repo
        self._vote_tokens = vote_tokens
        self._rand = randomizer

    @property
    def min_classic_games(self) -> int:
        return self._min_classic_games

    async def request_start(self, user_id: int) -> DeathmatchStartResult:
        await self._vote_tokens.invalidate(user_id, "deathmatch")
        games_played = await self._players.get_classic_game_count(user_id)
        if games_played < self._min_classic_games:
            return DeathmatchStartResult(
                status=DeathmatchStartStatus.NEED_CLASSIC_GAMES,
                remaining_games=self._min_classic_games - games_played,
            )

        top = await self._ratings.list_top_channels(self._top_limit)
        if len(top) < 2:
            return DeathmatchStartResult(status=DeathmatchStartStatus.NOT_ENOUGH_CHANNELS)

        selection_cap = max(2, self.MAX_ROUNDS + 1)
        selection_pool = top[:selection_cap]
        if len(selection_pool) < 2:
            return DeathmatchStartResult(status=DeathmatchStartStatus.NOT_ENOUGH_CHANNELS)

        current = self._rand.choice(selection_pool)
        opponent_candidates = [ch for ch in selection_pool if ch.id != current.id]
        if not opponent_candidates:
            return DeathmatchStartResult(status=DeathmatchStartStatus.NOT_ENOUGH_CHANNELS)

        opponents = self._expand_opponents(opponent_candidates, self.MAX_ROUNDS)
        opponent = opponents[0]
        remaining_ids = [ch.id for ch in opponents[1:]]
        seen_ids = {current.id, opponent.id}
        state = DeathmatchState(
            user_id=user_id,
            champion_id=None,
            seen_ids=tuple(seen_ids),
            remaining_ids=tuple(remaining_ids),
            rounds_played=0,
            round_total=self.MAX_ROUNDS,
        )
        await self._deathmatch_repo.save_state(state)
        round_info = await self._make_round(
            user_id,
            current,
            opponent,
            initial=True,
            round_number=1,
            round_total=self.MAX_ROUNDS,
        )
        return DeathmatchStartResult(status=DeathmatchStartStatus.OK, round=round_info)

    async def has_active_round(self, user_id: int) -> bool:
        state = await self._deathmatch_repo.get_state(user_id)
        if not state:
            return False
        active = await self._vote_tokens.get_active(user_id, "deathmatch")
        if active:
            return True
        await self._deathmatch_repo.delete_state(user_id)
        return False

    async def resume_round(self, user_id: int) -> Optional[DeathmatchRound]:
        state = await self._deathmatch_repo.get_state(user_id)
        if not state:
            return None
        token_info = await self._vote_tokens.get_active(user_id, "deathmatch")
        if not token_info:
            await self._deathmatch_repo.delete_state(user_id)
            return None
        current = await self._channels.get(token_info.channel_a_id)
        opponent = await self._channels.get(token_info.channel_b_id)
        initial = state.champion_id is None
        round_number = min(state.round_total, state.rounds_played + 1)
        return DeathmatchRound(
            current=current,
            opponent=opponent,
            token=token_info.token.value,
            initial=initial,
            number=round_number,
            total=state.round_total,
        )

    async def reset(self, user_id: int) -> None:
        await self._deathmatch_repo.delete_state(user_id)
        await self._vote_tokens.invalidate(user_id, "deathmatch")

    async def process_vote(
        self,
        user_id: int,
        token: str,
        a_id: int,
        b_id: int,
        winner: str,
    ) -> DeathmatchVoteResult:
        winner = (winner or "").upper()
        if winner not in {"A", "B"}:
            return DeathmatchVoteResult(status=DeathmatchVoteStatus.INVALID_TOKEN)

        if not await self._vote_tokens.consume(
            VoteToken(token),
            user_id=user_id,
            vote_type="deathmatch",
            channel_a_id=a_id,
            channel_b_id=b_id,
        ):
            return DeathmatchVoteResult(status=DeathmatchVoteStatus.INVALID_TOKEN)

        state = await self._deathmatch_repo.get_state(user_id)
        if not state:
            return DeathmatchVoteResult(status=DeathmatchVoteStatus.STATE_MISSING)

        channel_a = await self._channels.get(a_id)
        channel_b = await self._channels.get(b_id)
        winner_channel = channel_a if winner == "A" else channel_b
        winner_id = winner_channel.id

        await self._deathmatch_repo.log_vote(
            user_id=user_id,
            champion_id=state.champion_id,
            channel_a_id=a_id,
            channel_b_id=b_id,
            winner_id=winner_id,
        )

        seen_ids = set(state.seen_ids)
        seen_ids.update({a_id, b_id, winner_id})
        remaining_ids = list(state.remaining_ids)

        rounds_completed = state.rounds_played + 1
        if rounds_completed >= state.round_total or not remaining_ids:
            await self._deathmatch_repo.delete_state(user_id)
            await self._players.set_favorite_channel(user_id, winner_channel.id)
            return DeathmatchVoteResult(
                status=DeathmatchVoteStatus.FINISHED,
                champion=winner_channel,
            )

        next_id = remaining_ids.pop(0)
        next_opponent = await self._channels.get(next_id)
        seen_ids.add(next_opponent.id)
        new_state = DeathmatchState(
            user_id=user_id,
            champion_id=winner_id,
            seen_ids=tuple(seen_ids),
            remaining_ids=tuple(remaining_ids),
            rounds_played=rounds_completed,
            round_total=state.round_total,
        )
        await self._deathmatch_repo.save_state(new_state)
        round_info = await self._make_round(
            user_id,
            winner_channel,
            next_opponent,
            initial=False,
            round_number=rounds_completed + 1,
            round_total=state.round_total,
        )
        return DeathmatchVoteResult(
            status=DeathmatchVoteStatus.NEXT_ROUND,
            round=round_info,
        )

    def _expand_opponents(self, pool: Sequence[Channel], rounds: int) -> list[Channel]:
        candidates = list(pool)
        expanded: list[Channel] = []
        while len(expanded) < rounds:
            self._rand.shuffle(candidates)
            expanded.extend(candidates)
        return expanded[:rounds]

    async def _make_round(
        self,
        user_id: int,
        current: Channel,
        opponent: Channel,
        *,
        initial: bool,
        round_number: int,
        round_total: int,
    ) -> DeathmatchRound:
        token = await self._vote_tokens.create(
            user_id,
            "deathmatch",
            channel_a_id=current.id,
            channel_b_id=opponent.id,
        )
        return DeathmatchRound(
            current=current,
            opponent=opponent,
            token=token.value,
            initial=initial,
            number=round_number,
            total=round_total,
        )
