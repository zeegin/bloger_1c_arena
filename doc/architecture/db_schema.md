# Структура базы данных

Бот использует SQLite. Все перечисленные таблицы создаются и мигрируются в `SQLiteDatabase.init()` (`app/repositories/sqlite.py`) при старте приложения. Ниже указаны основные сущности, их столбцы, индексы и связи.

## Таблица `users`
| Поле | Тип | Описание |
| --- | --- | --- |
| `id` | INTEGER PK | Внутренний идентификатор пользователя |
| `tg_user_id` | INTEGER UNIQUE | Telegram ID пользователя |
| `username` | TEXT | username без `@` |
| `first_name` | TEXT | отображаемое имя |
| `favorite_channel_id` | INTEGER FK → `channels.id` | Любимчик из режима deathmatch |
| `classic_games` | INTEGER | Количество сыгранных классических игр (инкрементируется триггером при вставке в `votes`) |
| `reward_stage` | INTEGER | Порог, для которого уже выдан секретный приз (0 / 350 / 700) |
| `deathmatch_unlocked` | INTEGER | Флаг, что пользователь увидел уведомление о доступе к Deathmatch |
| `rating_unlocked` | INTEGER | Флаг, что доступ к рейтингу уже открыт после порогового числа игр |
| `created_at` | TEXT | время регистрации (`datetime('now')`) |

Дополнительно: при `INSERT ... ON CONFLICT` Telegram-данные обновляются, любимчик устанавливается отдельным методом `set_user_favorite_channel`.

## Таблица `channels`
| Поле | Тип | Описание |
| --- | --- | --- |
| `id` | INTEGER PK |
| `tg_url` | TEXT UNIQUE | Ссылка на канал |
| `title` | TEXT | Название канала |
| `description` | TEXT | Краткое описание |
| `image_url` | TEXT | URL аватара |
| `rating` | REAL | Текущий Elo рейтинг (по умолчанию 1500) |
| `games` | INTEGER | Количество сыгранных матчей (классическое голосование) |
| `wins` | INTEGER | Победы в классическом режиме |
| `losses` | INTEGER | Поражения в классическом режиме |
| `created_at` | TEXT | Дата добавления |

Индексы:
- `idx_channels_rating` по рейтингу (DESC) для выборки топа.

Заполняется из `channels.yaml` (адаптер `app/infrastructure/channels_loader.py`, функция `sync_channels`, которая вызывает `SQLiteChannelsRepository.add_or_update`).

## Таблица `votes`
| Поле | Тип | Описание |
| --- | --- | --- |
| `id` | INTEGER PK |
| `user_id` | INTEGER FK → `users.id` | Автор голоса |
| `channel_a_id`, `channel_b_id` | INTEGER FK → `channels.id` | Участники матча |
| `winner_channel_id` | INTEGER nullable | Победитель (`NULL` для ничьи) |
| `rating_a_before`, `rating_b_before` | REAL | Рейтинги до матча |
| `rating_a_after`, `rating_b_after` | REAL | Рейтинги после матча |
| `created_at` | TEXT | Таймстамп |

Назначение: аудит классических голосований + источник статистики (кол-во игр). При ничьей поле `winner_channel_id` остаётся `NULL`, но рейтинги и `games` обновляются через `SQLiteVotesRepository.record_vote`.

Индексы:
- `idx_votes_user_time` (`user_id`, `created_at DESC`) для аналитики/истории.
- `idx_votes_user` (`user_id`) для быстрых агрегаций по пользователю.

Триггер `trg_votes_classic_games` автоматически увеличивает `users.classic_games` при вставке голосов, а при миграциях инициализация вызывает пересчёт значения из существующих строк.

## Таблица `user_pair_seen`
| Поле | Тип | Описание |
| --- | --- | --- |
| `user_id` | INTEGER FK → `users.id` |
| `channel_a_id` | INTEGER FK → `channels.id` |
| `channel_b_id` | INTEGER FK → `channels.id` |
| `seen_at` | TEXT | когда пара была показана |

PK составной (`user_id`, `channel_a_id`, `channel_b_id`). Используется в `pair.get_pair` для минимизации повторов.

## Таблица `deathmatch_state`
| Поле | Тип | Описание |
| --- | --- | --- |
| `user_id` | INTEGER PK / FK → `users.id` |
| `champion_id` | INTEGER FK → `channels.id` | Текущий чемпион в deathmatch |
| `seen_ids` | TEXT (JSON) | Каналы, уже встречавшиеся пользователю |
| `remaining_ids` | TEXT (JSON) | Очередь оставшихся претендентов |
| `updated_at` | TEXT | Время последнего изменения |

Используется для возобновления deathmatch между голосами. Содержимое сериализуется/десериализуется как JSON списки.

## Таблица `deathmatch_votes`
| Поле | Тип | Описание |
| --- | --- | --- |
| `id` | INTEGER PK |
| `user_id` | INTEGER FK → `users.id` |
| `champion_id` | INTEGER nullable | Чемпион перед текущим голосом |
| `channel_a_id`, `channel_b_id` | INTEGER FK → `channels.id` | Участники раунда |
| `winner_channel_id` | INTEGER FK → `channels.id` | Победитель раунда |
| `created_at` | TEXT | Таймстамп |

Хранит историю deathmatch-боёв. *Не* влияет на рейтинг, используется для потенциального анализа/статистики.

## Таблица `vote_tokens`
| Поле | Тип | Описание |
| --- | --- | --- |
| `token` | TEXT PK | Idempotency-ключ для инлайн-кнопки |
| `user_id` | INTEGER FK → `users.id` |
| `vote_type` | TEXT | `classic` / `deathmatch` |
| `channel_a_id`, `channel_b_id` | INTEGER FK → `channels.id` | Пара каналов, за которых был сгенерирован токен |
| `consumed` | INTEGER | Флаг использования (0/1) |
| `created_at` | TEXT | Время генерации кнопки |
| `consumed_at` | TEXT nullable | Метка времени после использования |

Создаётся при рендеринге клавиатуры (`VoteTokensRepository.create`). Обработчик голосования вызывает `VoteTokensRepository.consume` c проверкой пользователя, типа голосования и конкретной пары каналов; повторные нажатия или попытки подменить идентификаторы отклоняются.

## Представление любимчиков
`users.favorite_channel_id` (обновляется при завершении deathmatch) + вспомогательная выборка `list_favorite_channels`, которая считает количество фанатов на канал. Эти данные выводятся в разделе «Любимчики».

## Полезные вспомогательные запросы
- `SQLiteStatsRepository.rating_stats()` — общее число голосов (`votes`) и пользователей (`users`).
- `SQLiteChannelsRepository.list_top(limit)` / `list_all()` — рэнкинги для топ-20 и ТОП-100/«все каналы».
- `SQLitePairingRepository.mark_seen()` / `has_seen_pair()` — предотвращение повторных пар в классике.
- `SQLiteDeathmatchRepository.log_vote()` — аудит deathmatch.

## Миграции
Все изменения схемы добавляются при инициализации `SQLiteDatabase.init()` через `_ensure_*` методы, которые выполняют `ALTER TABLE ... ADD COLUMN` (с игнорированием «duplicate column»), а для `votes` — полное пересоздание, когда нужно убрать `NOT NULL`.
