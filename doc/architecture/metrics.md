# Обзор метрик

Все метрики производительности записываются в формате JSONL логгером `metrics.actions` в файл, указанный через `METRICS_LOG_PATH` (по умолчанию `/data/metrics/actions.log`). Каждая строка содержит:

- `ts` — отметка времени (UTC) в ISO-8601.
- `action` — логическое имя операции.
- `duration_ms` — длительность в миллисекундах.
- `success` — `true`, если действие не завершилось исключением.
- `source` — подсистема (`telegram`, `media`, `database` и т. п.).
- Дополнительные поля (например, `user_id` для телеграм-коллбеков).

В `app/main.py` логгер инициализируется через `configure_metrics_logger`, поэтому любые альтернативные точки входа тоже должны вызвать эту функцию, иначе записи останутся в stdout.

Сырые JSONL удобно анализировать скриптом `scripts/calc_apdex.py`: он читает файл (или каталог с ротацией), агрегирует время (min/max/avg) и считает Apdex по каждому действию, формируя Markdown отчёт.

## Действия телеграм-бота

Файл: `app/application/bot_app.py`

| Шаблон action | Source | Описание |
| --- | --- | --- |
| `message:<command-or-type>` | `telegram` | Полная обработка входящих сообщений (сейчас `/start`). Включает апсерт пользователя и отправку страниц. |
| `callback:<payload>` | `telegram` | Любой inline-коллбек (меню, голосование, deathmatch). Payload (например, `callback:vote:…`) позволяет различить сценарии. Время охватывает весь цикл от upsert до ответа. |

Если Telegram передаёт `user_id`, он сохраняется в `extra`.

## Медиа и изображения

Файлы: `app/application/helpers/image_preview.py`, `app/infrastructure/images/provider.py`

| Action | Source | Описание |
| --- | --- | --- |
| `media:channel_fetch` | `media` | Высокоуровневое получение аватарки канала через `ImageProvider`. Если файл есть в дисковом кэше (`CachedImageProvider`), дополнительно фиксируется событие `image:channel_cache_hit`, иначе `image:channel_download`. |
| `media:preview_compose` | `media` | CPU-композиция дуэльного изображения (две картинки + VS-оверлей). |
| `image:channel_cache_hit` | `media` | Срабатывание дискового кэша `CachedImageProvider` (байты читаются напрямую с диска). |
| `image:channel_download` | `media` | HTTP-скачивание аватарки через `ImageDownloader` с последующей записью в кэш. |

Эти метрики показывают эффективность кэширования и затраты на генерацию превью.

## Операции базы данных (SQLite)

Во всех репозиториях `app/infrastructure/sqlite` асинхронные методы обёрнуты `@metrics.wrap_async(..., source="database")`.

**Pairing (`pairing.py`):**
- `db:pairing.low_game_pool`
- `db:pairing.fetch_closest`
- `db:pairing.has_seen_pair`
- `db:pairing.mark_seen`

**Players (`players.py`):**
- `db:players.upsert`
- `db:players.classic_games`
- `db:players.draw_count`
- `db:players.set_favorite`
- `db:players.get_favorite`
- `db:players.reward_stage`
- `db:players.set_reward_stage`
- `db:players.dm_unlocked`
- `db:players.mark_dm_unlocked`
- `db:players.dm_games`
- `db:players.dm_games_count`

**Votes (`votes.py`):**
- `db:votes.record_vote`

**Vote tokens (`vote_tokens.py`):**
- `db:vote_tokens.create`
- `db:vote_tokens.consume`
- `db:vote_tokens.get_active`
- `db:vote_tokens.invalidate`

**Stats (`stats.py`):**
- `db:stats.rating`
- `db:stats.deathmatch`

**Deathmatch (`deathmatch.py`):**
- `db:deathmatch.get_state`
- `db:deathmatch.save_state`
- `db:deathmatch.delete_state`
- `db:deathmatch.log_vote`

Эти действия покрывают все обращения доменных сервисов к базе, позволяя искать узкие места.

## Как пользоваться данными

1. Убедитесь, что путь из `METRICS_LOG_PATH` доступен и настроен до запуска бота.
2. Соберите JSONL из `data/metrics/`.
3. Выполните `python3 scripts/calc_apdex.py --log <путь> --target 400 --output reports/apdex.md`. Скрипт корректно обработает отсутствие файлов и агрегирует голосования по `callback:vote`/`callback:dmvote`; если в JSONL присутствует поле `media_cache` (например, `hit`, `halfhit`, `miss`), ключ действия автоматически будет дополнен пометкой `[cache=...]`, что позволит сравнивать кэшированные и «холодные» сценарии.
4. Готовый Markdown содержит Apdex, min/max/avg и число ошибок по каждому действию — его можно отправить команде или использовать в дашбордах.
