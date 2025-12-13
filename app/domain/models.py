from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Channel:
    id: int
    title: str
    tg_url: str
    description: str
    image_url: str
    rating: float
    games: int
    wins: int
    losses: int

    def record_result(self, *, won: bool | None, new_rating: float) -> "Channel":
        if won is None:
            return Channel(
                **{**self.__dict__, "games": self.games + 1, "rating": new_rating},
            )
        wins = self.wins + (1 if won else 0)
        losses = self.losses + (1 if won is False else 0)
        return Channel(
            **{
                **self.__dict__,
                "games": self.games + 1,
                "wins": wins,
                "losses": losses,
                "rating": new_rating,
            }
        )


@dataclass(frozen=True)
class RatingStats:
    games: int
    players: int


@dataclass(frozen=True)
class DeathmatchStats:
    games: int
    players: int


@dataclass(frozen=True)
class FavoriteChannelInfo:
    id: int
    title: str
    tg_url: str
    fans: int


@dataclass(frozen=True)
class Player:
    id: int
    tg_user_id: int
    username: str | None
    first_name: str | None
    favorite_channel_id: int | None = None
    is_admin: bool = False

    def with_favorite(self, channel_id: int | None) -> "Player":
        return Player(
            id=self.id,
            tg_user_id=self.tg_user_id,
            username=self.username,
            first_name=self.first_name,
            favorite_channel_id=channel_id,
            is_admin=self.is_admin,
        )


@dataclass(frozen=True)
class DeathmatchState:
    user_id: int
    champion_id: int | None
    seen_ids: tuple[int, ...]
    remaining_ids: tuple[int, ...]

    def next_opponent(self) -> tuple[int | None, "DeathmatchState"]:
        if not self.remaining_ids:
            return None, self
        next_id = self.remaining_ids[0]
        new_remaining = self.remaining_ids[1:]
        new_seen = tuple(set(self.seen_ids + (next_id,)))
        return next_id, DeathmatchState(
            user_id=self.user_id,
            champion_id=self.champion_id,
            seen_ids=new_seen,
            remaining_ids=new_remaining,
        )
