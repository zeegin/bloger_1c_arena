from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VoteToken:
    value: str

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class RatingBand:
    lower: int
    upper: int

    @classmethod
    def from_ratings(cls, a_rating: float, b_rating: float, step: int = 50) -> "RatingBand":
        lower = int((min(a_rating, b_rating) // step) * step)
        upper = int(((max(a_rating, b_rating) + step - 1) // step) * step)
        return cls(lower=lower, upper=upper)

    def __str__(self) -> str:
        return f"{self.lower}-{self.upper}"
