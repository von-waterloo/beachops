"""User-facing copy and message layout helpers."""

from __future__ import annotations

from tg_cursor_bot.domain.models import AgentSlot, MemoryEntry, RepoConfig, UserMode

MODE_LABELS: dict[str, str] = {
    "ask": "чат",
    "plan": "план",
    "do": "действие",
}

MODE_ICONS: dict[str, str] = {
    "ask": "❓",
    "plan": "📋",
    "do": "⚡",
}

EMPTY_STREAM_HINT = "Ожидаю ответ агента…"

_TOOL_STATUS_ICON: dict[str, str] = {
    "running": "🔄",
    "in_progress": "🔄",
    "completed": "✅",
    "done": "✅",
    "success": "✅",
    "failed": "❌",
    "error": "❌",
    "cancelled": "⏹",
}

_TOOL_STATUS_LABEL: dict[str, str] = {
    "running": "выполняется",
    "in_progress": "выполняется",
    "completed": "готово",
    "done": "готово",
    "success": "готово",
    "failed": "ошибка",
    "error": "ошибка",
    "cancelled": "отменено",
}


def build_run_header(mode: UserMode, repo_alias: str) -> str:
    mode_label = MODE_LABELS.get(mode.value, mode.value)
    return f"Режим · {mode_label}\nРепо · {repo_alias}"


def build_run_footer(
    *,
    pr_url: str | None = None,
    agent_id: str | None = None,
    error_message: str | None = None,
    duration_ms: int | None = None,
) -> str:
    lines: list[str] = []
    if duration_ms is not None and duration_ms >= 1000:
        secs = duration_ms // 1000
        lines.append(f"⏱ {secs} сек")
    if pr_url:
        lines.append(f"🔗 PR: {pr_url}")
    if agent_id:
        lines.append(f"🤖 Агент: https://cursor.com/agents/{agent_id}")
    if error_message:
        lines.append(f"⚠️ {error_message}")
    return "\n".join(lines)


def format_tool_line(name: str, status: str) -> str:
    key = status.lower().strip()
    icon = _TOOL_STATUS_ICON.get(key, "🔧")
    label = _TOOL_STATUS_LABEL.get(key, status)
    return f"{icon} {name} — {label}"


def format_thinking_line(char_count: int) -> str:
    return f"_Думаю… ({char_count} симв.)_"


def format_thinking_preview(text: str, *, max_chars: int = 300) -> str:
    snippet = text.strip()
    if len(snippet) > max_chars:
        snippet = "…" + snippet[-max_chars:]
    return f"_💭 {snippet}_"


def agent_cursor_link(agent_id: str) -> str:
    return f"🤖 Cursor: https://cursor.com/agents/{agent_id}"


def queued_message(position: int) -> str:
    return (
        f"📋 Запрос в очереди (#{position}).\n\n"
        "Ответ появится, когда дойдёт очередь.\n"
        "Отменить всё: /cancel или кнопка «Отменить»."
    )


def queue_full_message() -> str:
    return (
        "⏳ Очередь заполнена (макс. 2 ожидающих).\n\n"
        "Дождитесь ответа или отмените: /cancel"
    )


def queue_full_keep_buffer() -> str:
    return (
        "⏳ Очередь заполнена — пересланный контекст сохранён.\n\n"
        "Дождитесь ответа или /cancel, затем повторите вопрос."
    )


def forward_context_hint(timeout_sec: int) -> str:
    return (
        "📎 Контекст собирается.\n\n"
        "Перешлите ещё сообщения или напишите вопрос.\n"
        f"Автоотправка через {timeout_sec} сек после последней пересылки."
    )


def forward_context_hint_count(count: int, timeout_sec: int) -> str:
    return (
        f"📎 Собрано пересланных: {count}.\n\n"
        "Напишите вопрос или дождитесь автоотправки.\n"
        f"Таймер: {timeout_sec} сек после последней пересылки."
    )


def forward_buffer_full(max_items: int) -> str:
    return (
        f"📎 Буфер пересылок полон ({max_items}).\n\n"
        "Напишите вопрос, чтобы отправить агенту."
    )


