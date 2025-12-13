from __future__ import annotations

from contextlib import asynccontextmanager

from .container import AppConfig, AppContainer, create_container


@asynccontextmanager
async def bootstrap_app(config: AppConfig):
    container = create_container(config)
    await container.init_resources()
    try:
        yield container
    finally:
        await container.close()
