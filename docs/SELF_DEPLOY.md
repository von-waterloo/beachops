# Self-hosted CI/CD (BeachOps) — maintainer reference

Документ описывает **прод автора** (`von-waterloo/beachops`, runner `host-185`).
Для своей копии достаточно Docker Compose из [OPERATIONS.md](./OPERATIONS.md) /
корневого README; этот файл не обязателен. Обзор «свой деплой vs CI автора» —
в [KNOWLEDGE_BASE.md](./KNOWLEDGE_BASE.md#свой-деплой).

Кратко: приватный репозиторий → CI на GitHub-hosted → **auto-deploy с `main` или `dev`**
после зелёного CI на self-hosted runner **host-185**. Бот не хранит SSH-ключ
и не ходит на сервер напрямую; rollback/ручной деплой — через тот же Actions
`workflow_dispatch`.

## Поток деплоя

| Событие | Что происходит |
|---------|----------------|
| Push / merge в **`main`** или **`dev`** | Deploy prod ждёт зелёный CI, затем выкат на host-185 |
| Telegram `/rollback` или API | бот → `workflow_dispatch` с SHA → тот же Deploy prod |
| Actions UI → Run workflow | ручной `workflow_dispatch` с SHA |

Self-improve / `/do` на базе `dev`: агент пушит в `dev` → CI → тот же прод.
Прямой push агента в `main`/`master` по-прежнему запрещён policy.

Короткий SHA в dispatch раскрывается в полный (иначе `actions/checkout` ищет ветку).

## Репозиторий

- Целевой private repo: `von-waterloo/beachops` (`GITHUB_REPO`).
- Ветки: рабочая `dev`, прод-линия `main` (обе дают auto-deploy).
- Секреты Actions (на стороне GitHub, не в контейнере бота):
  - `ENV_PROD_BEACHOPS` (предпочтительно) или `ENV_PROD` — полное содержимое прод-`.env`.

## Runner

- Labels: `[self-hosted, host-185]` (тот же хост, что прод `185.244.49.94`).
- Workflow: [`.github/workflows/deploy-prod.yml`](../.github/workflows/deploy-prod.yml).
- На runner: checkout SHA → rsync в `/home/const/tg-cursor-bot` → `.env` из secret →
  `docker compose -p tg-cursor-bot up --build -d --remove-orphans` →
  health `http://127.0.0.1:8080/health`.

Ручной запуск: **Actions → Deploy prod → Run workflow** с input `sha`.

## CI gate

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) на `pull_request` и
`push` в `main`/`dev`:

1. Python 3.12: `pip install -e ".[dev]"`, `pytest`
2. webapp: `npm ci`, lint, test, build
3. `docker compose config` (с dummy env для required vars)

После зелёного CI Deploy prod выкатывает тот же SHA на host-185.

## Бот → workflow_dispatch (rollback / owner approve)

Включение: `GITHUB_DEPLOY_DISPATCH=1` + `GITHUB_TOKEN` + `GITHUB_REPO` в прод-`.env`.
Бот вызывает `trigger_prod_deploy` → Actions на host-185. SSH из контейнера бота нет.

## Secret ENV_PROD_BEACHOPS (Windows)

Не передавайте тело секрета через PowerShell-строку — кавычки в
`REPOSITORY_POLICY_JSON` могут пропасть. Заливайте файл через `cmd`:

```bat
cmd /c "gh secret set ENV_PROD_BEACHOPS --repo von-waterloo/beachops < .env"
```

(файл `.env` — актуальная копия с прод-сервера).

## Чего нет в контейнере бота

- Нет PuTTY/SSH ключей и `plink`/`pscp`.
- Нет записи в `/home/const/...` с бота.
- Нет автоматического push агента в `main`/`master` (policy).

Legacy ручной деплой с Windows (`scripts/deploy-to-prod.ps1`) остаётся запасным
каналом — см. [OPERATIONS.md](./OPERATIONS.md).

## Опционально

- [`.github/workflows/docker-publish.yml`](../.github/workflows/docker-publish.yml) —
  stub на теги `v*`; прод сейчас собирает образы на runner через compose.
