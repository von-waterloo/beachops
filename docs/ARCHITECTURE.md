# Архитектура

## Контекст системы

- **Telegram Bot API** — long polling, один инстанс (конфликт при нескольких).
- **Cursor Cloud Agents** — единственный execution plane продукта (`cursor-sdk`, bridge + cloud repos).
- **PostgreSQL 16 + pgvector** — пользователи, репозитории, сессии агентов, семантическая память.
- **Redis + ARQ** — durable jobs, distributed actor locks, rate limits, replay protection,
  short-lived hot cache (dashboard, auth bootstrap, embeddings).
- **FastAPI + React Mini App** — dashboard, approvals, realtime voice.
- **OpenAI API** — realtime STT, streaming TTS, эмбеддинги.
- **Workspace volume** — локальная рабочая директория для cursor-sdk bridge (`WORKSPACE_PATH`).

```
┌─────────────┐     long polling      ┌──────────────────┐
│  Telegram   │ ◄──────────────────► │   beachops  │
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
| Entry | `src/beachops/__main__.py`, `app.py` | запуск polling, регистрация handlers |
| Handlers | `src/beachops/bot/handlers/` | команды Telegram, текст, голос, фото, callbacks |
| Services | `src/beachops/services/` | policy, durable dispatch, агент, память, стрим UI |
| API/worker | `src/beachops/web/`, `worker.py` | Mini App API и ARQ execution |
| Frontend | `webapp/` | React/Vite Mini App (голос, очередь, агенты, approvals) |
| Domain | `src/beachops/domain/` | модели, шаблоны промптов |
| DB | `src/beachops/db/` | asyncpg pool, repositories |
| Config | `src/beachops/config/settings.py` | pydantic-settings из `.env` |

### AppContext

Единый контекст (`app_context.py`), создаётся в `post_init`:

- `pool` — asyncpg
- `users`, `repos`, `agent_slots`, `jobs`, `approvals`, `audit`, `system_state`, `passkeys`
- `run_events`, `notification_outbox`, `worker_nodes` — orchestration / legacy Windows registry
- `redis`, `arq`, `hot_cache`, AES-GCM crypto, repository/risk policy
- `memory` — индексация и recall
- `cursor` — CursorAgentService
- `transcription` — OpenAI STT
- `job_queue` — legacy media path; text/voice jobs идут через ARQ
- `active_runs`, `last_prompts` — in-memory состояние

## Аутентификация Mini App / сайта

- Единый IdP: Telegram user id + RBAC allowlist (`OWNER` / `OPERATOR` / `VIEWER`).
- Mini App: HMAC-подпись и возраст `initData` (`Authorization: tma …`); после успеха
  клиент может запросить `POST /api/auth/session` → та же browser cookie.
- Браузер с любого устройства: Telegram Login Widget → `POST /api/auth/telegram/login`
  (подпись Login Widget: `HMAC-SHA256(data, SHA256(bot_token))`) → Redis session.
  Публичный `GET /api/auth/telegram/config` отдаёт `botUsername` / `botId` / `origin`.
- Домен сайта должен быть задан в BotFather (`/setdomain` = host из `WEBAPP_BASE_URL`).
- Session cookie: opaque Redis token, `Secure` / `HttpOnly` / `SameSite=Strict`
  (`__Host-beachops_session`). Unsafe HTTP methods и WebSocket дополнительно
  проверяют `Origin`.
- GitHub OAuth (опционально): `GET /api/auth/github/start` → callback → encrypted
  token в `user_github_tokens` → `GET /api/github/repos` → pin через `POST /api/repos`.
- Passkey/WebAuthn endpoints оставлены как legacy; в UI не используются.

## Поток обработки промпта

```
text/voice → policy + encrypted beachops_jobs → ARQ worker → Cursor Cloud
photo      → validate_prompt_request (legacy media path)
forward          → ForwardContextBuffer (ждёт триггер или timeout)
                 → job_queue.submit
                 → _run_job
                      → memory.recall (ask/plan)
                      → build_prompt + cursor.run_prompt
                      → TelegramStreamRenderer (edit одного сообщения)
                      → memory.index_run