def forward_context_default_prompt() -> str:
    return (
        "[Instruction]\n"
        "Отнесись к пересланному контексту как к рабочей задаче (баг, идея, запрос).\n"
        "Сформулируй суть проблемы или цель; изучи релевантный код в текущем репозитории; "
        "назови вероятную причину или предложи, как починить или внедрить.\n"
        "Конкретика по проекту важнее пересказа переписки."
    )


def forward_flush_failed() -> str:
    return (
        "⚠️ Не удалось отправить пересланные сообщения.\n\n"
        "Перешлите снова или напишите вопрос текстом."
    )


def voice_no_speech() -> str:
    return "🎤 Не удалось распознать речь.\n\nЗапишите сообщение чуть громче и короче."


def voice_error() -> str:
    return "⚠️ Не удалось обработать голосовое.\n\nПовторите или отправьте текстом."


def photo_default_prompt() -> str:
    return (
        "Разбери скриншот(ы) и предложи, что проверить или исправить в коде."
    )


def photo_error() -> str:
    return "⚠️ Не удалось обработать изображение.\n\nПовторите или отправьте текстом."


def photo_unsupported_document() -> str:
    return (
        "📎 Поддерживаются только изображения (PNG, JPEG, WebP, GIF).\n\n"
        "PDF и DOCX отправляйте как файл (не как фото)."
    )


def document_empty() -> str:
    return (
        "📄 Не удалось извлечь текст из документа.\n\n"
        "Возможно, это скан без текстового слоя. "
        "Отправьте текстовую версию или перешлите ключевые фрагменты сообщением."
    )


def document_too_large(size_bytes: int | None, max_bytes: int) -> str:
    size_mb = f"{size_bytes / (1024 * 1024):.1f} МБ" if size_bytes else "файл"
    max_mb = max_bytes / (1024 * 1024)
    return (
        f"📎 Документ слишком большой ({size_mb}).\n\n"
        f"Максимум — {max_mb:.0f} МБ. Сожмите файл или пришлите выдержку текстом."
    )


def document_truncated(max_chars: int) -> str:
    return (
        f"📄 Документ длинный — в задачу переданы первые {max_chars:,} символов "
        "с пометкой об обрезке."
    ).replace(",", " ")


def document_error() -> str:
    return "⚠️ Не удалось обработать документ.\n\nПовторите или отправьте текстом."


def photo_too_many(taken: int, max_count: int) -> str:
    return f"📷 В альбоме {taken} фото — в задачу передано первые {max_count}."


def access_denied_mode(mode: UserMode) -> str:
    return (
        f"🔒 Режим /{mode.value} доступен только администраторам.\n\n"
        "Используйте /ask."
    )


def no_repo_selected() -> str:
    return "📁 Репозиторий не выбран.\n\nДобавьте: /repo add https://github.com/org/repo"


def repo_add_hint(default_branch: str) -> str:
    return (
        "📁 Как добавить репозиторий:\n\n"
        "/repo add https://github.com/org/repo\n\n"
        f"Ветка по умолчанию · {default_branch} (или укажите в конце: …/repo main)\n\n"
        "Или откройте /repo — выберите из списка кнопкой."
    )


def repo_saved(alias: str, *, is_active: bool) -> str:
    active = " · активный" if is_active else ""
    return f"✅ Репо · {alias}{active}"


def repo_switched(alias: str) -> str:
    return f"✅ Репо · {alias}"


def agent_list_header(*, page: int = 0, total_pages: int = 1) -> str:
    lines = [
        "Агенты · нажмите имя для переключения",
        "Под именем — редактировать или удалить",
    ]
    if total_pages > 1:
        lines.append(f"Страница {page + 1} из {total_pages}")
    return "\n".join(lines)


def agent_list_line(slot: AgentSlot) -> str:
    mark = " ✓" if slot.is_active else ""
    repo_part = f" · {slot.repo_alias}" if slot.repo_alias else ""
    status = " · есть контекст" if slot.cursor_agent_id else ""
    return f"· {slot.label}{mark}{repo_part}{status}"


