# Конфигурация

Все переменные читаются из `.env` (см. `.env.example`). Pydantic-settings, `extra=ignore`.

## Обязательные

| Переменная | Описание |
|------------|----------|
| `TG_BOT_TOKEN` | Токен Telegram Bot от @BotFather |
| `CURSOR_API_KEY` | API key из [Cursor Integrations](https://cursor.com/dashboard/integrations) (токен `mt`) |
| `OPENAI_API_KEY` | Транскрипция голоса + эмбеддинги памяти |
| `OWNER_USER_IDS` | Telegram ID владельцев; approve/panic/unpanic |
| `DATA_ENCRYPTION_KEY` | 32 байта base64url/hex для AES-256-GCM payload |
| `REPOSITORY_POLICY_JSON` | строгий allowlist GitHub URL и веток |
| `POSTGRES_PASSWORD` | обязательный пароль compose без insecure default |

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
| `REDIS_URL` | `redis://localhost:6379/0` | ARQ, rate limit, idempotency |

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
| `GITHUB_REPO` | `stekirill/beachops` | owner/name для GitHub API (deploy trigger) |
| `GITHUB_DEPLOY_DISPATCH` | `false` | `1`/`true` — разрешить owner-approve → `deploy-prod.yml` |
| `GITHUB_DEPLOY_WORKFLOW` | `deploy-prod.yml` | имя workflow файла для dispatch |
| `GITHUB_DEPLOY_REF` | `main` | git ref для `workflow_dispatch` (ветка/тег; SHA — в input) |

## OpenAI

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `TRANSCRIBE_MODEL` | `gpt-4o-mini-transcribe` | STT для голосовых |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | векторы памяти (1536 dim) |
| `VOICE_REALTIME_MODEL` | `gpt-realtime-whisper` | partial/final transcript Mini App |
| `VOICE_TTS_MODEL` | `gpt-4o-mini-tts` | голосовой ответ |
| `VOICE_TTS_VOICE` | `marin` | голос |
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

Установка: `scripts/install-windows-worker.ps1` (Scheduled Task) или `python -m beachops.windows_worker`.

## Прочее

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `LOG_LEVEL` | `INFO` | уровень logging |

## Пример `.env`

```env
TG_BOT_TOKEN=123456:ABC...
CURSOR_API_KEY=key_...
OPENAI_API_KEY=sk-...
VIEWER_USER_IDS=987654321
OPERATOR_USER_IDS=
OWNER_USER_IDS=123456789
DATA_ENCRYPTION_KEY=<64 hex chars>
REPOSITORY_POLICY_JSON={"repositories":[{"url":"https://github.com/acme/app","branches":["dev"]}]}
DATABASE_URL=postgresql://bot:<password>@localhost:5433/tg_cursor_bot
POSTGRES_PASSWORD=<long random password>
REDIS_URL=redis://localhost:6379/0
WORKSPACE_PATH=./data/workspace
DEFAULT_BRANCH=dev
CURSOR_MODEL=composer-2.5
STREAM_THINKING=preview
JOB_QUEUE_DEPTH=2
MEMORY_RECALL_K=3
```

## Telegram Bot Commands (меню)

Регистрируются в `register_bot_commands`:

- Все: start, ask, status, agents, repo, jobs, cancel, dashboard
- Operator: plan/task
- Owner: approvals, panic, unpanic

Per-chat scope для admin IDs через `BotCommandScopeChat`.
