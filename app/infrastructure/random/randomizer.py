from __future__ import annotations

import random
from typing import MutableSequence, Sequence, TypeVar

from ...domain.shared.repositories import Randomizer

T = TypeVar("T")


class SystemRandomizer(Randomizer):
    def __init__(self, source: random.Random | None = None):
        self._random = source or random.Random()

    def choice(self, seq: Sequence[T]) -> T:
        return self._random.choice(seq)

    def sample(self, population: Sequence[T], k: int) -> list[T]:
        return self._random.sample(population, k)

    def shuffle(self, seq: MutableSequence[T]) -> None:
        self._random.shuffle(seq)
