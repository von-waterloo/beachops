# Self-hosted CI/CD (BeachOps) — maintainer reference

Документ описывает **прод автора** (`von-waterloo/beachops`, runner `host-185`).
Для своей копии достаточно Docker Compose из [OPERATIONS.md](./OPERATIONS.md) /
корневого README; этот файл не обязателен.

Кратко: приватный репозиторий → CI на GitHub-hosted → **auto-deploy только с `dev`**
после зелёного CI на self-hosted runner **host-185**. Бот не хранит SSH-ключ
и не ходит на сервер напрямую; rollback/ручной деплой — через тот же Actions
`workflow_dispatch`.

## Поток деплоя

| Событие | Что происходит |
|---------|----------------|
| Push в **`dev`** | Deploy prod ждёт зелёный CI, затем выкат на host-185 |
| Push / merge в **`main`** | Только CI; автоматического выката нет |
| Telegram `/rollback` или API | бот → `workflow_dispatch` с SHA → тот же Deploy prod |
| Actions UI → Run workflow | ручной `workflow_dispatch` с SHA |

Self-improve / `/do` на базе `dev`: агент пушит в `dev` → CI → тот же прод.
Прямой push агента в `main`/`master` по-прежнему запрещён policy.

Короткий SHA в dispatch раскрывается в полный (иначе `actions/checkout` ищет ветку).

## Безопасный cutover

Runner проверяет, что автоматический SHA из `dev` продолжает историю текущего
`.deployed_sha`. Если `dev` отстал от уже развернутой истории, workflow
завершится **до** миграции и перезапуска контейнеров. Сначала перенесите эту
историю в `dev` обычным merge/rebase.

Деплой сначала собирает candidate, создаёт backup и запускает `migrate`
preflight. Лишь затем перезапускаются bot/worker/api/webapp и проверяется
`http://127.0.0.1:8080/ready`. `.deployed_sha` записывается после успешной
проверки. При ошибке после cutover workflow возвращает предыдущие app-образы;
автоматического downgrade БД нет, поэтому миграции должны быть
expand/contract-совместимыми.

CI на `main` и `dev` дополнительно выполняет `alembic upgrade head` на чистом
PostgreSQL + pgvector и проверяет, что в графе миграций ровно один head.

## Бот → workflow_dispatch (rollback / owner approve)

Включение: `GITHUB_DEPLOY_DISPATCH=1` + `GITHUB_TOKEN` + `GITHUB_REPO` в прод-`.env`.
Бот вызывает `trigger_prod_deploy` → Actions на host-185. SSH из контейнера бота нет.
`/rollback` — ручной deploy кода старого SHA, а не downgrade схемы. Перед
откатом на SHA без текущих миграций подготовьте совместимую схему и backup.

## Secret ENV_PROD_BEACHOPS (Windows)

```bat
cmd /c "gh secret set ENV_PROD_BEACHOPS --repo von-waterloo/beachops < .env"
```

Legacy: `scripts/deploy-to-prod.ps1` — см. [OPERATIONS.md](./OPERATIONS.md).
