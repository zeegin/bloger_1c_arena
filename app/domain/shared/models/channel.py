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
