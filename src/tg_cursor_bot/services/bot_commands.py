"""Telegram bot command menu registration."""

from __future__ import annotations

from telegram import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat


def bot_commands(*, is_admin: bool) -> list[BotCommand]:
    commands = [
        BotCommand("start", "Инструкция и статус"),
        BotCommand("help", "Справка"),
        BotCommand("ask", "Режим · чат"),
    ]
    if is_admin:
        commands.extend(
            [
                BotCommand("plan", "Режим · план"),
                BotCommand("do", "Режим · действие"),
            ]
        )
    commands.extend(
        [
            BotCommand("mode", "Режим и статус"),
            BotCommand("agents", "Список агентов"),
            BotCommand("repo", "Репозитории"),
            BotCommand("new", "Новый агент"),
            BotCommand("remember", "Сохранить заметку"),
            BotCommand("memory", "Память / поиск"),
            BotCommand("status", "Статус задачи"),
            BotCommand("cancel", "Отменить задачу"),
        ]
    )
    return commands


async def register_bot_commands(application) -> None:
    app = application.bot_data["app"]
    await application.bot.set_my_commands(
        bot_commands(is_admin=False),
        scope=BotCommandScopeAllPrivateChats(),
    )
    for admin_id in app.settings.admin_user_ids:
        await application.bot.set_my_commands(
            bot_commands(is_admin=True),
            scope=BotCommandScopeChat(chat_id=admin_id),
        )
