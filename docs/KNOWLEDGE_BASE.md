# BeachOps — база знаний

Единая точка входа: как пользоваться продуктом от первого `/start`
до Windows-агента на своём ПК и собственного деплоя.

Технические детали (env, схема БД, threat model) — в соседних документах;
здесь — **как жить с BeachOps каждый день**.

---

## Карта

| Хотите… | Читайте |
|---------|---------|
| Быстро начать в Telegram | [Онбординг](#онбординг) ниже |
| Команды и сценарии | [USER_GUIDE.md](./USER_GUIDE.md) |
| Cloud ↔ Windows worker | [Windows-агент](#windows-агент) ниже → [OPERATIONS.md](./OPERATIONS.md) |
| Поднять свой инстанс | [Свой деплой](#свой-деплой) ниже → [OPERATIONS.md](./OPERATIONS.md) |
| CI / owner-approve → прод | [SELF_DEPLOY.md](./SELF_DEPLOY.md) |
| Переменные `.env` | [CONFIGURATION.md](./CONFIGURATION.md) |
| Как устроено внутри | [ARCHITECTURE.md](./ARCHITECTURE.md) |

---

## Онбординг

### 1. Откройте бота

`/start` — статус, режимы, кнопки. Алиас `/help` делает то же самое.

### 2. Подключите репозиторий

Без активного репо промпт не примется.

```
/repo add https://github.com/you/repo
/repo add https://github.com/you/repo dev
```

Или Mini App → вкладка **Репо**. Если на сервере задан `DEFAULT_REPO_URL`,
новому пользователю репо подставится само при первом `/start`.

Репозиторий должен быть доступен Cursor (Dashboard → GitHub) и разрешён
политикой `REPOSITORY_POLICY_JSON` (пустой JSON = open mode).

### 3. Выберите режим

| Режим | Команда | Когда |
|-------|---------|--------|
| **Чат** | `/ask` | Вопрос по коду, без правок |
| **План** | `/plan` | Исследование + план; owner approve |
| **Задача** | `/task` | План → одноразовое Approve → запись |
| **Действие** | `/do` | Сразу пишет в базовую ветку (`dev` и т.п.) |

Для базы `main`/`master` `/do` уходит в изолированную ветку + PR.
Merge и деплой агент сам не делает.

### 4. Отправьте задачу

Текст · голос · фото/скрин · PDF/DOCX · пересылки из другого чата
(сначала пересылки, потом ваш вопрос).

Во время run сообщения копятся в durable-очереди. `/status` — режим,
модель, токен, активная задача. `/cancel` — стоп.

### 5. Откройте пульт

`/dashboard` — Mini App: голос realtime, агенты Cloud/Windows, репо,
очередь, approvals, health воркеров. Прямой вход на HTTPS — Passkey
(owner, после регистрации из Telegram).

В Mini App при первом входе — короткий **онбординг**; дальше справка
с анимированными типсами: кнопка **?** в шапке или полоска типса под
метриками. Полный текст — этот файл и [USER_GUIDE.md](./USER_GUIDE.md).

---

## Пульт управления

### Режимы и модели

- Кнопки на `/start`, `/status`, post-run: Composer 2.5 · Fable 5 · Sonnet 5 · GPT-5.6 Terra.
- Во время run — только «Отменить»; смена модели через `/status` или вкладку **Пульт**.
- Токены Cursor `mt` / `mt2` (если настроен второй ключ) — per-user; уже созданный
  агент остаётся на своём ключе → `/new` для нового токена.

### Слоты агентов

До `AGENT_SLOTS_MAX` (обычно 8) параллельных сессий Cursor:

```
/agents          — список и переключение
/new             — новый слот + сброс в чат
/agents rename … — имя активного
```

Каждый слот помнит репо и историю (`resume` по `cursor_agent_id`).
Переключение не архивирует облачного агента.

### Память

Автоматически после каждого run. Вручную: `/remember …`.
Список и поиск: `/memory`, `/memory запрос`. Кнопки **↻ #id** — повторить промпт.

### Очередь и approvals

- Jobs в Postgres (шифр) + ARQ; один actor — один активный Cursor run.
- `/jobs` — статусы; `/approvals` — решения owner.
- Plan/task → одноразовые Approve / Reject / Revision с TTL.
- Owner: `/panic` · `/unpanic` · `/rollback` `[sha]`.

### Роли

| Роль | Может |
|------|--------|
| `viewer` | Смотреть |
| `operator` | Читать / планировать / запрашивать write |
| `owner` | Approve, panic, rollback, Passkey, deploy-dispatch |

---

## Windows-агент

Cloud-агент крутится в Cursor Cloud. **Windows-агент** — на вашем ПК:
outbound worker claim'ит jobs с `runtime=windows` и запускает
`LocalAgentOptions(cwd=…)` через Cursor SDK.

### Зачем

Локальный cwd, IDE discovery, работа без cloud-песочницы — когда нужен
именно ваш диск и окружение Windows.

### Установка worker (Windows 11 + Docker Desktop)

1. На сервере BeachOps в `.env` задайте `WORKER_BOOTSTRAP_TOKEN`
   (длинный секрет) и перезапустите `api`.
2. На ПК скопируйте `.env.windows-worker.example` → `.env.windows-worker`:

   ```
   BEACHOPS_API_URL=https://ваш-mini-app-host
   BEACHOPS_WORKER_TOKEN=<тот же WORKER_BOOTSTRAP_TOKEN>
   CURSOR_API_KEY=<ключ Cursor на этой машине>
   # опционально:
   # BEACHOPS_HOST_WORK_ROOT=D:/Work
   # BEACHOPS_LOCAL_CWD=/host-work
   ```

3. Из корня репозитория:

   ```powershell
   .\scripts\install-windows-worker.ps1
   ```

4. Docker Desktop → Settings → General → **Start Docker Desktop when you sign in**
   (контейнер с `restart: unless-stopped` поднимется вместе с ПК).

Логи:

```powershell
docker compose -p beachops-windows-worker -f docker-compose.windows-worker.yml logs -f
```

Legacy без Docker: `.\scripts\install-windows-worker.ps1 -Native` (Scheduled Task, нужны права).

В Mini App чип **Windows** и фильтр Cloud / Windows показывают online-воркеры
и jobs. Подробнее API: [ARCHITECTURE.md](./ARCHITECTURE.md) → Windows worker.

### Привязка слота к Windows

Jobs берут runtime со **слота** (`user_agent_slots.runtime` + `local_path`).
По умолчанию слоты — `cloud`. Для Windows-слота задайте путь **внутри
контейнера worker** (том `BEACHOPS_HOST_WORK_ROOT` → `/host-work`):

```sql
UPDATE user_agent_slots
SET runtime = 'windows',
    local_path = '/host-work/YourRepo'
WHERE id = <slot_id> AND tg_user_id = <ваш_tg_id>;
```

`local_path` обязателен: без него Windows-job завершится с ошибкой.
Дальше обычные `/ask` · `/plan` · `/do` · голос — уйдут на ПК, не в ARQ cloud.

Вернуть в облако: `runtime = 'cloud'`, `local_path = NULL`.

---

## Свой деплой

Каждый инстанс — single-tenant. Чужие ключи, Telegram ID и репо автора
сюда не попадают: только ваши значения в `.env`.

### Минимальный путь

1. `.env.example` → `.env` — `TG_BOT_TOKEN`, `CURSOR_API_KEY`, `OWNER_USER_IDS`,
   `POSTGRES_PASSWORD`, `DATA_ENCRYPTION_KEY`, `REPOSITORY_POLICY_JSON`, …
2. GitHub в [Cursor Dashboard](https://cursor.com/dashboard), API key в Integrations.
3. Поднять стек:

   ```powershell
   docker compose up -d --build
   ```

Сервисы: `postgres` · `redis` · `migrate` · `bot` · `worker` · `api` · `webapp` (`:8080`).

Один процесс бота на один `TG_BOT_TOKEN` (иначе Conflict на long polling).

Mini App: публичный HTTPS в `WEBAPP_BASE_URL` + reverse-proxy на `:8080`
(Telegram не принимает HTTP/IP).

Полный ops-чеклист: [OPERATIONS.md](./OPERATIONS.md). Env: [CONFIGURATION.md](./CONFIGURATION.md).
Корневой [README.md](../README.md) — «Deploy your own copy».

### Self-deploy через GitHub Actions (прод автора)

Для копии **не обязательно**. Схема maintainer-прода:

1. CI на PR / `dev` / `main` (pytest, webapp, `compose config`).
2. Деплой **только** `workflow_dispatch` на self-hosted runner.
3. Owner approve в Telegram → бот дергает Actions (`GITHUB_DEPLOY_DISPATCH=1`).
4. В образе бота **нет** SSH-ключей — только GitHub token.

Документ: [SELF_DEPLOY.md](./SELF_DEPLOY.md).

Запасной ручной канал с Windows: `.\scripts\deploy-to-prod.ps1`
(см. OPERATIONS). После деплоя — миграции через сервис `migrate`.

### Самосовершенствование (opt-in)

Бот может работать над своим форком BeachOps — только если вы включите:

```
SELF_IMPROVE_ENABLED=1
SELF_IMPROVE_REPO_URL=https://github.com/you/beachops
SELF_IMPROVE_BRANCHES=dev
```

Затем Mini App → **Репо** → «Включить». Write идёт feature-branch + PR;
`main`/`master` protected. Плохой релиз: `/rollback`.

---

## Типичные ритуалы

**Спросить без правок**

```
/ask
Как устроена авторизация?
```

**Спланировать и одобрить**

```
/task
Добавь /health с проверкой Postgres
```

→ план в чат → owner **Одобрить**.

**Сразу в `dev`**

```
/do
Реализуй /health как в плане
```

**Скрин бага** — фото с подписью; альбомы склеиваются автоматически.

**Контекст из другого чата** — перешлите сообщения, затем напишите вопрос.

**Локальный Windows-run** — worker online + слот `runtime=windows` + путь к репо.

**Выкатить свою копию** — `.env` → `docker compose up -d --build`.

**Выкатить maintainer-прод** — зелёный CI → owner approve / Actions
или legacy `deploy-to-prod.ps1`.

---

## Безопасность в двух словах

- Private chat only; RBAC server-side.
- Repository allowlist; payload at rest encrypted.
- Plan/write через approvals; panic останавливает writes.
- Threat model: [THREAT_MODEL.md](./THREAT_MODEL.md).

---

## Куда углубиться

| Документ | Содержание |
|----------|------------|
| [USER_GUIDE.md](./USER_GUIDE.md) | Полный справочник команд и сценариев Telegram |
| [OPERATIONS.md](./OPERATIONS.md) | Docker, Windows worker, бэкапы, прод-хост |
| [SELF_DEPLOY.md](./SELF_DEPLOY.md) | Private repo, runner, workflow_dispatch |
| [CONFIGURATION.md](./CONFIGURATION.md) | Все env и дефолты |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Потоки, модули, схема БД |
| [DEVELOPMENT.md](./DEVELOPMENT.md) | Локальная разработка и тесты |
| [THREAT_MODEL.md](./THREAT_MODEL.md) | Границы доверия и инциденты |
