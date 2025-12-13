from __future__ import annotations

from ..domain import Channel
from .helpers.image_preview import CombinedImageService


class MediaService:
    def __init__(self, backend: CombinedImageService):
        self._backend = backend

    async def build_duel_preview(self, a: Channel, b: Channel):
        return await self._backend.build_preview(a, b)

    async def close(self) -> None:
        await self._backend.close()
