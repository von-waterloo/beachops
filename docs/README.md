# tg-cursor-bot — документация

Telegram-бот — интерфейс к **Cursor Cloud Agents**: текст, голос, фото; режимы ask/plan/do; семантическая память (Postgres + pgvector); очередь задач; мульти-репо.

## Содержание

| Документ | Для кого | Описание |
|----------|----------|----------|
| [Обзор и архитектура](./ARCHITECTURE.md) | разработчики | стек, потоки данных, модули, БД |
| [Руководство пользователя](./USER_GUIDE.md) | операторы бота | команды, режимы, сценарии в Telegram |
| [Разработка](./DEVELOPMENT.md) | разработчики | локальный запуск, структура кода, тесты |
| [Эксплуатация](./OPERATIONS.md) | DevOps | Docker, деплой, бэкапы, миграции |
| [Конфигурация](./CONFIGURATION.md) | все | переменные окружения, права доступа |

## Быстрый старт

1. Скопировать `.env.example` → `.env`, заполнить ключи.
2. Подключить GitHub в [Cursor Dashboard](https://cursor.com/dashboard).
3. Создать API key в [Integrations](https://cursor.com/dashboard/integrations).
4. Поднять Postgres и применить миграции (см. [DEVELOPMENT.md](./DEVELOPMENT.md)).
5. Запустить бота, в Telegram отправить `/start`.

Подробности деплоя на прод — [OPERATIONS.md](./OPERATIONS.md) и `.cursor/rules/servers-access.mdc`.
