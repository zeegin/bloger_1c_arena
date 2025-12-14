from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from ..domain.arena import ArenaService
from ..domain.deathmatch import DeathmatchService
from ..domain.players import PlayersService
from ..domain.rating import RatingService
from ..infrastructure import sync_channels
from ..infrastructure.images import CachedImageProvider, ImageDownloader
from ..infrastructure.random import SystemRandomizer
from ..infrastructure.sqlite import (
    SQLiteChannelsRepository,
    SQLiteDatabase,
    SQLiteDeathmatchRepository,
    SQLitePairingRepository,
    SQLitePlayersRepository,
    SQLiteStatsRepository,
    SQLiteVoteTokensRepository,
    SQLiteVotesRepository,
)
from .helpers.image_preview import CombinedImageService
from .media_service import MediaService
from .presenters import BotPresenter
from .queries.rating import RatingQueryService

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class AppConfig:
    bot_token: str
    db_path: str
    k_factor: float = 32.0
    top_n: int = 20
    min_classic_games_for_dm: int = 50
    reward_350_url: str | None = None
    reward_700_url: str | None = None
    delete_missing_channels: bool = True
    sync_channels_on_start: bool = True
    image_allowed_hosts: set[str] | None = None
    max_image_size_bytes: int = 2_000_000
    image_assets_path: str | None = None


class AppContainer:
    def __init__(
        self,
        *,
        config: AppConfig,
        rating_service: RatingService,
        rating_queries: RatingQueryService,
        players_service: PlayersService,
        arena_service: ArenaService,
        deathmatch_service: DeathmatchService,
        media_service: MediaService,
        presenter: BotPresenter,
        database: SQLiteDatabase,
        channels_repo: SQLiteChannelsRepository,
    ):
        self.config = config
        self.rating_service = rating_service
        self.rating_queries = rating_queries
        self.players_service = players_service
        self.arena_service = arena_service
        self.deathmatch_service = deathmatch_service
        self.media_service = media_service
        self.presenter = presenter

        self._database = database
        self._channels_repo = channels_repo

    async def init_resources(self) -> None:
        await self._database.init()

    async def sync_channels(self, yaml_path: str, *, delete_missing: bool = True) -> None:
        await sync_channels(
            self._channels_repo,
            yaml_path,
            delete_missing=delete_missing,
        )

    async def close(self) -> None:
        await self.media_service.close()


def create_container(config: AppConfig) -> AppContainer:
    database = SQLiteDatabase(config.db_path)

    channels_repo = SQLiteChannelsRepository(database)
    players_repo = SQLitePlayersRepository(database)
    stats_repo = SQLiteStatsRepository(database)
    vote_tokens_repo = SQLiteVoteTokensRepository(database)
    votes_repo = SQLiteVotesRepository(database)
    deathmatch_repo = SQLiteDeathmatchRepository(database)
    pairing_repo = SQLitePairingRepository(database)

    rating_service = RatingService(channels_repo, stats_repo)
    rating_queries = RatingQueryService(rating_service)
    players_service = PlayersService(players_repo)
    arena_service = ArenaService(
        pairing_repo=pairing_repo,
        channels_repo=channels_repo,
        vote_tokens=vote_tokens_repo,
        votes_repo=votes_repo,
        k_factor=config.k_factor,
    )
    deathmatch_service = DeathmatchService(
        min_classic_games=config.min_classic_games_for_dm,
        top_limit=config.top_n,
        rating_service=rating_service,
        players_service=players_service,
        channels_repo=channels_repo,
        deathmatch_repo=deathmatch_repo,
        vote_tokens=vote_tokens_repo,
        randomizer=SystemRandomizer(),
    )

    if config.image_assets_path:
        vs_dir_candidate = Path(config.image_assets_path)
        if not vs_dir_candidate.exists():
            logger.warning("Configured image assets path '%s' does not exist", vs_dir_candidate)
            vs_dir = None
        else:
            vs_dir = vs_dir_candidate
    else:
        fallback = Path(__file__).resolve().parents[2] / "img"
        if fallback.exists():
            vs_dir = fallback
        else:
            logger.warning("Default image assets directory '%s' not found; previews may lack VS images", fallback)
            vs_dir = None
    image_provider = CachedImageProvider(
        downloader=ImageDownloader(
            allowed_hosts=config.image_allowed_hosts,
            max_download_bytes=config.max_image_size_bytes,
        )
    )
    image_backend = CombinedImageService(
        image_provider=image_provider,
        vs_images_dir=vs_dir,
    )
    media_service = MediaService(image_backend)
    presenter = BotPresenter()

    return AppContainer(
        config=config,
        rating_service=rating_service,
        rating_queries=rating_queries,
        players_service=players_service,
        arena_service=arena_service,
        deathmatch_service=deathmatch_service,
        media_service=media_service,
        presenter=presenter,
        database=database,
        channels_repo=channels_repo,
    )
