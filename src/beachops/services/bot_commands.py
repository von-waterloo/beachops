"""Telegram bot command menu registration."""

from __future__ import annotations

from telegram import (
    BotCommand,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    MenuButtonCommands,
    MenuButtonWebApp,
    WebAppInfo,
)


def bot_commands(*, is_admin: bool, is_owner: bool = False) -> list[BotCommand]:
    """Visible "/" menu — compact, logically grouped.

    `/help` (→ `/start`) and `/mode` (→ `/status`) are exact aliases of
    другой команды в этом списке: обработчики остаются зарегистрированы
    (привычные команды продолжают работать), но из меню скрыты, чтобы не
    дублировать пункты.
    """
    commands = [
        BotCommand("start", "Начало · инструкция и статус"),
        BotCommand("ask", "Режим · чат"),
    ]
    if is_admin:
        commands.extend(
            [
                BotCommand("plan", "Режим · план"),
                BotCommand("do", "Режим · действие"),
                BotCommand("task", "Задача · через план"),
            ]
        )
    commands.extend(
        [
            BotCommand("status", "Статус, режим, модель, токен"),
            BotCommand("agents", "Агенты · переключить/создать"),
            BotCommand("new", "Новый агент"),
            BotCommand("repo", "Репозитории"),
            BotCommand("remember", "Сохранить заметку в память"),
            BotCommand("memory", "Память · поиск"),
            BotCommand("cancel", "Отменить задачу"),
            BotCommand("jobs", "Задачи · статус и история"),
            BotCommand("dashboard", "Control Room · Mini App"),
        ]
    )
    if is_owner:
        commands.extend(
            [
                BotCommand("approvals", "Подтверждения владельца"),
                BotCommand("panic", "Аварийно остановить работу"),
                BotCommand("unpanic", "Вернуть write-действия"),
                BotCommand("rollback", "Откатить прод на предыдущий SHA"),
            ]
        )
    return commands


def _webapp_https_url(app) -> str:
    url = str(getattr(app.settings, "webapp_base_url", "")).strip()
    return url if url.lower().startswith("https://") else ""


async def register_bot_commands(application) -> None:
    app = application.bot_data["app"]
    await application.bot.set_my_commands(
        bot_commands(is_admin=False),
        scope=BotCommandScopeAllPrivateChats(),
    )
    privileged_ids = tuple(
        dict.fromkeys(
            (
                *app.settings.admin_user_ids,
                *app.settings.operator_user_ids,
                *app.settings.owner_user_ids,
            )
        )
    )
    for admin_id in privileged_ids:
        await application.bot.set_my_commands(
            bot_commands(
                is_admin=True,
                is_owner=app.settings.can_approve(admin_id),
            ),
            scope=BotCommandScopeChat(chat_id=admin_id),
        )

    webapp_url = _webapp_https_url(app)
    if webapp_url:
        await application.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Control Room",
                web_app=WebAppInfo(url=webapp_url),
            )
        )
    else:
        await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
