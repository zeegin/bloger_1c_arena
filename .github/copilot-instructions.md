# Copilot / AI Agent Instructions for this repository

These short instructions help AI coding agents quickly become productive in this codebase.

## Big picture
- Architecture: DDD + Clean Architecture. See `app/domain/` (bounded contexts: `arena`, `deathmatch`, `rating`, `players`), `app/application/` (use-cases, `workflow.py`, presenters), and `app/infrastructure/` (adapters like `sqlite/`, `images/`).
- Dependency flow: Domain <- Application <- Infrastructure. The startup container wires adapters into interfaces.
- Entrypoint: `app/main.py` bootstraps the app (async context manager `bootstrap_app`), config via env vars, then starts the Telegram bot polling loop.

## Essential files to inspect
- `app/main.py` — startup, env vars, polling loop, metrics config.
- `app/application/bootstrap.py` and `app/application/container.py` — dependency wiring; use these to swap implementations in tests or alternative deployments.
- `app/application/workflow.py` — orchestrates user flows; primary place to change business logic for bot interactions.
- `app/application/presenters/` — text templates and page-building patterns used by the bot.
- `app/infrastructure/sqlite/` — concrete repository adapters and schema access; tests use these adapters for integration-style checks.
- `tests/` — unit/integration tests. Tests use `unittest` via discover (see README).

## Runtime & developer workflows
- Local dev (README): create a venv, `pip install -r requirements.txt`, run tests with:

  .venv/bin/python -m unittest discover -s tests

- Docker: `docker compose up --build` (project includes Dockerfile + docker-compose.yml).
- Key env vars: `BOT_TOKEN` (required), `DB_PATH` (default `/data/bot.db`), `SYNC_CHANNELS_ON_START`, `SYNC_DELETE_MISSING_CHANNELS`, `IMAGE_ALLOWED_HOSTS`, `IMAGE_MAX_BYTES`, `METRICS_LOG_PATH`.
- To regenerate channel list: `python3 scripts/fetch_tgstat_channels.py --output channels.yaml`.

## Project-specific conventions & patterns
- Use DDD bounded contexts — changes to domain logic go inside `app/domain/<context>` and expose services/repositories under `services/` and `repositories/`.
- Application-level orchestration lives in `app/application/workflow.py`. Presentation concerns live in `presenters/` and `media_service.py`.
- Dependency injection is explicit: prefer adding or replacing adapters in `container.py` and `bootstrap.py` rather than importing infrastructure directly in domain code.
- Messaging and pages: `Page` objects with `media` and `buttons` are rendered by `TelegramBotApp._render_page` in `app/application/bot_app.py`. Media “duel” previews are produced by `media_service.build_duel_preview` (returns an in-memory image-like object).

## Testing notes for agents
- Tests are runnable with `unittest` discover; avoid assuming `pytest` unless you add it and update CI.
- Many tests mock or replace infrastructure via the container; prefer writing tests that inject a lightweight adapter rather than patching at runtime.

## Integration points & external dependencies
- Telegram bot: `aiogram` is used; the bot lifecycle is in `app/main.py` and `app/application/bot_app.py`.
- Metrics: JSONL logging (default `/data/metrics/actions.log`) and `app/infrastructure/metrics` capture spans. `METRICS_LOG_PATH` controls output.
- Image fetching/caching: `app/infrastructure/images/provider.py` and `image_preview` helpers; respect `IMAGE_ALLOWED_HOSTS` and `IMAGE_MAX_BYTES` to avoid large downloads.
- SQLite: repository adapters are under `app/infrastructure/sqlite` — altering DB schemas or queries should update those adapters and tests in `tests/test_sqlite.py`.

## Coding guidance for PRs (practical, codebase-specific)
- When changing domain logic, add/update a small unit test under `tests/` exercising the service in `app/domain/<context>/services` and prefer injecting an in-memory adapter from `app/infrastructure/sqlite` or a test double provided by `container`.
- For changes affecting bot messages/templates, update `presenters/` and add an end-to-end style test that renders a `Page` and asserts on the produced text/markup.
- For performance-sensitive media changes, run a local check that `media_service.build_duel_preview` returns a small BytesIO and respects `IMAGE_MAX_BYTES`.

## Quick examples (where to change / how to inspect)
- Swap DB path: adjust `DB_PATH` env var (default set in `app/main.py` load_app_config()).
- Disable channel sync on start: set `SYNC_CHANNELS_ON_START=0` (checked in `app/main.py`).
- Inspect the bot dispatcher handlers: `app/application/bot_app.py::TelegramBotApp.build_dispatcher()` — add callback patterns there.

If anything is unclear or you want more details (CI, release steps, or contributor conventions), tell me which area to expand and I'll update this file.
