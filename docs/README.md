# BeachOps — документация

Диалог программиста с Cursor-агентами: Telegram + voice Mini App, ask/plan/do,
слоты агентов, Cloud/Windows runtime, plan/owner approval, durable jobs и audit.

## Содержание

| Документ | Для кого | Описание |
|----------|----------|----------|
| [Обзор и архитектура](./ARCHITECTURE.md) | разработчики | стек, потоки данных, модули, БД |
| [Руководство пользователя](./USER_GUIDE.md) | операторы бота | команды, режимы, сценарии в Telegram |
| [Разработка](./DEVELOPMENT.md) | разработчики | локальный запуск, структура кода, тесты |
| [Эксплуатация](./OPERATIONS.md) | DevOps | Docker, деплой, бэкапы, миграции |
| [Self-deploy / CI](./SELF_DEPLOY.md) | DevOps / owner | main/dev → CI → auto-deploy host-185; bot rollback via workflow_dispatch |
| [Конфигурация](./CONFIGURATION.md) | все | переменные окружения, права доступа |
| [Threat model](./THREAT_MODEL.md) | security/ops | trust boundaries, controls, incident response |

## Быстрый старт

1. Скопировать `.env.example` → `.env` (короткий шаблон) и заполнить ключи.
2. Подключить GitHub в [Cursor Dashboard](https://cursor.com/dashboard).
3. Создать API key в [Integrations](https://cursor.com/dashboard/integrations).
4. Поднять compose; `migrate` применит схему, затем bot/worker/API/webapp.
   Тонкая настройка — [CONFIGURATION.md](./CONFIGURATION.md).

Свой деплой: [OPERATIONS.md](./OPERATIONS.md) (Docker Compose) и корневой
[README.md](../README.md) («Deploy your own copy»). Прод автора / runner
host-185 — [SELF_DEPLOY.md](./SELF_DEPLOY.md) и `.cursor/rules/servers-access.mdc`
(не требуется для чужой инсталляции).
