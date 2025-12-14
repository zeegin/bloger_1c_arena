import asyncio
import logging
import os

from dotenv import load_dotenv
from aiogram import Bot

from .application.bot_app import TelegramBotApp
from .application.bootstrap import bootstrap_app
from .application.container import AppConfig

load_dotenv()
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


def load_app_config() -> AppConfig:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("BOT_TOKEN is empty. Put it to .env")
    db_path = os.getenv("DB_PATH", "/data/bot.db")
    k_factor = float(os.getenv("K_FACTOR", "32.0"))
    top_n = int(os.getenv("TOP_N", "20"))
    min_dm_games = int(os.getenv("MIN_CLASSIC_GAMES_FOR_DM", "50"))
    reward_350_url = os.getenv("ARENA_REWARD_350_URL", "").strip() or None
    reward_700_url = os.getenv("ARENA_REWARD_700_URL", "").strip() or None
    delete_missing = os.getenv("SYNC_DELETE_MISSING_CHANNELS", "1").strip().lower() not in {"0", "false", "no"}
    sync_on_start = os.getenv("SYNC_CHANNELS_ON_START", "1").strip().lower() not in {"0", "false", "no"}
    allowed_hosts_raw = os.getenv("IMAGE_ALLOWED_HOSTS", "").strip()
    allowed_hosts = {
        host.strip().lower()
        for host in allowed_hosts_raw.split(",")
        if host.strip()
    } or None
    max_image_bytes = int(os.getenv("IMAGE_MAX_BYTES", "2000000"))
    config = AppConfig(
        bot_token=bot_token,
        db_path=db_path,
        k_factor=k_factor,
        top_n=top_n,
        min_classic_games_for_dm=min_dm_games,
        reward_350_url=reward_350_url,
        reward_700_url=reward_700_url,
        delete_missing_channels=delete_missing,
        sync_channels_on_start=sync_on_start,
        image_allowed_hosts=allowed_hosts,
        max_image_size_bytes=max_image_bytes,
    )
    logger.info(
        "Config loaded: db_path=%s, top_n=%s, min_dm_games=%s, "
        "sync_channels=%s, delete_missing=%s, image_hosts=%s, max_image_bytes=%s",
        config.db_path,
        config.top_n,
        config.min_classic_games_for_dm,
        config.sync_channels_on_start,
        config.delete_missing_channels,
        ",".join(sorted(config.image_allowed_hosts)) if config.image_allowed_hosts else "any",
        config.max_image_size_bytes,
    )
    return config


async def main():
    config = load_app_config()
    logger.info("Bootstrapping application")
    async with bootstrap_app(config) as container:
        if config.sync_channels_on_start:
            logger.info("Syncing channels from channels.yaml (delete_missing=%s)", config.delete_missing_channels)
            await container.sync_channels(
                "channels.yaml",
                delete_missing=config.delete_missing_channels,
            )
            logger.info("Channels sync finished")
        else:
            logger.info("Skip channels sync because SYNC_CHANNELS_ON_START=0")

        logger.info("Building Telegram bot application")
        bot_app = TelegramBotApp(container)
        bot = Bot(config.bot_token)
        dp = bot_app.build_dispatcher()
        logger.info("Starting polling loop")
        try:
            await dp.start_polling(bot)
        except Exception:
            logger.exception("Polling stopped due to unexpected error")
            raise
        finally:
            logger.info("Polling loop finished")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user, shutting down")
