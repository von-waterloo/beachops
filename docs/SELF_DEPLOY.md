# Self-hosted CI/CD (BeachOps) — maintainer reference

Документ описывает **прод автора** (`von-waterloo/beachops`, runner `host-185`).
Для своей копии достаточно Docker Compose из [OPERATIONS.md](./OPERATIONS.md) /
корневого README; этот файл не обязателен.

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

## Бот → workflow_dispatch (rollback / owner approve)

Включение: `GITHUB_DEPLOY_DISPATCH=1` + `GITHUB_TOKEN` + `GITHUB_REPO` в прод-`.env`.
Бот вызывает `trigger_prod_deploy` → Actions на host-185. SSH из контейнера бота нет.

## Secret ENV_PROD_BEACHOPS (Windows)

```bat
cmd /c "gh secret set ENV_PROD_BEACHOPS --repo von-waterloo/beachops < .env"
```

Legacy: `scripts/deploy-to-prod.ps1` — см. [OPERATIONS.md](./OPERATIONS.md).
