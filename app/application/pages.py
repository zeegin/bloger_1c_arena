from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from ..domain import Channel


@dataclass(frozen=True)
class PageButton:
    text: str
    callback_data: str


@dataclass(frozen=True)
class PageMediaRequest:
    kind: str
    channels: Tuple[Channel, Channel]


@dataclass(frozen=True)
class Page:
    text: str
    buttons: List[List[PageButton]] = field(default_factory=list)
    media: List[PageMediaRequest] = field(default_factory=list)
    parse_mode: str = "HTML"
    disable_preview: bool = True
