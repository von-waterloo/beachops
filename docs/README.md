# BeachOps — документация

Private control plane: Telegram + voice Mini App, Cursor Cloud Agents,
plan/owner approval workflow, Redis/ARQ, audit/redaction and panic lock.

## Содержание

| Документ | Для кого | Описание |
|----------|----------|----------|
| [Обзор и архитектура](./ARCHITECTURE.md) | разработчики | стек, потоки данных, модули, БД |
| [Руководство пользователя](./USER_GUIDE.md) | операторы бота | команды, режимы, сценарии в Telegram |
| [Разработка](./DEVELOPMENT.md) | разработчики | локальный запуск, структура кода, тесты |
| [Эксплуатация](./OPERATIONS.md) | DevOps | Docker, деплой, бэкапы, миграции |
| [Self-deploy / CI](./SELF_DEPLOY.md) | DevOps / owner | private repo, runner host-185, CI gate, bot → workflow_dispatch |
| [Конфигурация](./CONFIGURATION.md) | все | переменные окружения, права доступа |
| [Threat model](./THREAT_MODEL.md) | security/ops | trust boundaries, controls, incident response |

## Быстрый старт

1. Скопировать `.env.example` → `.env`, заполнить ключи.
2. Подключить GitHub в [Cursor Dashboard](https://cursor.com/dashboard).
3. Создать API key в [Integrations](https://cursor.com/dashboard/integrations).
4. Настроить roles, AES key и repository policy.
5. Поднять compose stack; `migrate` применит схему, затем запустятся bot/worker/API/webapp.

Подробности деплоя на прод — [OPERATIONS.md](./OPERATIONS.md), [SELF_DEPLOY.md](./SELF_DEPLOY.md) и `.cursor/rules/servers-access.mdc`.
