from __future__ import annotations

from typing import Optional, Protocol

from ..models import DeathmatchState


class DeathmatchRepository(Protocol):
    async def get_state(self, user_id: int) -> Optional[DeathmatchState]: ...

    async def save_state(self, state: DeathmatchState) -> None: ...

    async def delete_state(self, user_id: int) -> None: ...

    async def log_vote(
        self,
        *,
        user_id: int,
        champion_id: Optional[int],
        channel_a_id: int,
        channel_b_id: int,
        winner_id: int,
    ) -> None: ...
