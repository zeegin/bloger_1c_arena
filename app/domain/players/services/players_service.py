from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from ...shared.models import Channel
from ..repositories import PlayersRepository


class PlayersService:
    """
    Управление данными пользователей: учёт в базе, статистика и любимчики.
    """

    def __init__(self, repo: PlayersRepository):
        self._repo = repo

    async def upsert_user(self, tg_user_id: int, username: Optional[str], first_name: Optional[str]) -> int:
        return await self._repo.upsert(tg_user_id, username, first_name)

    async def get_classic_game_count(self, user_id: int) -> int:
        return await self._repo.get_classic_games(user_id)

    async def get_draw_count(self, user_id: int) -> int:
        return await self._repo.get_draw_count(user_id)

    async def set_favorite_channel(self, user_id: int, channel_id: Optional[int]) -> None:
        await self._repo.set_favorite(user_id, channel_id)

    async def get_favorite_channel(self, user_id: int) -> Optional[Channel]:
        return await self._repo.get_favorite(user_id)

    async def get_reward_stage(self, user_id: int) -> int:
        return await self._repo.get_reward_stage(user_id)

    async def set_reward_stage(self, user_id: int, stage: int) -> None:
        await self._repo.set_reward_stage(user_id, stage)

    async def claim_reward(self, user_id: int, thresholds: Sequence["RewardThreshold"]) -> Optional["RewardGrant"]:
        eligible = [t for t in thresholds if t.url]
        if not eligible:
            return None
        eligible = sorted(eligible, key=lambda t: t.limit)
        current_stage = await self.get_reward_stage(user_id)
        games = await self.get_classic_game_count(user_id)
        for threshold in eligible:
            if current_stage >= threshold.limit:
                continue
            if games >= threshold.limit:
                await self.set_reward_stage(user_id, threshold.limit)
                return RewardGrant(games=games, url=threshold.url)
        return None

    async def has_unlocked_deathmatch(self, user_id: int) -> bool:
        return await self._repo.is_deathmatch_unlocked(user_id)

    async def mark_deathmatch_unlocked(self, user_id: int) -> None:
        await self._repo.mark_deathmatch_unlocked(user_id)

    async def get_deathmatch_game_count(self, user_id: int) -> int:
        return await self._repo.get_deathmatch_games(user_id)


@dataclass(frozen=True)
class RewardThreshold:
    limit: int
    url: str


@dataclass(frozen=True)
class RewardGrant:
    games: int
    url: str
