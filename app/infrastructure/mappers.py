from __future__ import annotations

import json
from typing import Any, Mapping

from ..domain.models import (
    Channel,
    DeathmatchState,
    DeathmatchStats,
    FavoriteChannelInfo,
    RatingStats,
)


def _coerce(mapping: Mapping[str, Any], key: str, default: Any = None) -> Any:
    value = mapping.get(key, default)
    return value if value is not None else default


def channel_from_row(row: Mapping[str, Any]) -> Channel:
    return Channel(
        id=int(row["id"]),
        title=str(row["title"]),
        tg_url=str(row["tg_url"]),
        description=str(_coerce(row, "description", "") or ""),
        image_url=str(_coerce(row, "image_url", "") or ""),
        rating=float(_coerce(row, "rating", 0.0) or 0.0),
        games=int(_coerce(row, "games", 0) or 0),
        wins=int(_coerce(row, "wins", 0) or 0),
        losses=int(_coerce(row, "losses", 0) or 0),
    )


def rating_stats_from_row(row: Mapping[str, Any]) -> RatingStats:
    return RatingStats(
        games=int(_coerce(row, "games", 0) or 0),
        players=int(_coerce(row, "players", 0) or 0),
    )


def deathmatch_stats_from_row(row: Mapping[str, Any]) -> DeathmatchStats:
    return DeathmatchStats(
        games=int(_coerce(row, "games", 0) or 0),
        players=int(_coerce(row, "players", 0) or 0),
    )


def favorite_channel_from_row(row: Mapping[str, Any]) -> FavoriteChannelInfo:
    return FavoriteChannelInfo(
        id=int(row["id"]),
        title=str(row["title"]),
        tg_url=str(row["tg_url"]),
        fans=int(_coerce(row, "fans", 0) or 0),
    )


def deathmatch_state_from_row(row: Mapping[str, Any]) -> DeathmatchState:
    seen_ids = tuple(int(x) for x in json.loads(row.get("seen_ids") or "[]"))
    remaining_ids = tuple(int(x) for x in json.loads(row.get("remaining_ids") or "[]"))
    return DeathmatchState(
        user_id=int(row["user_id"]),
        champion_id=row.get("champion_id"),
        seen_ids=seen_ids,
        remaining_ids=remaining_ids,
    )


def serialize_deathmatch_state(state: DeathmatchState) -> tuple[str, str]:
    return json.dumps(sorted(state.seen_ids)), json.dumps(list(state.remaining_ids))
