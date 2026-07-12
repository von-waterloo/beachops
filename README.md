# BeachOps

**Your Cursor cloud agents, reachable from Telegram.**

Ask a question on the subway. Plan a change from the Mini App. Ship a fix to `dev` and watch CI put it on prod. BeachOps is the control room: one bot, durable jobs, named agent slots, voice when you want it — and Cursor Cloud Agents doing the actual coding.

This is **not** a remote control for a chat tab open in Cursor on your laptop. BeachOps owns its own cloud agent sessions. You talk to them from Telegram; they work on your GitHub repos.

Full docs live in [docs/README.md](./docs/README.md).

| Doc | What’s inside |
|-----|----------------|
| [Architecture](./docs/ARCHITECTURE.md) | Stack, run pipeline, DB |
| [User guide](./docs/USER_GUIDE.md) | Commands, modes, Telegram UX |
| [Development](./docs/DEVELOPMENT.md) | Local setup, layout, tests |
| [Operations](./docs/OPERATIONS.md) | Docker, backups, migrate |
| [Self-deploy](./docs/SELF_DEPLOY.md) | `main`/`dev` → CI → prod |
| [Configuration](./docs/CONFIGURATION.md) | Every env knob |

---

## Why it exists

Cursor is great at the keyboard. BeachOps is for when you’re *not* at the keyboard:

- **Ask** — read the repo, answer in Telegram (no writes)
- **Plan** — investigate, produce a plan; owner approves, then do (unless `AUTO_APPROVE_PLANS=true`)
- **Do** — commit and push on your base branch (`dev` by default); `main`/`master` stay PR-only

Plus: multiple named agent sessions, semantic memory, a real job queue, owner approvals when you want them, and a Mini App for voice and the dashboard.

**Self-improve loop (maintainer):** pin this repo on `dev` → `/do` → agent pushes → green CI → auto-deploy. Same path for your own instance once Actions is wired.

---

## Features at a glance

- Telegram bot + HTTPS Mini App (dashboard, voice, repos, queue)
- Cursor **Cloud Agents** via `cursor-sdk` (`create` / `resume`, streaming back into one Telegram message)
- Up to 8 named **agent slots** per user — switch, rename, delete in Telegram and Mini App (**Работа**)
- Durable jobs (Postgres + Redis/ARQ), cancel, reconciler if Telegram UI lags
- GitHub repos: open mode or allowlist; soft pin via OAuth in the Mini App
- Memory: every finished run is indexed; ask/plan recall top-k
- Models & Cursor accounts (`mt` / `mt2` / `mt3`) switchable from `/status`
- Owner `/rollback` via GitHub Actions `workflow_dispatch`

---

## Deploy your own copy

Each deploy is a **single-tenant** box. Your bot token, your Cursor/OpenAI keys, your Telegram IDs. Nobody else’s.

