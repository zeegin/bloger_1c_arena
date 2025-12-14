from __future__ import annotations

from typing import Protocol


class ImageProvider(Protocol):
    async def fetch(self, url: str) -> bytes | None: ...

    async def close(self) -> None: ...