def agent_switched(label: str) -> str:
    return f"✅ Агент · {label}"


def agent_created(label: str) -> str:
    return (
        f"✅ Новый агент · {label}\n\n"
        "Следующее сообщение пойдёт в этот слот."
    )


def agent_slots_full(max_slots: int) -> str:
    return (
        f"Достигнут лимит агентов ({max_slots}).\n\n"
        "Переключитесь на существующий через /agents."
    )


def agent_new_from_command(label: str) -> str:
    return (
        f"✅ Новая сессия · {label}\n\n"
        "Предыдущие агенты сохранены — /agents для переключения."
    )


def agent_not_found() -> str:
    return "Агент не найден."


def agent_rename_usage() -> str:
    return (
        "Пример:\n"
        "/agents rename Метрика — пропал отчёт"
    )


def agent_renamed(label: str) -> str:
    return f"✅ Агент переименован · {label}"


def agent_rename_failed() -> str:
    return "Не удалось переименовать. Выберите агента через /agents."


def agent_rename_prompt(current_label: str) -> str:
    return (
        f"✏️ Переименовать «{current_label}»\n\n"
        "Ответьте новым именем одним сообщением.\n"
        "Отмена: /cancel"
    )


def agent_rename_cancelled() -> str:
    return "Переименование отменено."


def agent_delete_confirm(label: str) -> str:
    return (
        f"🗑 Удалить агента «{label}»?\n\n"
        "Сессия Cursor отвяжется; история в Cursor останется на их стороне.\n"
        "Активный run будет отменён."
    )


def agent_deleted(label: str, *, new_active_label: str | None) -> str:
    if new_active_label:
        return f"🗑 Удалён · {label}\n\nАктивный агент · {new_active_label}"
    return f"🗑 Удалён · {label}"


def agent_delete_last() -> str:
    return "Нельзя удалить последнего агента — нужен хотя бы один слот."


def agent_delete_failed() -> str:
    return "Не удалось удалить агента."


def repo_not_found(alias: str) -> str:
    return f"Репо «{alias}» не найден."


def repo_list_header() -> str:
    return "Репозитории · выберите кнопкой или /repo <alias>"


def repo_list_line(repo: RepoConfig) -> str:
    mark = " · активный" if repo.is_active else ""
    return f"· {repo.alias}{mark}\n  {repo.github_url} ({repo.default_branch})"


def repo_empty(default_branch: str) -> str:
    return (
        "Репозитории не настроены.\n\n"
        "/repo add https://github.com/org/repo\n\n"
        f"Ветка по умолчанию · {default_branch}"
    )


def mode_set(mode: UserMode) -> str:
    label = MODE_LABELS.get(mode.value, mode.value)
    return f"✅ Режим · {label}"


def mode_set_next(mode: UserMode) -> str:
    label = MODE_LABELS.get(mode.value, mode.value)
    return f"Режим · {label}. Применится к следующему сообщению."


def model_set(model_key: str) -> str:
    from tg_cursor_bot.domain.cursor_models import cursor_model_label

    return f"✅ Модель · {cursor_model_label(model_key)}"


def model_set_next(model_key: str) -> str:
    from tg_cursor_bot.domain.cursor_models import cursor_model_label

    return f"Модель · {cursor_model_label(model_key)}. Применится к следующему сообщению."


def cancel_ok(*, cleared_queue: int = 0, cleared_forwards: int = 0) -> str:
    parts: list[str] = ["✅ Задача отменена."]
    if cleared_queue:
        parts.append(f"Из очереди снято: {cleared_queue}.")
    if cleared_forwards:
        parts.append(f"Пересланных в буфере снято: {cleared_forwards}.")
    return " ".join(parts) if len(parts) > 1 else parts[0]


def cancel_none() -> str:
    return "Нет активной задачи.\n\nОтправьте текст, голос или фото, чтобы начать."


def cancel_failed() -> str:
    return "Задача уже завершена или не может быть отменена."


def cancel_inline_answer() -> str:
    return "Отменяю…"


def memory_empty() -> str:
    return "Память пуста."