1. Copy `.env.example` → `.env` and fill the required block (BotFather, Cursor, OpenAI, owner IDs, Postgres password, encryption key, repo policy).
2. Connect the repos you care about in the [Cursor Dashboard](https://cursor.com/dashboard).
3. Bring the stack up:

```powershell
docker compose up -d --build
```

You get: `postgres`, `redis`, `migrate`, one polling `bot`, `worker`, `api`, `webapp` on `:8080`.

Compose wires `DATABASE_URL` / `REDIS_URL` on the internal network. Cursor SDK workspace lives in volume `bot-data` (`WORKSPACE_PATH=/data/workspace`).

Optional Mini App: put a public HTTPS URL in `WEBAPP_BASE_URL` (Telegram rejects bare HTTP/IP), proxy to `:8080`, and `/setdomain` in BotFather.

Optional bind-mount for the workspace:

```powershell
docker compose -f docker-compose.yml -f docker-compose.bind.yml up -d --build
```

Postgres dump:

```powershell
docker compose exec -T postgres pg_dump -U bot tg_cursor_bot > backup.sql
```

**One bot process per `TG_BOT_TOKEN`.** Two pollers = Telegram Conflict. Guaranteed.

More: [OPERATIONS.md](./docs/OPERATIONS.md), [CONFIGURATION.md](./docs/CONFIGURATION.md).

---

## Local development

1. `.env.example` → `.env` with your keys.
2. GitHub connected in Cursor; API key from [Integrations](https://cursor.com/dashboard/integrations).
3. Postgres 16 + pgvector + Redis:

```powershell
docker compose up -d postgres redis
.\.venv\Scripts\Activate.ps1
pip install -e .
$env:DATABASE_URL="postgresql://bot:botsecret@localhost:5433/tg_cursor_bot"
alembic upgrade head
python -m beachops
```

In full Compose, the one-shot `migrate` service runs `alembic upgrade head` before bot/API/worker start.

---

## First five minutes in Telegram

1. `/start`
2. Pin a repo: `/repo add https://github.com/you/repo` or Mini App → Repos (any HTTPS GitHub URL; base branch defaults to `dev`)
3. `/ask` to chat, `/plan` / `/task` for plan → approve → do, `/do` to write on the base branch
4. Send text, voice, or a screenshot

No active repo → no prompt. That’s intentional.

---

## Commands

| Command | What it does |
|---------|----------------|
| `/start` (`/help`) | Quick-start + status |
| `/ask` `/plan` `/do` `/task` | Chat / plan / write / task-via-plan |
| `/status` (`/mode`) | Mode, model, token, queue — with buttons |
| `/agents` | List / switch slots; rename & delete |
| `/new` | New agent slot (keeps the old ones) |
| `/repo` | List / switch / add repositories |
| `/remember` | Save a note into memory (active repo) |
| `/memory` | Recent notes; `/memory query` — semantic search |
| `/cancel` | Kill active run + clear queue |
| `/jobs` `/approvals` | Durable jobs & owner decisions |
| `/rollback` | Owner: redeploy previous (or given) SHA |
| `/dashboard` | Open the Mini App |

---

## Maintainer production (optional)

Author’s box (host-185): **push to `main` or `dev` → green CI → Deploy prod**.

- Self-improve: agent works on `dev`, CI deploys the same way
- Rollback: Telegram `/rollback` or Actions `workflow_dispatch`
- Legacy one-shot: `.\scripts\deploy-to-prod.ps1`

Details: [SELF_DEPLOY.md](./docs/SELF_DEPLOY.md), [OPERATIONS.md](./docs/OPERATIONS.md).

---

## Migrate from legacy SQLite

If you still have `data/bot.db` from an older build:

```powershell
.\.venv\Scripts\Activate.ps1
python scripts/migrate_sqlite_to_postgres.py --sqlite .\data\bot.db
```

`OPENAI_API_KEY` helps re-embed historical runs.

---

## Environment

See [CONFIGURATION.md](./docs/CONFIGURATION.md) and `.env.example`. Short version: BotFather token, Cursor API key, OpenAI key, owner Telegram IDs, Postgres password, `DATA_ENCRYPTION_KEY`, and `REPOSITORY_POLICY_JSON` (empty list = open mode for any HTTPS GitHub URL; writes to `main`/`master` still forbidden).

---

## Things worth knowing

- Ask is externally read-only — no current-branch writes, no PR flags.
- Ask/plan recall memory; write runs need an approved plan hash when approvals are on.
- Every finished run is indexed into memory.
- On `main`/`master` as base, do creates an isolated branch + PR only. Merge, force-push, and “deploy from the agent” stay blocked by policy.
- Voice uses OpenAI `gpt-4o-mini-transcribe`. Photos: up to 20 by default (`PHOTO_MAX_COUNT`).
- Streaming edits one Telegram message (~1 edit/sec). The source of truth is Postgres if the UI lags.

---

## Roadmap (from the product call)

1. ~~**Cloud-only product surface**~~ — **done**: Cursor Cloud only; Windows worker out of UX/docs.
2. ~~**Agent hygiene in the Mini App**~~ — **done**: rename, delete, create on **Работа**.
3. **Self-improve + deploy** — keep `dev` → CI → prod sharp; that's the loop BeachOps is for.
4. **Honest UX copy** — BeachOps sessions, not "your open Cursor tab." *(current)*
5. **Polish the control room** — voice, queue, timeline without dual-runtime fog. *(current)*

PRs and issues welcome.