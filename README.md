# BeachOps

Telegram-бот и Mini App для диалога с вашими Cursor-агентами: ask/plan/do,
несколько слотов, голос, очередь задач и approvals — в одном приятном чате.

**Полная документация:** [docs/README.md](./docs/README.md)

| Раздел | Ссылка |
|--------|--------|
| Архитектура | [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) |
| Пользователь Telegram | [docs/USER_GUIDE.md](./docs/USER_GUIDE.md) |
| Разработка | [docs/DEVELOPMENT.md](./docs/DEVELOPMENT.md) |
| Эксплуатация / деплой | [docs/OPERATIONS.md](./docs/OPERATIONS.md) |
| Конфигурация (.env) | [docs/CONFIGURATION.md](./docs/CONFIGURATION.md) |

## Deploy your own copy

Каждый деплой — изолированный single-tenant инстанс. Чужой бот, Cursor/OpenAI ключи, репозитории и Telegram ID автора сюда не попадают: вы подставляете **свои** значения в `.env`.

1. Скопируйте `.env.example` → `.env` (там только обязательное — остальное с дефолтами).
2. Заполните ключи и `OWNER_USER_IDS`, `POSTGRES_PASSWORD`, `DATA_ENCRYPTION_KEY`, `REPOSITORY_POLICY_JSON`.
3. Подключите нужные репозитории в [Cursor Dashboard](https://cursor.com/dashboard).
4. Поднимите стек:

```powershell
docker compose up -d --build
```

Сервисы: `postgres`, `redis`, `migrate`, один polling `bot`, `worker`, `api`, `webapp` (порт `8080`).

Compose сам задаёт `DATABASE_URL` и `REDIS_URL` внутри сети. Workspace Cursor — volume `bot-data` (`WORKSPACE_PATH=/data/workspace`).

Опционально Mini App: публичный HTTPS в `WEBAPP_BASE_URL` (Telegram не принимает HTTP/IP) и reverse-proxy на `:8080`.

Опционально bind-mount workspace:

```powershell
docker compose -f docker-compose.yml -f docker-compose.bind.yml up -d --build
```

Бэкап Postgres:

```powershell
docker compose exec -T postgres pg_dump -U bot tg_cursor_bot > backup.sql
```

Важно: **один** процесс бота на один `TG_BOT_TOKEN` (иначе Conflict на long polling).

Подробности: [docs/OPERATIONS.md](./docs/OPERATIONS.md), [docs/CONFIGURATION.md](./docs/CONFIGURATION.md).

## Prerequisites (локальная разработка)

1. `.env.example` → `.env`, свои ключи.
2. GitHub в [Cursor Dashboard](https://cursor.com/dashboard).
3. API key в [Integrations](https://cursor.com/dashboard/integrations).
4. Roles, `DATA_ENCRYPTION_KEY`, `REPOSITORY_POLICY_JSON`.
5. PostgreSQL 16 + pgvector + Redis:

```powershell
docker compose up -d postgres redis
.\.venv\Scripts\Activate.ps1
pip install -e .
$env:DATABASE_URL="postgresql://bot:botsecret@localhost:5433/tg_cursor_bot"
alembic upgrade head
```

В Docker one-shot `migrate` делает `alembic upgrade head` до старта bot/API/worker.

## Local run (Windows)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
$env:DATABASE_URL="postgresql://bot:botsecret@localhost:5433/tg_cursor_bot"
python -m beachops
```

Нужны Postgres, Redis, схема, encryption key и repository policy.

## Maintainer's own production reference (not required for your deployment)

Прод автора (185.244.49.94, runner host-185): **push в `main` или `dev` → CI → Deploy prod**.
Rollback — Telegram /rollback или Actions workflow_dispatch. Legacy с Windows:

`powershell
.\scripts\deploy-to-prod.ps1
`

См. [docs/SELF_DEPLOY.md](./docs/SELF_DEPLOY.md), [docs/OPERATIONS.md](./docs/OPERATIONS.md) и .cursor/rules/servers-access.mdc.

## Migrate from legacy SQLite

Если есть `data/bot.db` от старой версии:

```powershell
.\.venv\Scripts\Activate.ps1
python scripts/migrate_sqlite_to_postgres.py --sqlite .\data\bot.db
```

`OPENAI_API_KEY` нужен для эмбеддингов исторических run (желательно).

## First setup in Telegram

`/start` — quick-start (repo, mode, text/voice, queue, cancel).

1. `/start`
2. Репозиторий: `/repo add https://github.com/you/repo` или Mini App → Репо
   (любой HTTPS GitHub URL; базовая ветка выбирается там же).
3. `/do` — сразу в базовую ветку; `/ask` — спросить; `/plan`/`/task` — план с approve.
4. Текст, голос или фото.

## Commands

| Command | Description |
|---------|-------------|
| `/start` (alias `/help`) | Full usage guide |
| `/ask` `/plan` `/do` `/task` | Чат / план / действие на базовой ветке / задача через план |
| `/status` (alias `/mode`) | Mode, model, token, active task / queue — with inline buttons |
| `/agents` | List/switch cloud agent sessions |
| `/new` | New cloud agent session (resets to ask) |
| `/repo` | List/switch/add repositories (inline buttons) |
| `/remember` | Save a note to memory (active repo) |
| `/memory` | Last 10 entries; `/memory query` — semantic search |
| `/cancel` | Cancel active run and clear queue |
| `/jobs` `/approvals` | Durable jobs and owner decisions |
| `/rollback` | Owner: redeploy previous (or given) prod SHA |
| `/dashboard` | Open the Telegram Mini App |

## Environment

See [docs/CONFIGURATION.md](./docs/CONFIGURATION.md) and `.env.example`.

## Notes

- Ask is externally read-only: no current-branch writes or PR flags.
- Ask/plan runs recall top-k memory chunks; write runs require an approved plan hash.
- Every run is indexed into memory.
- Write runs can create an isolated branch/PR only; merge, deploy, force-push and production access are blocked.
- Voice: OpenAI `gpt-4o-mini-transcribe`. Photos: up to 20 by default (`PHOTO_MAX_COUNT`, Cursor API max 100).
- Streaming updates edit a single Telegram message (max ~1 edit/sec).
