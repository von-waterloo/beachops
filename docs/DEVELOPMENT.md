# Разработка

## Требования

- Python ≥ 3.10 (Docker: 3.12)
- PostgreSQL 16 + расширение `vector` (pgvector)
- Node.js — не нужен напрямую; `cursor-sdk` поднимает bridge сам
- ffmpeg — для обработки голоса (в Docker уже установлен)

## Локальная установка (Windows)

```powershell
cd "d:\Work\Cursor Bot"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
# заполнить .env
```

### Postgres локально

```powershell
docker compose up -d postgres
```

Порт на хосте: **5433** → 5432 в контейнере (см. `docker-compose.yml`).

### Миграции

```powershell
.\.venv\Scripts\Activate.ps1
$env:DATABASE_URL="postgresql://bot:botsecret@localhost:5433/tg_cursor_bot"
alembic upgrade head
```

> Бот при локальном `python -m tg_cursor_bot` **не** применяет миграции — только проверяет подключение и extension `vector`.

Новая ревизия (создаёте и запускаете сами):

```powershell
alembic revision -m "описание"
alembic upgrade head
```

### Запуск бота

```powershell
.\.venv\Scripts\Activate.ps1
$env:DATABASE_URL="postgresql://bot:botsecret@localhost:5433/tg_cursor_bot"
python -m tg_cursor_bot
```

## Структура проекта

```
src/tg_cursor_bot/
├── __main__.py           # точка входа
├── app.py                # Application factory, handlers registry
├── app_context.py        # DI-контекст
├── config/settings.py    # env → Settings
├── domain/
│   ├── models.py         # UserMode, RepoConfig, …
│   └── prompts.py        # префиксы ask/plan/do, memory block
├── bot/handlers/
│   ├── start.py          # /start, /help
│   ├── mode.py           # /ask, /plan, /do, /mode
│   ├── repo.py           # /repo
│   ├── agent.py          # /new
│   ├── memory.py         # /remember, /memory
│   ├── status.py         # /status
│   ├── cancel.py         # /cancel
│   ├── text.py           # текстовые промпты
│   ├── voice.py          # голос
│   ├── photo.py          # фото / альбомы
│   └── callbacks.py      # inline-кнопки
├── services/
│   ├── run_executor.py   # оркестрация run
│   ├── cursor_agent.py   # cursor-sdk
│   ├── job_queue.py      # очередь per user
│   ├── memory_service.py
│   ├── embedding_service.py
│   ├── transcription.py
│   ├── stream_bridge.py  # StreamState
│   ├── stream_display.py
│   ├── telegram_renderer.py
│   ├── status_animation.py
│   ├── cancel_service.py
│   ├── inline_keyboards.py
│   ├── ui_copy.py        # тексты для пользователя
│   └── telegram_images.py
└── db/
    ├── connection.py
    └── repositories/     # users, repos, agent_slots, memory

alembic/                  # миграции
tests/                    # pytest
scripts/
├── deploy-to-prod.ps1
└── migrate_sqlite_to_postgres.py
```

## Тесты

```powershell
.\.venv\Scripts\Activate.ps1
pytest
```

Основные тесты: `test_stream_bridge`, `test_stream_display`, `test_telegram_images`, `test_import_smoke`.

## Добавление handler

1. Создать функцию в `bot/handlers/`.
2. Зарегистрировать в `app.py` → `register_handlers`.
3. При новой команде — добавить в `services/bot_commands.py`.
4. Обновить [USER_GUIDE.md](./USER_GUIDE.md) и [ARCHITECTURE.md](./ARCHITECTURE.md) при существенных изменениях.

## Миграция с SQLite

Если есть legacy `data/bot.db`:

```powershell
.\.venv\Scripts\Activate.ps1
python scripts/migrate_sqlite_to_postgres.py --sqlite .\data\bot.db
```

Нужен `OPENAI_API_KEY` для эмбеддингов исторических run.

## Полезные env для разработки

```env
LOG_LEVEL=DEBUG
DATABASE_URL=postgresql://bot:botsecret@localhost:5433/tg_cursor_bot
WORKSPACE_PATH=./data/workspace
```

## Cursor rule для документации

При серьёзных изменениях см. `.cursor/rules/docs-sync.mdc` — агент должен обновлять docs.
