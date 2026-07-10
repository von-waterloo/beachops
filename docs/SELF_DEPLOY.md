# Self-hosted CI/CD (BeachOps) — maintainer reference

Документ описывает **прод автора** (`von-waterloo/beachops`, runner `host-185`).
Для своей копии достаточно Docker Compose из [OPERATIONS.md](./OPERATIONS.md) /
корневого README; этот файл не обязателен.

Кратко: приватный репозиторий → CI на GitHub-hosted → **auto-deploy на `main`**
после зелёного CI на self-hosted runner **host-185**. Бот не хранит SSH-ключ
и не ходит на сервер напрямую; rollback/ручной деплой — через тот же Actions
`workflow_dispatch`.

## Репозиторий

- Целевой private repo: `von-waterloo/beachops` (`GITHUB_REPO`).
- Ветки: рабочая и прод-линия **`main`** (push → CI → deploy). `dev` — опциональная
  интеграционная ветка без auto-deploy.
- Секреты Actions (на стороне GitHub, не в контейнере бота):
  - `ENV_PROD_BEACHOPS` (предпочтительно) или `ENV_PROD` — полное содержимое прод-`.env`.

## Runner

- Labels: `[self-hosted, host-185]` (тот же хост, что прод `185.244.49.94`).
- Service: `actions.runner.von-waterloo-beachops.host-185.service` (user `const`).
- Workflow: [`.github/workflows/deploy-prod.yml`](../.github/workflows/deploy-prod.yml).
- На runner: checkout SHA → rsync в `/home/const/tg-cursor-bot` → `.env` из secret →
  pre-deploy `pg_dump` → stop `bot` → `docker compose up --build -d` →
  health `http://127.0.0.1:8080/health`.

## Поток деплоя

| Событие | Что происходит |
|---------|----------------|
| Push / merge в **`main`** | CI → при success **Deploy prod** на host-185 |
| Push в `dev` | только CI (без деплоя) |
| Telegram `/rollback` или API | бот → `workflow_dispatch` с SHA → тот же Deploy prod |
| Actions UI → Run workflow | ручной `workflow_dispatch` с SHA |

## CI gate

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) на `pull_request` и
`push` в `main`/`dev`:

1. Python 3.12: `pip install -e ".[dev]"`, `pytest`
2. webapp: `npm ci`, lint, test, build
3. `docker compose config`

Deploy слушает `workflow_run` workflow **CI** на ветке `main` и стартует только
при `conclusion=success` и `event=push`.

## Бот → workflow_dispatch (rollback / owner approve)

Включение: `GITHUB_DEPLOY_DISPATCH=1` + `GITHUB_TOKEN` + `GITHUB_REPO` в прод-`.env`.
Бот вызывает `trigger_prod_deploy` → Actions на host-185. SSH из контейнера бота нет.

## Secret ENV_PROD_BEACHOPS (Windows)

```bat
cmd /c "gh secret set ENV_PROD_BEACHOPS --repo von-waterloo/beachops < .env"
```

Legacy: `scripts/deploy-to-prod.ps1` — см. [OPERATIONS.md](./OPERATIONS.md).
