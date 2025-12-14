from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VoteToken:
    value: str

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ActiveVoteToken:
    token: VoteToken
    channel_a_id: int
    channel_b_id: int
