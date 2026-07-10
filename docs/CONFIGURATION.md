# Конфигурация

Минимальный шаблон: [`.env.example`](../.env.example) — только то, без чего
не стартует. Всё остальное уже задано дефолтами в `Settings`
(`src/beachops/config/settings.py`). Ниже — полный справочник на случай тонкой
настройки.

Pydantic-settings, `extra=ignore`: неизвестные ключи в `.env` просто игнорируются.

## Обязательные (есть в `.env.example`)

| Переменная | Описание |
|------------|----------|
| `TG_BOT_TOKEN` | Токен Telegram Bot от @BotFather |
| `CURSOR_API_KEY` | API key из [Cursor Integrations](https://cursor.com/dashboard/integrations) |
| `OPENAI_API_KEY` | Транскрипция голоса + эмбеддинги памяти |
| `OWNER_USER_IDS` | Telegram ID владельцев; approve/panic/unpanic/rollback |
| `POSTGRES_PASSWORD` | пароль Postgres для docker compose |
| `DATA_ENCRYPTION_KEY` | 32 байта base64url/hex для AES-256-GCM payload |
| `REPOSITORY_POLICY_JSON` | пустой `{"repositories":[]}` = открытый режим (любой HTTPS GitHub URL); непустой список — строгий allowlist URL/веток. Запись в `main`/`master` запрещена всегда |

Локально удобно также задать `DATABASE_URL` / `REDIS_URL` (в example уже есть).
В Docker compose `DATABASE_URL` и `REDIS_URL` переопределяются сам.

## Доступ и роли

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `VIEWER_USER_IDS` | — | только read-only `/ask` |
| `OPERATOR_USER_IDS` | — | read/plan/do; approve недоступен |
| `OWNER_USER_IDS` | — | все решения, `/panic`, `/unpanic` |
| `WHITELIST_USER_IDS`, `ADMIN_USER_IDS` | — | legacy fallback: viewer / owner |

Проверки: `Settings.is_whitelisted()`, `Settings.is_admin()`, `Settings.can_use_mode()`.

## База данных

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `DATABASE_URL` | `postgresql://bot:botsecret@localhost:5432/tg_cursor_bot` | asyncpg DSN; имя сохранено для совместимости данных |
| `REDIS_URL` | `redis://localhost:6379/0` | ARQ, rate limit, idempotency, hot cache |

Docker compose переопределяет `DATABASE_URL` на `@postgres:5432`.

## Cursor Agent

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `CURSOR_MODEL` | `composer-2.5` | модель Cloud Agent |
| `CURSOR_API_KEY_MT2` | — (пусто) | второй Cursor API key — переключалка **mt / mt2** в боте; пусто = переключалка скрыта, работает только `CURSOR_API_KEY` |
| `WORKSPACE_PATH` | `./data/workspace` | workspace для cursor-sdk bridge; в Docker: `/data/workspace` |
| `DEFAULT_BRANCH` | `dev` | стартовая ветка; обязана входить в policy |
| `DEFAULT_REPO_URL` | — (пусто) | seed только если точная пара URL/branch разрешена policy |
| `DEFAULT_RUNTIME` | `cloud` | runtime Cursor SDK (`cloud` \| `windows`); прод — cloud |
| `GITHUB_TOKEN` | — | PR metadata + (опционально) Actions `workflow_dispatch` для deploy |
| `GITHUB_REPO` | — (пусто) | `owner/name` вашего форка; нужен только при `GITHUB_DEPLOY_DISPATCH=1` |
| `GITHUB_DEPLOY_DISPATCH` | `false` | `1`/`true` — разрешить owner-approve → `deploy-prod.yml` |
| `GITHUB_DEPLOY_WORKFLOW` | `deploy-prod.yml` | имя workflow файла для dispatch |
| `GITHUB_DEPLOY_REF` | `main` | git ref для `workflow_dispatch` (ветка/тег; SHA — в input) |
| `SELF_IMPROVE_ENABLED` | `false` | opt-in: разрешить боту работать над своим BeachOps-форком |
| `SELF_IMPROVE_REPO_URL` | — | HTTPS URL форка; если пусто — берётся из `GITHUB_REPO` |
| `SELF_IMPROVE_BRANCHES` | `dev` | ветки allowlist для self-improve (`main`/`master` остаются protected) |

`SELF_IMPROVE_*` по умолчанию выключены: чужой деплой и ваш текущий доступ не меняются.
В Mini App (вкладка **Репо**) owner видит карточку и может активировать режим одной кнопкой.
пока вы сами не включите. После деплоя плохой SHA owner откатывает командой `/rollback`
(нужны `GITHUB_DEPLOY_DISPATCH=1`, `GITHUB_TOKEN`, `GITHUB_REPO`).

## SSH-диагностика сервера (опционально, риск!)

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `AGENT_SSH_HOST` | — (пусто) | хост для read-only docker-диагностики |
| `AGENT_SSH_PORT` | `22` | SSH-порт |
| `AGENT_SSH_USER` | — (пусто) | SSH-пользователь (рекомендуется отдельный, без sudo) |
| `AGENT_SSH_PRIVATE_KEY_B64` | — (пусто) | приватный ключ, base64 (без passphrase) |
| `AGENT_SSH_LABEL` | `сервер` | название хоста в инструкции агенту (`prod`, `dev` и т.п.) |
| `AGENT_SSH_REMOTE_DIR` | — (пусто) | cwd на сервере для `docker compose` команд |

Активна только когда **все три** `AGENT_SSH_HOST` / `AGENT_SSH_USER` /
`AGENT_SSH_PRIVATE_KEY_B64` заполнены (`Settings.agent_ssh_configured()`), и только
для operator/owner (`Settings.can_use_server_ssh()`). При выполнении cloud-агент
получает ключ через `CloudAgentOptions.env_vars`, а `domain/prompts.server_ssh_block`
подмешивает в промпт (ask/do) инструкцию: подключиться по SSH и выполнять **только**
read-only `docker ps/logs/inspect/stats`, ничего не менять на сервере, удалить ключ
после работы.

**Это осознанное отклонение от общего принципа проекта** «бот не хранит и не передаёт
SSH-ключи / production credentials» (см. `docs/THREAT_MODEL.md`,
`services/deploy_trigger.py`). Приватный ключ уходит в cloud-песочницу LLM-агента —
заведите **отдельный ограниченный** ключ/пользователя (без sudo, по возможности —
forced command только на `docker ps/logs/inspect` в `authorized_keys`), не переиспользуйте
существующий root/admin-ключ. Не включайте на деплойменте, к которому подключены
третьи лица, если не готовы к этому риску.

## OpenAI

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `TRANSCRIBE_MODEL` | `gpt-4o-mini-transcribe` | STT для голосовых |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | векторы памяти (1536 dim) |
| `VOICE_REALTIME_MODEL` | `gpt-realtime` | модель WebSocket Realtime API (connect) |
| `VOICE_TRANSCRIBE_MODEL` | `gpt-4o-transcribe` | nested transcription model в realtime-сессии Mini App |
| `VOICE_TTS_MODEL` | `gpt-4o-mini-tts` | голосовой ответ (steerable TTS) |
| `VOICE_TTS_VOICE` | `cedar` | голос; `cedar`/`marin` — лучшее качество OpenAI |
| `VOICE_TTS_INSTRUCTIONS` | Spartan (в коде) | стиль подачи; пусто = встроенный спартанский TOV |
| `VOICE_SPOKEN_MAX_CHARS` | `900` | лимит символов после сжатия ответа в брифинг |
| `VOICE_MAX_SESSION_SEC` | `300` | max voice session |

## Память

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `MEMORY_RECALL_K` | `3` | сколько chunks подмешивать в ask/plan |
| `MEMORY_LIST_LIMIT` | `10` | лимит `/memory` без query |
| `MEMORY_EMBED_MAX_CHARS` | `8000` | обрезка текста перед embedding |

## Control plane и Mini App

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `WEBAPP_BASE_URL` | — | публичный HTTPS URL Telegram Mini App (прод: `https://beachops.marketolog.tech`; TLS на host nginx → `:8080`) |
| `WEB_AUTH_MAX_AGE_SEC` | `3600` | срок валидности Telegram initData |
| `WEB_SESSION_TTL_SEC` | `43200` | TTL защищённой browser-сессии после входа по Passkey |
| `WEB_AUTH_CHALLENGE_TTL_SEC` | `300` | TTL одноразового WebAuthn challenge |
| `CALLBACK_TOKEN_TTL_SEC` | `600` | TTL одноразовых owner-кнопок |
| `CALLBACK_RATE_LIMIT` | `30` | callback actions за окно |
| `CALLBACK_RATE_WINDOW_SEC` | `60` | окно rate limit |

Текстовые jobs сохраняются в PostgreSQL в зашифрованном виде и отправляются в Redis/ARQ. `JOB_QUEUE_DEPTH` остаётся только для legacy media-path.

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
| `MEDIA_GROUP_DELAY_SEC` | `6.0` | задержка сборки альбома (фото и пересылки) |
| `SHUTDOWN_DRAIN_SEC` | `15.0` | ожидание активных run при остановке бота |
| `PROMPT_COALESCE_SEC` | `5` | debounce текста и фото в один промпт (0–30): ждёт тишины после последнего апдейта, чтобы подпись и картинки не уезжали разными run |

## Пересланный контекст

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `FORWARD_CONTEXT_TIMEOUT_SEC` | `25` | автоотправка буфера пересылок без вашего вопроса |
| `FORWARD_CONTEXT_MAX_ITEMS` | `25` | max блоков пересылок в одной пачке (альбом = 1 блок) |
| `AGENT_SLOTS_MAX` | `8` | макс. слотов Cursor-агентов на пользователя (5–10) |

## Windows worker (локальный execution plane)

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `DEFAULT_RUNTIME` | `cloud` | runtime по умолчанию: `cloud` \| `windows` |
| `WORKER_BOOTSTRAP_TOKEN` | пусто | bootstrap-токен для `POST /api/workers/register` (альтернатива owner TMA); alias `BEACHOPS_WORKER_BOOTSTRAP_TOKEN` |

На Windows-ПК worker читает:

| Переменная | Описание |
|------------|----------|
| `BEACHOPS_API_URL` | URL BeachOps API (например Mini App HTTPS) |
| `BEACHOPS_WORKER_TOKEN` | токен из ответа `/api/workers/register` |
| `BEACHOPS_WORKER_HOSTNAME` | опционально; иначе имя машины |
| `CURSOR_API_KEY` | ключ Cursor на локальной машине |
| `BEACHOPS_LOCAL_CWD` | cwd для discovery локальных IDE-агентов |

Установка на Windows ПК: `scripts/install-windows-worker.ps1` (Docker Desktop,
`docker-compose.windows-worker.yml`) или `-Native` (Scheduled Task). Env:
`.env.windows-worker` / `.env.windows-worker.example`.

## Прочее

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `LOG_LEVEL` | `INFO` | уровень logging; JSON в stdout (`service`, `correlation_id`, `user_id`, `job_id`, `action`, `duration_ms`, `error_code`) |

## Пример `.env`

См. корневой [`.env.example`](../.env.example) — короткий шаблон.
Не копируйте сюда десятки тюнинг-переменных: дефолты в коде достаточны.

## Telegram Bot Commands (меню)

Регистрируются в `register_bot_commands`:

- Все: start, ask, status, agents, repo, jobs, cancel, dashboard
- Operator: plan/task
- Owner: approvals, panic, unpanic

Per-chat scope для admin IDs через `BotCommandScopeChat`.
