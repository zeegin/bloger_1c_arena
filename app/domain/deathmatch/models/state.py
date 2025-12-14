from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeathmatchState:
    user_id: int
    champion_id: int | None
    seen_ids: tuple[int, ...]
    remaining_ids: tuple[int, ...]
    rounds_played: int
    round_total: int

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
            rounds_played=self.rounds_played,
            round_total=self.round_total,
        )
