# Telegram ↔ Cursor Cloud Agents Bot

Natural-language Telegram interface (text, voice, photos) to Cursor Cloud Agents with ask/plan/do modes, streaming updates, multi-repo support, semantic memory (Postgres + pgvector), and access control.

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

4. **PostgreSQL 16 + pgvector** — apply migrations before first bot start:



```powershell

docker compose up -d postgres

.\.venv\Scripts\Activate.ps1

pip install -e .

$env:DATABASE_URL="postgresql://bot:botsecret@localhost:5433/tg_cursor_bot"

alembic upgrade head

```

The bot checks Postgres connectivity and the `vector` extension on startup; it does **not** apply DDL when run locally outside Docker.

In Docker, `entrypoint.sh` runs `alembic upgrade head` automatically before start.

New revisions: `alembic revision -m "description"` then `alembic upgrade head`.



## Local run (Windows)



```powershell

python -m venv .venv

.\.venv\Scripts\Activate.ps1

pip install -e .

$env:DATABASE_URL="postgresql://bot:botsecret@localhost:5433/tg_cursor_bot"

python -m tg_cursor_bot

```

Requires a running Postgres with schema applied (see above).



## Docker (server deploy)



Postgres data and cursor-sdk workspace use **named volumes**.



```powershell

docker compose up -d --build

```

(Migrations run automatically via entrypoint on container start.)

### Prod (185.244.49.94)



From Windows (PuTTY `pscp`/`plink`, `.env` in repo root):



```powershell

.\scripts\deploy-to-prod.ps1

```



Then migrations on the server (if not run yet):



```powershell

echo y | plink -ssh -l const -i "C:\Users\vonwa\.ssh\const.ppk" 185.244.49.94 "cd /home/const/tg-cursor-bot && docker compose exec -T bot alembic upgrade head"

```



See [docs/OPERATIONS.md](./docs/OPERATIONS.md) and `.cursor/rules/servers-access.mdc`.



Important:

- `DATABASE_URL` is set by compose for the bot service.

- `WORKSPACE_PATH=/data/workspace` inside the container (volume `bot-data`).

- Run **one** bot instance only (Telegram polling conflict otherwise).



Host bind mount for workspace:



```powershell

docker compose -f docker-compose.yml -f docker-compose.bind.yml up -d --build

```



Backup Postgres:



```powershell

docker compose exec -T postgres pg_dump -U bot tg_cursor_bot -f backup.sql

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

2. Add a repo: `/repo add backend https://github.com/you/repo` (ветка `dev` по умолчанию)

3. Select mode: `/ask` (chat, all users); `/plan` and `/do` (admins only) — or buttons on `/start` and `/status`

4. Send text, voice, or photo



## Commands



| Command | Description |

|---------|-------------|

| `/start` `/help` | Full usage guide |

| `/ask` `/plan` `/do` | Set mode |

| `/mode` | Show / pick mode (inline buttons) |

| `/new` | New cloud agent session (resets to ask) |

| `/repo` | List/switch/add repositories (inline buttons) |

| `/remember` | Save a note to memory (active repo) |

| `/memory` | Last 10 entries; `/memory query` — semantic search |

| `/status` | Current task / queue status |

| `/cancel` | Cancel active run and clear queue |



## Environment

See [docs/CONFIGURATION.md](./docs/CONFIGURATION.md) and `.env.example`.

## Notes

- Ask mode prepends: «ПРОСТО ОТВЕЧАЙ код не трогай» and uses Cursor `plan` mode.
- Ask/plan runs recall top-k memory chunks into the prompt; `/do` does not.
- Every run is indexed into memory.
- Plan/Do modes prepend git-safety rules (see [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md)).
- Voice: OpenAI `gpt-4o-mini-transcribe`. Photos: up to 20 by default (`PHOTO_MAX_COUNT`, Cursor API max 100).
- Streaming updates edit a single Telegram message (max ~1 edit/sec).

