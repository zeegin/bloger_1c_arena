from __future__ import annotations

from typing import Protocol, Sequence

from ...shared.models import Channel, FavoriteChannelInfo


class ChannelsRepository(Protocol):
    async def get(self, channel_id: int) -> Channel: ...

    async def list_top(self, limit: int) -> Sequence[Channel]: ...

    async def list_all(self) -> Sequence[Channel]: ...

    async def list_favorites(self) -> Sequence[FavoriteChannelInfo]: ...

    async def add_or_update(
        self,
        *,
        tg_url: str,
        title: str,
        description: str,
        image_url: str,
    ) -> None: ...

    async def delete_not_in(self, allowed_urls: set[str]) -> int: ...
