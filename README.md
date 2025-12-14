## Запуск в Docker

```bash
docker compose up --build
```

## Локальная разработка

1. Установи Python 3.12 (например, через Homebrew).
2. Создай окружение и установи зависимости:
   ```bash
   python3.12 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
   Если нужны утилиты для подготовки данных (например, загрузка каналов из HTML), поставь расширенный набор:
   ```bash
   pip install -r requirements-dev.txt
   ```
3. Запусти тесты:
   ```bash
   .venv/bin/python -m unittest discover -s tests
   ```
   > Перед запуском убедись, что установлены зависимости из `requirements.txt`.

## Ключевые компоненты

- `app/domain/arena|deathmatch|rating|players` — доменные bounded contexts. Каждый контекст содержит свои `services/` и `repositories/` (интерфейсы) и опирается только на shared kernel.
- `app/domain/shared` — shared kernel: общие value objects (`Channel`, `VoteToken`, `RatingStats`, …) и общие протоколы (например, хранилище токенов голосования).
- `app/application` — сценарии и представление бота: `workflow.py` оркестрирует доменные сервисы, `presenters/` отвечают за тексты и шаблоны, `media_service.py` собирает карточки дуэлей.
- `app/infrastructure` — реализации портов: `sqlite/` содержит адаптеры репозиториев и миграции БД, `images/` — загрузку и кеширование превью, `channels_loader.py` — синхронизацию справочника.
- `tests/` — изолированные тесты workflow, presenter и инфраструктурных адаптеров (`tests/test_sqlite.py`, `tests/test_image_service.py` и др.).

## Архитектура

Проект построен по принципам DDD и чистой архитектуры:

- **Bounded contexts**: `arena` отвечает за классические дуэли и Elo, `deathmatch` — за турнир на выбивание, `rating` — за чтение рейтингов и витрины, `players` — за состояние пользователей. Контексты не зависят друг от друга напрямую.
- **Shared kernel**: папка `app/domain/shared` хранит только те value objects и протоколы, которые действительно используются в нескольких контекстах (каналы, статистика, токены голосования).
- **Application layer**: `app/application/workflow.py` описывает user journey Telegram-бота и зависит только от доменных интерфейсов. Представления (`presenters/templates`) и медиасервис формируют конкретный UI/контент.
- **Infrastructure layer**: конкретные реализации репозиториев находятся в `app/infrastructure/sqlite`. Другие адаптеры (загрузка изображений, синхронизация каналов) тоже собраны в инфраструктуре и внедряются через контейнер (`app/application/container.py`).
- **Dependency flow**: Domain ← Application ← Infrastructure. Контейнер связывает зависимости на старте, что позволяет легко подменять адаптеры в тестах или при переходе на другую БД/транспорт.

## Обновление списка каналов

Чтобы перегенерировать `channels.yaml` c актуальными каналами из подборки TGStat, запусти:

```
python3 scripts/fetch_tgstat_channels.py --output channels.yaml
```

По умолчанию при старте бота из `channels.yaml` удаляются все каналы, которых нет в файле. Это поведение можно отключить, если выставить переменные:
- `SYNC_CHANNELS_ON_START=0` — вообще пропустить синхронизацию при запуске.
- `SYNC_DELETE_MISSING_CHANNELS=0` — синхронизировать, но не удалять отсутствующие каналы.

Если используешь внешние изображения, можно дополнительно ограничить загрузку:
- `IMAGE_ALLOWED_HOSTS=cdn.tgstat.ru,cdn4.telesco.pe` — список разрешённых хостов (через запятую).
- `IMAGE_MAX_BYTES=2000000` — максимальный размер скачиваемого файла в байтах.

Для сбора «сырых» метрик действий Telegram бот пишет JSON‑строки в отдельный лог (по умолчанию `/data/metrics/actions.log`). Можно переопределить путь через `METRICS_LOG_PATH`. Строки вида:

```jsonl
{"ts":"2025-01-15T12:34:56.789+00:00","action":"callback:menu:play","duration_ms":423.1,"success":true,"user_id":123456}
```

Для формирования отчета выполните:

```bash
python3 scripts/calc_apdex.py --log ./data/metrics/actions.log --target 400 --output ./reports/apdex.md
```
