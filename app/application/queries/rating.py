from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ...domain.shared.models import Channel, FavoriteChannelInfo, RatingStats, DeathmatchStats
from ...domain.rating import RatingService


@dataclass(frozen=True)
class TopEntry:
    title: str
    tg_url: str
    rating: float
    games: int
    wins: int


@dataclass(frozen=True)
class TopListing:
    entries: list[TopEntry]
    stats: RatingStats


@dataclass(frozen=True)
class OrderedListing:
    entries: list[TopEntry]
    show_all: bool


@dataclass(frozen=True)
class WeightedEntry:
    title: str
    tg_url: str
    wins: int
    games: int
    rate_percent: float


@dataclass(frozen=True)
class FavoritesSummary:
    favorites: list[FavoriteChannelInfo]
    stats: DeathmatchStats


class RatingQueryService:
    def __init__(self, rating: RatingService):
        self._rating = rating

    async def top_listing(self, limit: int) -> TopListing | None:
        top = await self._rating.list_top_channels(limit)
        if not top:
            return None
        stats = await self._rating.get_rating_stats()
        return TopListing(entries=self._to_top_entries(top), stats=stats)

    async def ordered_listing(self, limit: int = 100) -> OrderedListing | None:
        top = await self._rating.list_top_channels(limit)
        if not top:
            return None
        show_all = False
        channels: Sequence[Channel] = top
        if len(top) < limit:
            channels = await self._rating.list_all_channels()
            if not channels:
                return None
            show_all = True
        return OrderedListing(entries=self._to_top_entries(channels), show_all=show_all)

    async def winrate_top(self, limit: int = 100) -> list[WeightedEntry]:
        channels = await self._rating.list_all_channels()
        if not channels:
            return []

        def win_rate(ch: Channel) -> float:
            games = max(1, int(ch.games))
            wins = max(0, int(ch.wins))
            return wins / games

        sorted_channels = sorted(channels, key=win_rate, reverse=True)[:limit]
        return [
            WeightedEntry(
                title=ch.title,
                tg_url=ch.tg_url,
                wins=int(ch.wins),
                games=int(ch.games),
                rate_percent=win_rate(ch) * 100,
            )
            for ch in sorted_channels
        ]

    async def favorites_summary(self) -> FavoritesSummary | None:
        favorites = await self._rating.list_favorite_channels()
        if not favorites:
            return None
        stats = await self._rating.get_deathmatch_stats()
        return FavoritesSummary(favorites=favorites, stats=stats)

    def _to_top_entries(self, channels: Sequence[Channel]) -> list[TopEntry]:
        return [
            TopEntry(
                title=ch.title,
                tg_url=ch.tg_url,
                rating=float(ch.rating),
                games=int(ch.games),
                wins=int(ch.wins),
            )
            for ch in channels
        ]
