# Эксплуатация

Секция **Docker Compose** ниже универсальна для любого хоста: свой `.env`, свои
ключи, свой сервер. Раздел **Прод-сервер (185.244.49.94)** и self-hosted runner
`host-185` — это конкретный прод поддерживающего автора, не обязательный шаг
для вашей копии BeachOps.

## Docker Compose (локально / сервер)

Стек: **postgres** + **redis** + one-shot **migrate** + один long-polling
**bot** + **worker** (ARQ/Cursor) + **api** (FastAPI) + **webapp** (nginx/React).

```powershell
docker compose up -d --build
docker compose ps
docker compose logs -f --tail=100 bot
docker compose logs -f --tail=100 worker api
```

Volumes:

| Volume | Назначение |
|--------|------------|
| `postgres-data` | данные PostgreSQL |
| `redis-data` | ARQ queue, idempotency, rate limits, hot cache |
| `bot-data` | workspace cursor-sdk (`/data/workspace`) |

### Миграции

**В Docker:** сервис `migrate` выполняет `alembic upgrade head`; bot/API/worker
ждут его успешного завершения.

**Локально без Docker:** миграции вручную (см. [DEVELOPMENT.md](./DEVELOPMENT.md)).

### Windows worker (локальные Cursor-агенты)

На Windows 11 ПК с **Docker Desktop** (рекомендуется):

1. `.env.windows-worker` из `.env.windows-worker.example` (`BEACHOPS_API_URL`,
   `BEACHOPS_WORKER_TOKEN` = прод `WORKER_BOOTSTRAP_TOKEN`, `CURSOR_API_KEY`).
2. `.\scripts\install-windows-worker.ps1` — контейнер
   `docker-compose.windows-worker.yml`, `restart: unless-stopped`.
3. Docker Desktop → Settings → General → **Start Docker Desktop when you sign in**
   (тогда worker поднимается вместе с ПК).

Логи: `docker compose -p beachops-windows-worker -f docker-compose.windows-worker.yml logs -f`.

Legacy без Docker: `.\scripts\install-windows-worker.ps1 -Native` (Scheduled Task, нужны права).

Jobs со `runtime=windows` не уходят в ARQ — их claim'ит Windows daemon.

### Bind mount workspace (опционально)

```powershell
docker compose -f docker-compose.yml -f docker-compose.bind.yml up -d --build
```

## Прод-сервер (185.244.49.94)

Каталог остаётся `/home/const/tg-cursor-bot` для совместимости существующих
named volumes. Приложение и Python package полностью называются BeachOps.

### CI / self-hosted deploy (предпочтительно)

См. [SELF_DEPLOY.md](./SELF_DEPLOY.md): CI на PR/`main`/`dev`, прод — только
`workflow_dispatch` на runner `[self-hosted, host-185]` (secret
`ENV_PROD_BEACHOPS` или `ENV_PROD`). Бот не использует SSH.

### Деплой с Windows (legacy)

```powershell
.\scripts\deploy-to-prod.ps1
```

Скрипт не передаёт `.env`: использует серверный файл, создаёт backup PostgreSQL,
добавляет отсутствующий encryption key/policy compatibility, останавливает старый
poller, собирает весь стек и запускает миграции.

Порядок на сервере:

```bash
docker compose -p tg-cursor-bot build
docker compose -p tg-cursor-bot up -d --force-recreate --remove-orphans
```

Так старый long-polling процесс гарантированно завершается до старта нового (иначе Telegram отдаёт updates двум инстансам → `Conflict`).

SSH/PuTTY детали — `.cursor/rules/servers-access.mdc`.

### После деплоя

Миграции применяет `migrate`. Проверка:

```powershell
echo y | plink -ssh -l const -i "C:\Users\vonwa\.ssh\const.ppk" 185.244.49.94 "cd /home/const/tg-cursor-bot && docker compose -p tg-cursor-bot logs migrate"
```

### Мониторинг

```powershell
echo y | plink -ssh -l const -i "C:\Users\vonwa\.ssh\const.ppk" 185.244.49.94 "cd /home/const/tg-cursor-bot && docker compose -p tg-cursor-bot ps"
echo y | plink -ssh -l const -i "C:\Users\vonwa\.ssh\const.ppk" 185.244.49.94 "cd /home/const/tg-cursor-bot && docker compose -p tg-cursor-bot logs --tail=100 bot worker api"
```

## Важные ограничения

- **Один инстанс бота** — Telegram long polling не поддерживает несколько процессов с одним токеном.
- Bot остаётся на polling. Mini App требует публичный HTTPS URL в `WEBAPP_BASE_URL`.
- Self-improve (`SELF_IMPROVE_*`) по умолчанию выключен. Включение только в вашем `.env`
  добавляет ваш форк BeachOps в allowlist; откат прода — `/rollback` (нужен
  `GITHUB_DEPLOY_DISPATCH`).
- На проде: docker `webapp` слушает host port `8080`; host nginx + Let's Encrypt
  проксируют `https://beachops.marketolog.tech` → `127.0.0.1:8080`
  (конфиг `/etc/nginx/sites-available/beachops-marketolog.conf`, шаблон в
  `scripts/prod-beachops-marketolog.nginx.conf`).
- Не лезть в `/var/lib/docker` без sudo; использовать `docker compose`.

## Бэкап PostgreSQL

На сервере:

```bash
cd /home/const/tg-cursor-bot
docker compose -p tg-cursor-bot exec -T postgres pg_dump -U bot tg_cursor_bot > /tmp/beachops_backup.sql
```

Скачать на Windows:

```powershell
pscp -i "C:\Users\vonwa\.ssh\const.ppk" const@185.244.49.94:/tmp/beachops_backup.sql "C:\Users\vonwa\beachops_backup.sql"
```

Локально:

```powershell
docker compose exec -T postgres pg_dump -U bot tg_cursor_bot > backup.sql
```

## Восстановление

```powershell
docker compose exec -T postgres psql -U bot tg_cursor_bot < backup.sql
```

(На Windows для больших дампов — файл через pscp + psql внутри контainers.)

## Обновление зависимостей

1. Изменить `pyproject.toml`
2. `pip install -e .` локально, прогнать тесты
3. `docker compose up -d --build`
4. Обновить [CONFIGURATION.md](./CONFIGURATION.md) если добавлены env

## Troubleshooting

| Симптом | Проверка |
|---------|----------|
| «Доступ запрещён» | `WHITELIST_USER_IDS` содержит Telegram user id |
| plan/do/task недоступны | пользователь в `OPERATOR_USER_IDS` или `OWNER_USER_IDS` |
| Бот не стартует | Postgres/Redis, encryption key, repository policy, миграции |
| Mini App не открывается | нужен `WEBAPP_BASE_URL` с HTTPS, HTTP/IP Telegram не принимает |
| Mini App: шторм `/api/voice/ws` или dashboard 401 | открывать только из Telegram (нужен `initData`); вне TG реконнект не должен крутиться |
| Voice WS рвётся без причины в UI | `docker compose logs api webapp` — искать JSON с `"action":"voice_session"` / `"error_code"` / `exception`; auth fail → 4401, rate limit → 4429 |
| Нет JSON-логов у api/worker | `configure_logging` на старте; `LOG_LEVEL`; ротация `json-file` 50m×5 в compose |
| Conflict: terminated by other getUpdates | второй инстанс с тем же токеном |
| Cursor error | `CURSOR_API_KEY`, GitHub подключён в dashboard |
| Память не работает | `OPENAI_API_KEY`, миграции применены |
