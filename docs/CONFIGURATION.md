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
| `OWNER_USER_IDS` | Telegram ID владельцев; rollback / legacy approve |
| `POSTGRES_PASSWORD` | пароль Postgres для docker compose |
| `DATA_ENCRYPTION_KEY` | 32 байта base64url/hex для AES-256-GCM payload |
| `REPOSITORY_POLICY_JSON` | пустой `{"repositories":[]}` = открытый режим (любой HTTPS GitHub URL); непустой список — строгий allowlist URL/веток. Запись в `main`/`master` запрещена всегда |

Локально удобно также задать `DATABASE_URL` / `REDIS_URL` (в example уже есть).
В Docker compose `DATABASE_URL` и `REDIS_URL` переопределяются сам.

## Доступ и роли

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `VIEWER_USER_IDS` | — | только read-only `/ask` |
| `OPERATOR_USER_IDS` | — | read/plan/do |
| `OWNER_USER_IDS` | — | все решения, `/rollback`; approve планов (дефолт) |
| `WHITELIST_USER_IDS`, `ADMIN_USER_IDS` | — | legacy fallback: viewer / owner |
| `AUTO_APPROVE_PLANS` | `false` | `true` — после `/plan` сразу enqueue DO, без кнопок владельцу |
| `VOICE_REQUIRE_CONFIRM` | `false` | `true` — подтверждать расшифровку голоса перед отправкой |

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
| `CURSOR_MODEL` | `composer-2.5` | UI-preset / fallback; динамический каталог — `GET /v1/models` (кэш Redis) |
| `CURSOR_API_BASE_URL` | `https://api.cursor.com` | база Cloud Agents API v1 |
| `CURSOR_API_KEY_MT2` | — (пусто) | второй Cursor API key — кнопка **🔑 mt2**; пусто = кнопка скрыта |
| `CURSOR_API_KEY_MT3` | — (пусто) | третий Cursor API key — кнопка **🔑 mt3**; ряд токенов виден, если задан MT2 и/или MT3 |
| `PHOTO_MAX_COUNT` | `5` | макс. изображений на prompt (жёсткий потолок API v1 = 5) |
| `WORKSPACE_PATH` | `./data/workspace` | workspace для cursor-sdk bridge; в Docker: `/data/workspace` |
| `DEFAULT_BRANCH` | `dev` | стартовая ветка; обязана входить в policy |
| `DEFAULT_REPO_URL` | — (пусто) | seed только если точная пара URL/branch разрешена policy |
| `DEFAULT_RUNTIME` | `cloud` | legacy; продукт всегда cloud (`runtime_router`) |
| `GITHUB_TOKEN` | — | PR metadata + (опционально) Actions `workflow_dispatch` для deploy |
| `GITHUB_REPO` | — (пусто) | `owner/name` вашего форка; нужен только при `GITHUB_DEPLOY_DISPATCH=1` |
| `GITHUB_OAUTH_CLIENT_ID` | — | OAuth App Client ID: вход GitHub → список репо → закрепить в Mini App |
| `GITHUB_OAUTH_CLIENT_SECRET` | — | OAuth App Client Secret; callback = `{WEBAPP_BASE_URL}/api/auth/github/callback` |
| `GITHUB_DEPLOY_DISPATCH` | `false` | `1`/`true` — разрешить owner-approve → `deploy-prod.yml` |
| `GITHUB_DEPLOY_WORKFLOW` | `deploy-prod.yml` | имя workflow файла для dispatch |
| `GITHUB_DEPLOY_REF` | `main` | git ref для `workflow_dispatch` (ветка/тег; SHA — в input) |
| `SELF_IMPROVE_ENABLED` | `false` | стартовый дефолт до первого переключения в Mini App (вкладка **Апрувы**); пока выкл — обычные репо без требований к allowlist |
| `SELF_IMPROVE_REPO_URL` | — | HTTPS URL форка BeachOps; при наличии добавляется в policy (open mode сохраняется); цель для тоггла |
| `SELF_IMPROVE_BRANCHES` | `dev` | ветки allowlist (`main`/`master` protected) |

Включение/выключение в рантайме — вкладка **Апрувы** в Mini App (owner). Env задаёт цель и seed.
пока вы сами не включите. После деплоя плохой SHA owner откатывает командой `/rollback`
(нужны `GITHUB_DEPLOY_DISPATCH=1`, `GITHUB_TOKEN`, `GITHUB_REPO`).

