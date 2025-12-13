from __future__ import annotations

from ..domain import Channel
from ..domain.repositories import ChannelsRepository


class CatalogService:
    """
    Каталожный слой: вся работа с отдельными карточками каналов.
    """

    def __init__(self, repo: ChannelsRepository):
        self._repo = repo

    async def get_channel(self, channel_id: int) -> Channel:
        return await self._repo.get(channel_id)
