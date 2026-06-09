# Конфигурация

Все переменные читаются из `.env` (см. `.env.example`). Pydantic-settings, `extra=ignore`.

## Обязательные

| Переменная | Описание |
|------------|----------|
| `TG_BOT_TOKEN` | Токен Telegram Bot от @BotFather |
| `CURSOR_API_KEY` | API key из [Cursor Integrations](https://cursor.com/dashboard/integrations) |
| `OPENAI_API_KEY` | Транскрипция голоса + эмбеддинги памяти |
| `WHITELIST_USER_IDS` | Telegram user ID через запятую; без них бот откажет в доступе |

## Доступ и роли

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `ADMIN_USER_IDS` | — | ID админов: `/plan`, `/do`, расширенное меню команд |

Проверки: `Settings.is_whitelisted()`, `Settings.is_admin()`, `Settings.can_use_mode()`.

## База данных

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `DATABASE_URL` | `postgresql://bot:botsecret@localhost:5432/tg_cursor_bot` | asyncpg DSN |
| `POSTGRES_PASSWORD` | `botsecret` | пароль Postgres в compose |

Docker compose переопределяет `DATABASE_URL` на `@postgres:5432`.

## Cursor Agent

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `CURSOR_MODEL` | `composer-2.5` | модель Cloud Agent |
| `WORKSPACE_PATH` | `./data/workspace` | workspace для cursor-sdk bridge; в Docker: `/data/workspace` |
| `DEFAULT_BRANCH` | `dev` | ветка по умолчанию для `/repo add` без branch |
| `DEFAULT_REPO_URL` | — (пусто) | GitHub URL; при **первом** заходе нового пользователя добавляется как активное репо (alias из имени репо). Суффиксы вроде `/actions` обрезаются |

## OpenAI

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `TRANSCRIBE_MODEL` | `gpt-4o-mini-transcribe` | STT для голосовых |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | векторы памяти (1536 dim) |

## Память

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `MEMORY_RECALL_K` | `3` | сколько chunks подмешивать в ask/plan |
| `MEMORY_LIST_LIMIT` | `10` | лимит `/memory` без query |
| `MEMORY_EMBED_MAX_CHARS` | `8000` | обрезка текста перед embedding |

## Очередь

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `JOB_QUEUE_DEPTH` | `2` | max ожидающих промптов на пользователя |

## Стрим UI

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `STREAM_THINKING` | `preview` | `off` \| `preview` \| `admin` — показ thinking в Telegram |
| `STREAM_THINKING_PREVIEW_CHARS` | `300` | длина preview thinking (plan/do) |

Логика: `stream_display.resolve_thinking_display()`.

## Фото

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `PHOTO_MAX_COUNT` | `20` | max изображений в одном промпте (1–100; потолок — лимит Cursor/Anthropic vision API; при >20 max сторона картинки 2000px вместо 8000px) |
| `MEDIA_GROUP_DELAY_SEC` | `1.0` | задержка сборки альбома Telegram |

## Пересланный контекст

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `FORWARD_CONTEXT_TIMEOUT_SEC` | `15` | автоотправка буфера пересылок без вашего вопроса |
| `FORWARD_CONTEXT_MAX_ITEMS` | `25` | max блоков пересылок в одной пачке (альбом = 1 блок) |
| `AGENT_SLOTS_MAX` | `8` | макс. слотов Cursor-агентов на пользователя (5–10) |

## Прочее

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `LOG_LEVEL` | `INFO` | уровень logging |

## Пример `.env`

```env
TG_BOT_TOKEN=123456:ABC...
CURSOR_API_KEY=key_...
OPENAI_API_KEY=sk-...
WHITELIST_USER_IDS=123456789,987654321
ADMIN_USER_IDS=123456789
DATABASE_URL=postgresql://bot:botsecret@localhost:5433/tg_cursor_bot
POSTGRES_PASSWORD=botsecret
WORKSPACE_PATH=./data/workspace
DEFAULT_BRANCH=dev
CURSOR_MODEL=composer-2.5
STREAM_THINKING=preview
JOB_QUEUE_DEPTH=2
MEMORY_RECALL_K=3
```

## Telegram Bot Commands (меню)

Регистрируются в `register_bot_commands`:

- Все пользователи: start, help, ask, mode, repo, new, remember, memory, status, cancel
- Admin дополнительно: plan, do

Per-chat scope для admin IDs через `BotCommandScopeChat`.