```

Все jobs идут в **cloud** (`services/runtime_router` игнорирует legacy `runtime=windows`).
Cloud agent id: префикс `bc-` (`domain/runtime.is_cloud_agent_id`).

### Режимы (UserMode)

| Режим | Cursor mode | Git / PR | Память в промпт | Кто может |
|-------|-------------|----------|-----------------|-----------|
| **ask** | `agent` | externally read-only | да | viewer+ |
| **plan** | `plan` | без записи | да | operator+ |
| **do** | `agent` | работа на базовой ветке (`work_on_current_branch`); для `main`/`master` — isolated branch + PR | нет | operator+ |

**Write + git:** на обычной базе (`dev` и т.п.) — `work_on_current_branch=true`,
`auto_create_pr=false`. На `main`/`master` — изолированная ветка + PR.
Merge/deploy/force/delete/prod access блокируются policy и prompt.

**Репозитории:** пустой `REPOSITORY_POLICY_JSON` = открытый режим (любой HTTPS
GitHub URL). Непустой allowlist по-прежнему ограничивает URL/ветки. Запись в
`main`/`master` запрещена всегда. Добавление репо — `/repo add` или Mini App
`POST /api/repos` (ветка редактируется через `PATCH /api/repos/{id}`).

**Cloud-чаты:** dashboard отдаёт `cursorUrl` (`https://cursor.com/agents/{bc-…}`)
для слотов и jobs — открытие чата на компьютере.

**Mini App:** вкладки **Работа** / **Голос** / **Лента** / **Апрувы** / **Репо**.
`POST /api/prompts` (ask/plan/do, опционально `images[]` base64), `GET /api/jobs/{id}/stream`
(транскрипт `beachops_run_events`). CRUD слотов: `POST /api/agents`, `PATCH /api/agents/{id}`,
`DELETE /api/agents/{id}`. Cloud worker пишет throttled `run.progress`; голос шлёт
`job.progress` captions и (если `VOICE_MILESTONE_TTS=true`) редкие mid-run TTS-вехи,
затем финальный разговорный брифинг (`kind=final`).

**Voice channel** (`channel=voice` в `build_prompt`): отдельные префиксы
`VOICE_ASK_PREFIX` / `VOICE_PLAN_PREFIX` / `VOICE_DO_GUIDANCE` — короче и без технарщины,
чем Telegram-текст. TOV: `domain/voice_persona.py`.

**Situation brief** (`services/situation_brief.py`): перед Cursor-run в промпт
добавляется снимок очереди, approve, слота/репо/модели — для агента, не для TTS.
По умолчанию `AUTO_APPROVE_PLANS=false`: после plan — `awaiting_approval` и owner-кнопки;
`AUTO_APPROVE_PLANS=true` сразу enqueue DO.

**HTTP MCP `beachops-ops`:** при `MCP_ENABLED` + `MCP_PUBLIC_URL` + `MCP_BEARER_TOKEN`
`CursorAgentService` передаёт cloud-агенту `HttpMcpServerConfig` с tools
`ssh_exec`, `docker_ps`, `docker_logs` (`web/mcp_server.py` → `OpsSshService`).
Промпты ask/plan/do напоминают использовать MCP для логов/SSH, не выдумывать вывод.

**Project skills** (`.cursor/skills/`, индекс `project-skills`): `add-bot-feature`, `telegram-ui`, `db-migrations`, `bot-testing`, `agent-run-pipeline`, `github-branches`, `deploy-prod`. В plan/do промптах агенту сказано читать нужный skill перед нетривиальной работой.

У каждого режима свой системный префикс в `domain/prompts.py`:

- **ask** (`ASK_SYSTEM_PREFIX`) — только текст в Telegram, без правок кода; смотри репо, не гадай; глубина = сложности вопроса; A/B/C только когда без выбора нельзя спланировать разработку.
- **plan** (`PLAN_SYSTEM_PREFIX`) — исследовать код, переиспользовать существующее, опираться на skills; объём плана = задаче; до 3 A/B/C при критичных развилках; план под Telegram (без mermaid/таблиц), напоминание про миграции.
- **do** (`DO_GUIDANCE` + git safety) — сразу правки в базовой ветке; без лишних уточнений; без merge/deploy в main.

### CursorAgentService

1. `AsyncClient.launch_bridge(workspace=WORKSPACE_PATH)`
2. `agents.create` или `agents.resume(cursor_agent_id)`
3. `agent.send(prompt, SendOptions(mode=...))`
4. Стрим `run.messages()` → `StreamState` (assistant, thinking, tool_call, status)
5. `run.wait()` → финальный текст, PR URL, duration

Финальный результат длиннее ~3000 символов дополнительно отправляется полным
`.md`-файлом: Telegram-сообщение с шапкой и футером ограничено 4096 символами.

### Токены Cursor (mt / mt2)

- Два API key: `CURSOR_API_KEY` (`mt`) и опциональный `CURSOR_API_KEY_MT2` (`mt2`); ключ передаётся per-run в `run_prompt(api_key=...)` / `cancel_run(api_key=...)`.
- Выбор пользователя — `users.cursor_token_key` (кнопки 🔑 mt / 🔑 mt2 в клавиатурах, только если mt2 настроен).
- При первом run токен **фиксируется на слоте** (`user_agent_slots.cursor_token_key`): агента, созданного под одним ключом, нельзя резюмить другим. Переключение действует для новых агентов (`/new`).
- Резолв: `run_executor.resolve_run_token_key` — токен слота (если агент уже создан), иначе выбор пользователя; ключи — `domain/cursor_tokens.py`.

