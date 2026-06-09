# Эксплуатация

## Docker Compose (локально / сервер)

Стек: **postgres** (pgvector/pg16) + **bot** (long polling).

```powershell
docker compose up -d --build
docker compose ps
docker compose logs -f --tail=100 bot
```

Volumes:

| Volume | Назначение |
|--------|------------|
| `postgres-data` | данные PostgreSQL |
| `bot-data` | workspace cursor-sdk (`/data/workspace`) |

### Миграции

**В Docker:** `entrypoint.sh` выполняет `alembic upgrade head` перед стартом бота.

**Локально без Docker:** миграции вручную (см. [DEVELOPMENT.md](./DEVELOPMENT.md)).

### Bind mount workspace (опционально)

```powershell
docker compose -f docker-compose.yml -f docker-compose.bind.yml up -d --build
```

## Прод-сервер (185.244.49.94)

Каталог: `/home/const/tg-cursor-bot`

### Деплой с Windows

```powershell
.\scripts\deploy-to-prod.ps1
```

Скрипт: tar архив (включая `.env`) → pscp → распаковка → **stop/rm старого bot** → build → `up --force-recreate`.

Порядок на сервере:

```bash
docker compose stop -t 15 bot
docker compose rm -f bot
docker compose build bot
docker compose up -d --force-recreate --remove-orphans --no-deps bot
```

Так старый long-polling процесс гарантированно завершается до старта нового (иначе Telegram отдаёт updates двум инстансам → `Conflict`).

SSH/PuTTY детали — `.cursor/rules/servers-access.mdc`.

### После деплоя

Миграции применяются entrypoint при старте контейнера. При необходимости вручную:

```powershell
echo y | plink -ssh -l const -i "C:\Users\vonwa\.ssh\const.ppk" 185.244.49.94 "cd /home/const/tg-cursor-bot && docker compose exec -T bot alembic upgrade head"
```

### Мониторинг

```powershell
echo y | plink -ssh -l const -i "C:\Users\vonwa\.ssh\const.ppk" 185.244.49.94 "cd /home/const/tg-cursor-bot && docker compose ps"
echo y | plink -ssh -l const -i "C:\Users\vonwa\.ssh\const.ppk" 185.244.49.94 "cd /home/const/tg-cursor-bot && docker compose logs -f --tail=100 bot"
```

## Важные ограничения

- **Один инстанс бота** — Telegram long polling не поддерживает несколько процессов с одним токеном.
- **Nginx / webhook не нужны** — используется polling.
- Не лезть в `/var/lib/docker` без sudo; использовать `docker compose`.

## Бэкап PostgreSQL

На сервере:

```bash
cd /home/const/tg-cursor-bot
docker compose exec -T postgres pg_dump -U bot tg_cursor_bot > /tmp/tg_cursor_bot_backup.sql
```

Скачать на Windows:

```powershell
pscp -i "C:\Users\vonwa\.ssh\const.ppk" const@185.244.49.94:/tmp/tg_cursor_bot_backup.sql "C:\Users\vonwa\tg_cursor_bot_backup.sql"
```

Локально:

```powershell
docker compose exec -T postgres pg_dump -U bot tg_cursor_bot -f backup.sql
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
| plan/do недоступны | пользователь в `ADMIN_USER_IDS` |
| Бот не стартует | `docker compose logs bot` — Postgres, `vector` extension |
| Conflict: terminated by other getUpdates | второй инстанс с тем же токеном |
| Cursor error | `CURSOR_API_KEY`, GitHub подключён в dashboard |
| Память не работает | `OPENAI_API_KEY`, миграции применены |
