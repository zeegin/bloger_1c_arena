from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FavoriteChannelInfo:
    id: int
    title: str
    tg_url: str
    fans: int
