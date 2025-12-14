from __future__ import annotations

from typing import MutableSequence, Protocol, Sequence, TypeVar

T = TypeVar("T")


class Randomizer(Protocol):
    def choice(self, seq: Sequence[T]) -> T: ...

    def sample(self, population: Sequence[T], k: int) -> list[T]: ...

    def shuffle(self, seq: MutableSequence[T]) -> None: ...
