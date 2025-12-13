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
3. Запусти тесты:
   ```bash
   .venv/bin/python -m unittest discover -s tests
   ```
   > Перед запуском убедись, что установлены зависимости из `requirements.txt`.

## Ключевые компоненты

- `app/domain/arena|deathmatch|rating|players` — доменные bounded contexts и бизнес-логика.
- `app/services/catalog.py` — каталожные операции поверх хранилища.
- `app/application/workflow.py` — бот-вью и навигация.
- `app/application/helpers/image_preview.py` — генерация превью `A vs B`.
- `app/repositories/sqlite.py` — подключения к SQLite, миграции и реализации репозиториев.

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