def memory_header() -> str:
    return "Память · последние записи · ↻ повторить запуск"


def memory_search_header(query: str) -> str:
    return f"Память · поиск: {query[:60]}"


def memory_note_saved(entry_id: int) -> str:
    return f"Заметка сохранена (#{entry_id})."


def memory_item_line(item: MemoryEntry) -> str:
    kind_label = "заметка" if item.kind == "note" else "запуск"
    body_preview = (item.body or "")[:120]
    pr = f"\n🔗 {item.pr_url}" if item.pr_url else ""
    mode_part = ""
    if item.mode:
        mode_part = f" · {MODE_LABELS.get(item.mode, item.mode)}"
    return (
        f"\n#{item.id} · {kind_label}{mode_part}{pr}\n"
        f"{item.title[:80]}\n"
        f"{body_preview}"
    )


def retry_no_prompt() -> str:
    return "Нет сохранённого запроса для повтора."


def build_welcome_message(
    *,
    mode: UserMode,
    model_key: str,
    repo: RepoConfig | None,
    is_admin: bool,
    has_repos: bool,
    active_agent_label: str | None = None,
) -> str:
    from tg_cursor_bot.domain.cursor_models import cursor_model_label

    mode_label = MODE_LABELS.get(mode.value, mode.value)
    model_label = cursor_model_label(model_key)
    if repo:
        repo_line = f"{repo.alias}"
    elif has_repos:
        repo_line = "не выбран — откройте /repo"
    else:
        repo_line = "не добавлен — см. быстрый старт"

    agent_line = active_agent_label or "Агент 1"

    lines = [
        "Telegram ↔ Cursor Cloud Agents",
        "",
        "Сейчас",
        f"· Режим · {mode_label}",
        f"· Модель · {model_label}",
        f"· Репо · {repo_line}",
        f"· Агент · {agent_line}",
        "",
        "Быстрый старт",
        "1. /repo add https://github.com/org/repo",
        "2. Кнопки режима ниже или /ask",
        "3. Текст, 🎤 голосом или 📷 фото — задача уйдёт агенту",
        "",
        "Режимы",
        "· чат (/ask) — ответ без правок кода",
    ]
    if is_admin:
        lines.extend(
            [
                "· план (/plan) — план изменений",
                "· действие (/do) — правки и PR",
            ]
        )
    else:
        lines.append("· /plan и /do — только для администраторов")

    lines.extend(
        [
            "",
            "Пока агент работает",
            "· Ответ стримится в одном сообщении",
            "· Отмена: кнопка «Отменить» или /cancel",
            "· Второй запрос встанет в очередь (до 2)",
            "",
            "Память",
            "/remember текст — сохранить заметку",
            "/memory — последние записи; /memory запрос — семантический поиск",
            "",
            "Команды",
            "/mode /agents /repo /new /remember /memory /status /cancel /help",
        ]
    )
    return "\n".join(lines)


def build_status_message(
    *,
    mode: UserMode,
    model_key: str,
    repo: RepoConfig | None,
    is_active: bool,
    pending_count: int,
    has_active_run: bool,
    forward_buffer_count: int = 0,
    active_agent_label: str | None = None,
) -> str:
    from tg_cursor_bot.domain.cursor_models import cursor_model_label

    mode_label = MODE_LABELS.get(mode.value, mode.value)
    model_label = cursor_model_label(model_key)
    repo_line = repo.alias if repo else "не выбран"
    agent_line = active_agent_label or "Агент 1"

    lines = [
        "Статус",
        "",
        f"· Режим · {mode_label}",
        f"· Модель · {model_label}",
        f"· Репо · {repo_line}",
        f"· Агент · {agent_line}",
    ]
    if forward_buffer_count:
        lines.append(
            f"· Пересылки · {forward_buffer_count} в буфере (напишите вопрос)"
        )
    if is_active:
        lines.append("· Задача · выполняется")
    elif pending_count:
        lines.append(f"· Очередь · {pending_count} ожидает")
    else:
        lines.append("· Задача · свободен")

    if has_active_run:
        lines.append("· Run · активен (можно /cancel)")

    return "\n".join(lines)
