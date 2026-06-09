"""Prompt templates."""

from tg_cursor_bot.domain.models import UserMode

ASK_SYSTEM_PREFIX = """РЕЖИМ ЧАТ — только текстовый ответ в Telegram.

Запрет действий в репозитории:
- Не меняй, не создавай и не удаляй файлы.
- Не коммить, не пушь, не создавай ветки и PR.
- Можно читать код для понимания, но ответ — только текстом в чат.

Формат ответа (Telegram):
- Русский язык; без markdown-заголовков (##), mermaid, markdown-таблиц.
- Без путей к файлам (frontend/src/...) и без [blocked] — только понятные названия («генерация постов», «настройки проекта»).
- Структура: суть (3–6 пунктов) → рекомендация что делать и почему.
- Опросник (A/B/C, ответ буквами) — только если запрос про разработку/доработку продукта и без выбора нельзя спланировать реализацию (архитектура, UI, API, данные). Не больше 2–3 коротких вопросов; к каждому — рекомендуемый вариант по умолчанию.
- Если вопрос не про разработку, или выбор очевиден, или пользователь уже указал решение — опросник не нужен, дай прямой ответ.
- До ~2500 символов. Не пиши «сейчас сформирую план» без самого плана в этом же сообщении.

---

"""

MEMORY_PREFIX = "Контекст из памяти:\n{block}\n\n---\n\n"

GIT_SAFETY_TEMPLATE = """КРИТИЧНО — Git:
- НИКОГДА не делай git push в main или master (включая force), если пользователь явно не попросил запушить именно в main/master.
- Не пуши на remote вообще, пока пользователь явно не попросил push.
- Рабочая базовая ветка: {default_branch}. Создавай feature-ветки от неё; изменения в main/master — только через PR.
- Не делай force push в main/master; при такой просьбе предупреди о риске.

"""


def git_safety_prefix(*, default_branch: str) -> str:
    branch = default_branch.strip() or "dev"
    return GIT_SAFETY_TEMPLATE.format(default_branch=branch)


def build_prompt(
    text: str,
    mode: UserMode,
    *,
    default_branch: str = "dev",
    memory_block: str | None = None,
) -> str:
    body = text.strip()
    if memory_block:
        body = f"{MEMORY_PREFIX.format(block=memory_block)}{body}"
    if mode == UserMode.ASK:
        return f"{ASK_SYSTEM_PREFIX}{body}"
    if mode in (UserMode.PLAN, UserMode.DO):
        return f"{git_safety_prefix(default_branch=default_branch)}{body}"
    return body
