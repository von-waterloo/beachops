# BeachOps

Private Telegram control plane for Cursor Cloud Agents: read-only inspection, mandatory plan/owner approval before writes, durable ARQ jobs, audit/redaction, panic lock, and a voice-first Telegram Mini App.

**Полная документация:** [docs/README.md](./docs/README.md)

| Раздел | Ссылка |
|--------|--------|
| Архитектура | [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) |
| Пользователь Telegram | [docs/USER_GUIDE.md](./docs/USER_GUIDE.md) |
| Разработка | [docs/DEVELOPMENT.md](./docs/DEVELOPMENT.md) |
| Эксплуатация / деплой | [docs/OPERATIONS.md](./docs/OPERATIONS.md) |
| Конфигурация (.env) | [docs/CONFIGURATION.md](./docs/CONFIGURATION.md) |

## Prerequisites



1. Copy `.env.example` to `.env` and fill in values.

2. Connect GitHub in [Cursor Dashboard](https://cursor.com/dashboard).

3. Create API key at [Integrations](https://cursor.com/dashboard/integrations).

4. Configure explicit `VIEWER_USER_IDS`, `OPERATOR_USER_IDS`, `OWNER_USER_IDS`, `DATA_ENCRYPTION_KEY` and `REPOSITORY_POLICY_JSON`.

5. **PostgreSQL 16 + pgvector + Redis** — Docker starts both and runs the one-shot migration service:



```powershell

docker compose up -d postgres redis

.\.venv\Scripts\Activate.ps1

pip install -e .

$env:DATABASE_URL="postgresql://bot:botsecret@localhost:5433/tg_cursor_bot"

alembic upgrade head

```

BeachOps checks PostgreSQL, Redis and the `vector` extension on startup.

In Docker, the one-shot `migrate` service runs `alembic upgrade head` before bot/API/worker.

New revisions: `alembic revision -m "description"` then `alembic upgrade head`.



## Local run (Windows)



```powershell

python -m venv .venv

.\.venv\Scripts\Activate.ps1

pip install -e .

$env:DATABASE_URL="postgresql://bot:botsecret@localhost:5433/tg_cursor_bot"

python -m beachops

```

Requires PostgreSQL, Redis, applied schema, encryption key and repository policy.



## Docker (server deploy)



Postgres, Redis and cursor-sdk workspace use **named volumes**.



```powershell

docker compose up -d --build

```

Stack: `postgres`, `redis`, `migrate`, one polling `bot`, `worker`, `api`, `webapp`.

### Prod (185.244.49.94)



From Windows (PuTTY `pscp`/`plink`, `.env` in repo root):



```powershell

.\scripts\deploy-to-prod.ps1

```



See [docs/OPERATIONS.md](./docs/OPERATIONS.md) and `.cursor/rules/servers-access.mdc`.



Important:

- `DATABASE_URL` and `REDIS_URL` are set by compose.

- `WORKSPACE_PATH=/data/workspace` inside the container (volume `bot-data`).

- Run **one** bot instance only (Telegram polling conflict otherwise).



Host bind mount for workspace:



```powershell

docker compose -f docker-compose.yml -f docker-compose.bind.yml up -d --build

```



Backup Postgres:



```powershell

docker compose exec -T postgres pg_dump -U bot tg_cursor_bot > backup.sql

```



## Migrate from legacy SQLite



If you have `data/bot.db` from an older version:



```powershell

.\.venv\Scripts\Activate.ps1

python scripts/migrate_sqlite_to_postgres.py --sqlite .\data\bot.db

```



Requires `OPENAI_API_KEY` for embedding historical runs (optional but recommended).



## First setup in Telegram



Send `/start` — full quick-start guide (repo, mode, text/voice, queue, cancel).



1. `/start`

2. Select a repository from the server-side allowlist (`/repo`). `/repo add` accepts only exact allowlisted URL/branch pairs.

3. Use `/ask` for read-only work or `/task` to create a plan. A write-run starts only from a one-time owner approval.

4. Send text, voice, or photo



## Commands



| Command | Description |

|---------|-------------|

| `/start` (alias `/help`) | Full usage guide |

| `/ask` `/plan` `/task` | Read-only answer or mandatory planning phase |

| `/status` (alias `/mode`) | Mode, model, token, active task / queue — with inline buttons |

| `/agents` | List/switch cloud agent sessions |

| `/new` | New cloud agent session (resets to ask) |

| `/repo` | List/switch/add repositories (inline buttons) |

| `/remember` | Save a note to memory (active repo) |

| `/memory` | Last 10 entries; `/memory query` — semantic search |

| `/cancel` | Cancel active run and clear queue |
| `/jobs` `/approvals` | Durable jobs and owner decisions |
| `/panic` `/unpanic` | Emergency stop and one-time owner re-enable |
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