### Plan-режим: перехват плана

Cursor в `mode="plan"` возвращает в `result.result` только короткую вводную фразу, а сам план:

- передаёт tool-вызовом **`create_plan`** (полный markdown в `args["plan"]`) — перехватывается в `_consume_message` → `StreamState.set_plan`;
- сохраняет артефактом `artifacts/plans/*.plan.md` (с YAML frontmatter) — fallback через `agent.list_artifacts()` / `download_artifact()`, только если `create_plan` был вызван в этом run (защита от чужого плана при resume).

`_finalize_plan` подставляет plan artifact в `final_text`. Worker создаёт
`PLAN_EXECUTION` approval и отдельные одноразовые owner callback tokens. Статическая
кнопка `CB_BUILD_PLAN` считается legacy и execution не запускает.

### Durable jobs

`beachops_jobs` хранит encrypted payload и state machine; ARQ получает только UUID.
Redis lock гарантирует один run на actor. После plan при `AUTO_APPROVE_PLANS=true`
— сразу do-follow-up; иначе `awaiting_approval` и owner-кнопки (дефолт).
Прямой `/do` и ask завершаются как `succeeded` без лишнего Telegram-approval;
review — через PR в GitHub. Worker восстанавливает stale planning/running jobs
после рестарта.

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
- Текст и фото склеиваются через `PromptCoalesceBuffer` (`PROMPT_COALESCE_SEC`, по умолчанию 5 с) — один run после тишины
- До `PHOTO_MAX_COUNT` изображений → `SDKImage` в Cursor
- Без caption/текста — дефолтный промпт «Разбери скриншот…»

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
- Слот может хранить legacy `runtime`/`local_path` в БД; продуктовая поверхность — только cloud

### Windows worker API (legacy)

Endpoints `/api/workers/*` и пакет `beachops.windows_worker` остаются в коде для
совместимости, но **сняты с продукта**: `runtime_router` всегда выбирает cloud.
Новые интеграции не используют Windows worker.
## Схема БД

| Таблица | Ключевые поля |
|---------|---------------|
| `users` | `tg_user_id`, `current_mode`, `is_admin`, `cursor_model_key`, `cursor_token_key` |
| `user_repos` | `alias`, `github_url`, `default_branch`, `is_active` |
| `user_github_tokens` | encrypted OAuth token per `tg_user_id` (GitHub connect) |
| `user_agent_slots` | `label`, `cursor_agent_id`, `repo_id`, `active_run_id`, `is_active`, `cursor_token_key`, `runtime`, `local_path` |
| `memory_entries` | `kind`, `title`, `body`, `embedding vector(1536)`, метаданные run |
| `beachops_jobs`, `beachops_job_events`, `beachops_artifacts` | durable state machine (`runtime`, `worker_node_id`) |
| `beachops_run_events`, `beachops_notification_outbox` | stream milestones + idempotent Telegram notifier |
| `beachops_worker_nodes` | Windows worker registry / heartbeat |
| `approvals`, `callback_tokens` | owner decisions, digest+TTL+single-use |
| `audit_events`, `system_state` | append-only audit и control-plane flags |

Миграции: Alembic в `alembic/versions/` (в т.ч. `013_orchestration_events`). DDL **не** применяется кодом бота при локальном запуске; в Docker entrypoint выполняет `alembic upgrade head`.

### Event-driven delivery

```
Bot → beachops_jobs → ARQ runner → Cursor Cloud
                  ↘ run_events + notification_outbox → notifier → Telegram
                  ↘ reconciler (cron) → get_run → finalize orphaned UI
```

Telegram stream edits — best-effort UI. Источник правды: Postgres. Cancel — Redis `CancelStore` (bot↔worker).
Hot cache (`HotCache`): dashboard TTL ~3 с, auth bootstrap ~15 мин, embeddings по hash текста.

## Безопасность

- Explicit RBAC: viewer/operator/owner; private-chat-only.
- Repository policy: пустой JSON = open mode; непустой = allowlist URL/веток;
  запись в `main`/`master` блокируется всегда.
- Payload AES-256-GCM; output redaction перед Telegram/DB/API/TTS.
- Callback digest+TTL+atomic consume, Redis idempotency/rate limit.
- Owner `/cancel` и `/rollback` для остановки работы и отката прода.

## Зависимости (ключевые)

- `python-telegram-bot` 22.x, `cursor-sdk` ≥ 0.1.9
- `asyncpg`, `pgvector`, `redis`, `arq`
- `fastapi`, `uvicorn`, React/Vite
- `openai`, `cryptography`, `telegramify-markdown`
- `alembic`, `pydantic-settings`
