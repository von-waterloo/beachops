# Self-hosted CI/CD (BeachOps)

Кратко: приватный репозиторий → CI на GitHub-hosted → деплой только через
`workflow_dispatch` на self-hosted runner **host-185**. Бот не хранит SSH-ключ
и не ходит на сервер напрямую.

## Репозиторий

- Целевой private repo: `von-waterloo/beachops` (`GITHUB_REPO`).
- Ветки: рабочая `dev`, прод-линия `main` (см. skill `github-branches`).
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

Деплой **не** стартует от push — только явный dispatch после owner-approve.

## Owner approval → workflow_dispatch

Планируемый поток:

1. Оператор/агент готовит изменения; CI зелёный на PR/`dev`.
2. Owner в Telegram одобряет deploy (approval kind `deploy`).
3. Бот вызывает `beachops.services.deploy_trigger.trigger_prod_deploy` с
   `GITHUB_TOKEN` (fine-grained / PAT с `actions:write` на этот repo) и SHA.
4. GitHub ставит job на runner host-185; бот только ждёт/показывает статус Actions.

Включение: `GITHUB_DEPLOY_DISPATCH=1` + `GITHUB_TOKEN` в прод-`.env`
(уже на `von-waterloo/beachops`).

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
- Нет автоматического push в `main` и нет auto-deploy на каждый commit.

Legacy ручной деплой с Windows (`scripts/deploy-to-prod.ps1`) остаётся запасным
каналом — см. [OPERATIONS.md](./OPERATIONS.md).

## Опционально

- [`.github/workflows/docker-publish.yml`](../.github/workflows/docker-publish.yml) —
  stub на теги `v*`; прод сейчас собирает образы на runner через compose.
