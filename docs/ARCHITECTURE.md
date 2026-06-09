# Архитектура

## Контекст системы

- **Telegram Bot API** — long polling, один инстанс (конфликт при нескольких).
- **Cursor Cloud Agents** — через `cursor-sdk` (bridge + cloud repos).
- **PostgreSQL 16 + pgvector** — пользователи, репозитории, сессии агентов, семантическая память.
- **OpenAI API** — транскрипция голоса, эмбеддинги для памяти.
- **Workspace volume** — локальная рабочая директория для cursor-sdk bridge (`WORKSPACE_PATH`).

```
┌─────────────┐     long polling      ┌──────────────────┐
│  Telegram   │ ◄──────────────────► │   tg-cursor-bot  │
│   Client    │                       │  (python-telegram│
└─────────────┘                       │      -bot)       │
                                      └────────┬─────────┘
                                               │
                    ┌──────────────────────────┼──────────────────────────┐
                    ▼                          ▼                          ▼
            ┌───────────────┐          ┌───────────────┐          ┌───────────────┐
            │  PostgreSQL   │          │  cursor-sdk   │          │   OpenAI API  │
            │  + pgvector   │          │  Cloud Agents │          │ transcribe +  │
            └───────────────┘          └───────────────┘          │  embeddings   │
                                                                  └───────────────┘
```

## Слои приложения

| Слой | Путь | Назначение |
|------|------|------------|
| Entry | `src/tg_cursor_bot/__main__.py`, `app.py` | запуск polling, регистрация handlers |
| Handlers | `src/tg_cursor_bot/bot/handlers/` | команды Telegram, текст, голос, фото, callbacks |
| Services | `src/tg_cursor_bot/services/` | бизнес-логика: агент, очередь, память, стрим UI |
| Domain | `src/tg_cursor_bot/domain/` | модели, шаблоны промптов |
| DB | `src/tg_cursor_bot/db/` | asyncpg pool, repositories |
| Config | `src/tg_cursor_bot/config/settings.py` | pydantic-settings из `.env` |

### AppContext

Единый контекст (`app_context.py`), создаётся в `post_init`:

- `pool` — asyncpg
- `users`, `repos`, `agent_slots` — репозитории и сервис слотов агентов
- `memory` — индексация и recall
- `cursor` — CursorAgentService
- `transcription` — OpenAI STT
- `job_queue` — per-user FIFO очередь
- `active_runs`, `last_prompts` — in-memory состояние

## Поток обработки промпта

```
text/voice/photo → validate_prompt_request
forward          → ForwardContextBuffer (ждёт триггер или timeout)
                 → job_queue.submit
                 → _run_job
                      → memory.recall (ask/plan)
                      → build_prompt + cursor.run_prompt
                      → TelegramStreamRenderer (edit одного сообщения)
                      → memory.index_run
```

### Режимы (UserMode)

| Режим | Cursor mode | auto_create_pr | Память в промпт | Кто может |
|-------|-------------|----------------|-----------------|-----------|
| **ask** | `agent` | нет | да | все в whitelist |
| **plan** | `plan` | нет | да | admin |
| **do** | `agent` | да | нет | admin |

Ask: Cursor `agent` без PR; в промпт — правила «только текст в Telegram» (без правок кода, без MD-простыней). Опросник A/B/C — только для запросов про разработку, когда без выбора нельзя спланировать реализацию. Plan/Do — git-safety правила (ветка по умолчанию, без push в main/master без явной просьбы).

### CursorAgentService

1. `AsyncClient.launch_bridge(workspace=WORKSPACE_PATH)`
2. `agents.create` или `agents.resume(cursor_agent_id)`
3. `agent.send(prompt, SendOptions(mode=...))`
4. Стрим `run.messages()` → `StreamState` (assistant, thinking, tool_call, status)
5. `run.wait()` → финальный текст, PR URL, duration

### Очередь задач (JobQueue)

На пользователя:

- **1 активный** run
- до `JOB_QUEUE_DEPTH` (по умолчанию 2) **ожидающих**
- при переполнении — отказ с сообщением

Отмена (`/cancel`): очистка pending + `request_cancel` + `cursor.cancel_run` если есть active run.

### Семантическая память

- Каждый завершённый run → `memory_entries` (kind=`run`) с embedding
- `/remember` → kind=`note`
- Recall (top-k cosine, HNSW index) в ask/plan перед отправкой в Cursor
- `/memory query` — семантический поиск; без query — последние N записей

### Стриминг в Telegram

- Одно сообщение редактируется (`TelegramStreamRenderer`), rate limit ~1 edit/sec
- Анимация статуса (`AnimatedStatus`) пока нет видимого вывода; после первого текста/инструментов — строка «Агент работает» со спиннером и `typing` до финала
- `STREAM_THINKING`: off | preview | admin — видимость «thinking» блоков
- Пока run идёт — текст в сообщении **без** форматирования (сырой markdown из Cursor)
- На `finalize`: `markdown_sanitize` → `telegramify-markdown.convert()` → `text` + `entities` (без `parse_mode`)
- При сбое конвертации или `BadRequest` от Telegram — fallback `readable_plain` (без литералов `##` / `**`), не сырой markdown
- Модули: `services/markdown_sanitize.py`, `services/markdown_format.py`

### Фото

- Поддержка photo, image document, media groups (альбомы)
- До `PHOTO_MAX_COUNT` изображений → `SDKImage` в Cursor
- Без caption — дефолтный промпт «Разбери скриншот…»

### Пересланный контекст

- Handler `forward` (group 0) → `ForwardContextBuffer`
- Пересылки копятся; ваш текст/голос — триггер flush
- Fallback: `FORWARD_CONTEXT_TIMEOUT_SEC` после последней пересылки
- Одна пачка → один `submit_user_prompt`; при reject очереди буфер сохраняется
- Формат промпта: блоки с `[Forwarded …]`, разделитель `---`, блок `[Your message]`

### Слоты агентов

- До `AGENT_SLOTS_MAX` (по умолчанию 8) именованных слотов на пользователя (`user_agent_slots`)
- Активный слот хранит `cursor_agent_id`; переключение через `/agents` или кнопку «Агенты» — **без** archive в Cursor
- `/new` и «+ Новый агент» создают новый слот и делают его активным; старые слоты сохраняются
- Run идёт в активный слот и его `repo_id`; при activate слота синхронизируется активное репо в `user_repos`
- Смена репо через `/repo` не сбрасывает контекст; у пустого слота (без `cursor_agent_id`) обновляется `repo_id`

## Схема БД

| Таблица | Ключевые поля |
|---------|---------------|
| `users` | `tg_user_id`, `current_mode`, `is_admin` |
| `user_repos` | `alias`, `github_url`, `default_branch`, `is_active` |
| `user_agent_slots` | `label`, `cursor_agent_id`, `repo_id`, `active_run_id`, `is_active` |
| `memory_entries` | `kind`, `title`, `body`, `embedding vector(1536)`, метаданные run |

Миграции: Alembic в `alembic/versions/`. DDL **не** применяется кодом бота при локальном запуске; в Docker entrypoint выполняет `alembic upgrade head`.

## Безопасность

- **Whitelist** (`WHITELIST_USER_IDS`) — gate на все updates (group -1)
- **Admin** (`ADMIN_USER_IDS`) — plan/do, расширенное меню команд
- Секреты только в `.env`, не коммитить

## Зависимости (ключевые)

- `python-telegram-bot` 21.x
- `cursor-sdk` ≥ 0.1.0
- `asyncpg`, `pgvector`
- `openai`, `telegramify-markdown`
- `alembic`, `pydantic-settings`
