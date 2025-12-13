from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..elo_rating import elo_update
from ..models import Channel
from ..repositories import (
    ChannelsRepository,
    PairingRepository,
    VoteTokensRepository,
    VotesRepository,
)
from ..value_objects import RatingBand, VoteToken
from .pairing import PairingPolicy


@dataclass(frozen=True)
class DuelPair:
    channel_a: Channel
    channel_b: Channel
    token: str
    rating_band: str


class ArenaService:
    """
    Сервис арены: подбирает пары и применяет голоса в рейтинге Elo.
    """

    def __init__(
        self,
        *,
        pairing_repo: PairingRepository,
        channels_repo: ChannelsRepository,
        vote_tokens: VoteTokensRepository,
        votes_repo: VotesRepository,
        k_factor: float,
    ):
        self._pairing_policy = PairingPolicy(pairing_repo)
        self._channels_repo = channels_repo
        self._vote_tokens = vote_tokens
        self._votes_repo = votes_repo
        self._k_factor = k_factor

    async def prepare_duel(self, user_id: int) -> Optional[DuelPair]:
        pair = await self._pairing_policy.get_pair(user_id)
        if not pair:
            return None
        token = await self._vote_tokens.create(
            user_id,
            "classic",
            channel_a_id=pair[0].id,
            channel_b_id=pair[1].id,
        )
        rating_band = self.rating_range(float(pair[0].rating), float(pair[1].rating))
        return DuelPair(channel_a=pair[0], channel_b=pair[1], token=token.value, rating_band=rating_band)

    async def apply_vote(self, user_id: int, token: str, a_id: int, b_id: int, winner: str) -> bool:
        winner = (winner or "").upper()
        if winner not in {"A", "B", "D"}:
            return False

        if not await self._vote_tokens.consume(
            VoteToken(token),
            user_id=user_id,
            vote_type="classic",
            channel_a_id=a_id,
            channel_b_id=b_id,
        ):
            return False

        a = await self._channels_repo.get(a_id)
        b = await self._channels_repo.get(b_id)
        res = elo_update(a.rating, b.rating, winner=winner, k=self._k_factor)

        draw = winner == "D"
        winner_id: Optional[int]
        if draw:
            winner_id = None
        else:
            winner_id = a_id if winner == "A" else b_id

        updated_a = a.record_result(
            won=None if draw else winner == "A",
            new_rating=res.ra_after,
        )
        updated_b = b.record_result(
            won=None if draw else winner == "B",
            new_rating=res.rb_after,
        )

        await self._votes_repo.record_vote(
            user_id=user_id,
            channel_a_before=a,
            channel_b_before=b,
            channel_a_after=updated_a,
            channel_b_after=updated_b,
            winner_channel_id=winner_id,
            draw=draw,
        )

        return True

    @staticmethod
    def rating_range(a_rating: float, b_rating: float) -> str:
        band = RatingBand.from_ratings(a_rating, b_rating)
        return str(band)