## OpenAI

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `TRANSCRIBE_MODEL` | `gpt-4o-mini-transcribe-2025-12-15` | STT для голосовых Telegram |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | векторы памяти (1536 dim) |
| `VOICE_REALTIME_MODEL` | `gpt-realtime` | WebSocket connect Realtime API (`session.type=realtime`) |
| `VOICE_INPUT_TRANSCRIBE_MODEL` | `gpt-4o-transcribe` | nested `audio.input.transcription.model` |
| `VOICE_INPUT_TRANSCRIBE_PROMPT` | словарь BeachOps (в коде) | bias STT; пусто = встроенный keyword list |
| `VOICE_TTS_MODEL` | `gpt-4o-mini-tts-2025-12-15` | голосовой ответ (steerable TTS) |
| `VOICE_TTS_VOICE` | `cedar` | голос; `cedar`/`marin` — лучшее качество OpenAI |
| `VOICE_TTS_INSTRUCTIONS` | laconic (в коде) | стиль подачи; пусто = встроенный TOV |
| `VOICE_SPOKEN_MAX_CHARS` | `900` | лимит символов после сжатия ответа в брифинг |
| `VOICE_MAX_SESSION_SEC` | `300` | max voice session |
| `VOICE_MILESTONE_TTS` | `false` | устные вехи mid-run в Mini App; `true` — редкие фразы (ack, awaiting_approval) |
| `VOICE_MILESTONE_MIN_INTERVAL_SEC` | `15` | мин. пауза между mid-run TTS |
| `VOICE_MILESTONE_MAX_PER_JOB` | `4` | max mid-run фраз на задачу (ack не считается) |

## Память

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `MEMORY_RECALL_K` | `3` | сколько chunks подмешивать в ask/plan |
| `MEMORY_LIST_LIMIT` | `10` | лимит `/memory` без query |
| `MEMORY_EMBED_MAX_CHARS` | `8000` | обрезка текста перед embedding |

## HTTP MCP (ops on owner hosts)

Full guide: [OPS_MCP.md](./OPS_MCP.md) (English).

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_ENABLED` | `false` | Enable `/mcp` and inject `beachops-ops` into cloud agents |
| `MCP_PUBLIC_URL` | — | Public HTTPS MCP URL (usually `{WEBAPP_BASE_URL}/mcp`) |
| `MCP_BEARER_TOKEN` | — | Bearer for MCP auth and `HttpMcpServerConfig` |
| `OPS_SSH_HOSTS` | — | Allowlist `alias=user@host:port` (+ optional `/via=other`). Example: `eu=…,mt-dev=…,ru=…/via=eu` |
| `OPS_SSH_KEY_PATH` | — | Private key path **inside the api container** (overlay mounts to `/run/beachops-ssh/id_ed25519`) |
| `OPS_SSH_KEY_HOST_PATH` | — | Absolute key path **on the Docker host**; required to use `docker-compose.ops.yml` |
| `OPS_SSH_TIMEOUT_SEC` | `30` | SSH command timeout (5–120) |
| `OPS_SSH_MAX_OUTPUT_CHARS` | `12000` | Truncate tool stdout/stderr |

Tools: `ssh_exec`, `docker_ps`, `docker_logs`. Suggested aliases: `eu` (BeachOps), `mt-dev` (app DEV), `ru` (app PROD). MCP is independent of Cursor key presets (`mt` / `mt2` / `mt3`).

## Control plane и Mini App

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `WEBAPP_BASE_URL` | — | публичный HTTPS URL Telegram Mini App (прод: `https://beachops.marketolog.tech`; TLS на host nginx → `:8080`); домен также нужен в BotFather `/setdomain` для Login Widget |
| `TG_BOT_USERNAME` | — (auto via getMe) | username бота без `@` для Login Widget; если пусто — берётся из Telegram `getMe` и кэшируется |
| `WEB_AUTH_MAX_AGE_SEC` | `3600` | срок валидности Telegram initData и Login Widget payload |
| `WEB_SESSION_TTL_SEC` | `43200` | TTL opaque browser-сессии после Telegram Login / Mini App |
| `WEB_AUTH_CHALLENGE_TTL_SEC` | `300` | TTL одноразового WebAuthn challenge (legacy Passkey) |
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
| `PHOTO_MAX_COUNT` | `5` | max изображений в одном промпте (1–5; жёсткий потолок Cloud Agents API v1) |
| `MEDIA_GROUP_DELAY_SEC` | `6.0` | задержка сборки альбома (фото и пересылки) |
| `SHUTDOWN_DRAIN_SEC` | `15.0` | ожидание активных run при остановке бота |
| `PROMPT_COALESCE_SEC` | `5` | debounce текста и фото в один промпт (0–30): ждёт тишины после последнего апдейта, чтобы подпись и картинки не уезжали разными run |

## Пересланный контекст

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `FORWARD_CONTEXT_TIMEOUT_SEC` | `25` | автоотправка буфера пересылок без вашего вопроса |
| `FORWARD_CONTEXT_MAX_ITEMS` | `25` | max блоков пересылок в одной пачке (альбом = 1 блок) |
| `AGENT_SLOTS_MAX` | `8` | макс. слотов Cursor-агентов на пользователя (5–10) |

## Windows worker (снят с продукта)

Legacy outbound worker на Windows-ПК (`beachops.windows_worker`, `/api/workers/*`)
больше не входит в продуктовую поверхность: все runs идут в Cursor Cloud.
Переменные и скрипты (`install-windows-worker.ps1`, `.env.windows-worker`) остаются
для совместимости; новые деплои не настраивают.

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `DEFAULT_RUNTIME` | `cloud` | игнорируется роутером; всегда cloud |
| `WORKER_BOOTSTRAP_TOKEN` | пусто | legacy bootstrap для `/api/workers/register` |

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
- Owner: approvals, rollback

Per-chat scope для admin IDs через `BotCommandScopeChat`.
