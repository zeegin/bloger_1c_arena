from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ..models import Channel, DeathmatchState
from ..players import PlayersService
from ..rating import RatingService
from ..repositories import ChannelsRepository, DeathmatchRepository, VoteTokensRepository
from ..value_objects import VoteToken


@dataclass(frozen=True)
class DeathmatchRound:
    current: Channel
    opponent: Channel
    token: str
    initial: bool


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
    ):
        self._min_classic_games = min_classic_games
        self._top_limit = top_limit
        self._ratings = rating_service
        self._players = players_service
        self._channels = channels_repo
        self._deathmatch_repo = deathmatch_repo
        self._vote_tokens = vote_tokens

    @property
    def min_classic_games(self) -> int:
        return self._min_classic_games

    async def request_start(self, user_id: int) -> DeathmatchStartResult:
        games_played = await self._players.get_classic_game_count(user_id)
        if games_played < self._min_classic_games:
            return DeathmatchStartResult(
                status=DeathmatchStartStatus.NEED_CLASSIC_GAMES,
                remaining_games=self._min_classic_games - games_played,
            )

        top = await self._ratings.list_top_channels(self._top_limit)
        if len(top) < 2:
            return DeathmatchStartResult(status=DeathmatchStartStatus.NOT_ENOUGH_CHANNELS)

        current = top[0]
        opponent = top[1]
        remaining_ids = [ch.id for ch in top[2:]]
        seen_ids = {current.id, opponent.id}
        state = DeathmatchState(
            user_id=user_id,
            champion_id=None,
            seen_ids=tuple(seen_ids),
            remaining_ids=tuple(remaining_ids),
        )
        await self._deathmatch_repo.save_state(state)
        round_info = await self._make_round(user_id, current, opponent, initial=True)
        return DeathmatchStartResult(status=DeathmatchStartStatus.OK, round=round_info)

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

        next_opponent = None
        if remaining_ids:
            next_id = remaining_ids.pop(0)
            next_opponent = await self._channels.get(next_id)

        if not next_opponent:
            await self._deathmatch_repo.delete_state(user_id)
            await self._players.set_favorite_channel(user_id, winner_channel.id)
            return DeathmatchVoteResult(
                status=DeathmatchVoteStatus.FINISHED,
                champion=winner_channel,
            )

        seen_ids.add(next_opponent.id)
        new_state = DeathmatchState(
            user_id=user_id,
            champion_id=winner_id,
            seen_ids=tuple(seen_ids),
            remaining_ids=tuple(remaining_ids),
        )
        await self._deathmatch_repo.save_state(new_state)
        round_info = await self._make_round(user_id, winner_channel, next_opponent, initial=False)
        return DeathmatchVoteResult(
            status=DeathmatchVoteStatus.NEXT_ROUND,
            round=round_info,
        )

    async def _make_round(self, user_id: int, current: Channel, opponent: Channel, *, initial: bool) -> DeathmatchRound:
        token = await self._vote_tokens.create(
            user_id,
            "deathmatch",
            channel_a_id=current.id,
            channel_b_id=opponent.id,
        )
        return DeathmatchRound(current=current, opponent=opponent, token=token.value, initial=initial)
