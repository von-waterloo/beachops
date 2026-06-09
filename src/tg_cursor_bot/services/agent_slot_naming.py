"""Auto and manual labels for agent slots."""

from __future__ import annotations

import random
import re

from tg_cursor_bot.domain.models import RepoConfig

_LABEL_MAX_LEN = 48
_USER_BLOCK_PREFIX = "[Your message]\n"
_BLOCK_SEPARATOR = "\n\n---\n\n"

# 100 коротких «цепких» имён для новых слотов.
RANDOM_SLOT_LABELS: tuple[str, ...] = (
    "Лиса",
    "Якорь",
    "Сокол",
    "Компас",
    "Маяк",
    "Ворон",
    "Искра",
    "Север",
    "Ветер",
    "Ручей",
    "Заря",
    "Буря",
    "Клинок",
    "Щит",
    "Стрела",
    "Пламя",
    "Гром",
    "Молния",
    "Туман",
    "Роса",
    "Орёл",
    "Сова",
    "Заяц",
    "Барс",
    "Волк",
    "Кит",
    "Каштан",
    "Клён",
    "Осина",
    "Сосна",
    "Полынь",
    "Тмин",
    "Мята",
    "Чабрец",
    "Базальт",
    "Гранит",
    "Кварц",
    "Янтарь",
    "Жемчуг",
    "Шторм",
    "Прилив",
    "Камыш",
    "Песок",
    "Волна",
    "Бухта",
    "Скала",
    "Утёс",
    "Облако",
    "Радуга",
    "Звезда",
    "Луна",
    "Комета",
    "Орбита",
    "Импульс",
    "Вектор",
    "Сигнал",
    "Шифр",
    "Ключ",
    "Замок",
    "Карта",
    "Флаг",
    "Парус",
    "Курс",
    "Штурвал",
    "Линза",
    "Призма",
    "Спектр",
    "Эхо",
    "Ритм",
    "Мотив",
    "Стих",
    "Образ",
    "Идея",
    "След",
    "Тропа",
    "Берёзка",
    "Кедр",
    "Ель",
    "Пихта",
    "Мох",
    "Ласка",
    "Выдра",
    "Куница",
    "Рысь",
    "Сорока",
    "Грач",
    "Дятел",
    "Снег",
    "Иней",
    "Мороз",
    "Сумрак",
    "Рассвет",
    "Утро",
    "Вечер",
    "Полдень",
    "Багрянец",
    "Закат",
    "Гнездо",
    "Перья",
    "Костёр",
)

_RANDOM_LABELS_SET = frozenset(RANDOM_SLOT_LABELS)
_LEGACY_AUTO_LABEL_RE = re.compile(r"^(?:Агент \d+|Основной|.+ #\d+)$")
_GENERIC_PHRASES = frozenset(
    {
        "ok",
        "okay",
        "yes",
        "no",
        "да",
        "нет",
        "привет",
        "hello",
        "hi",
        "help",
        "спасибо",
        "thanks",
        "thank you",
    }
)


def random_slot_label() -> str:
    return random.choice(RANDOM_SLOT_LABELS)


def is_auto_slot_label(label: str) -> bool:
    """True if label is default/auto — safe to replace from first prompt."""
    cleaned = label.strip()
    if cleaned in _RANDOM_LABELS_SET:
        return True
    return bool(_LEGACY_AUTO_LABEL_RE.match(cleaned))


def default_slot_label(repo: RepoConfig | None, index: int) -> str:
    """Backward-compatible alias; new slots use random short names."""
    del repo, index
    return random_slot_label()


def _truncate_label(line: str, *, max_len: int = _LABEL_MAX_LEN) -> str:
    line = re.sub(r"\s+", " ", line.strip())
    if len(line) <= max_len:
        return line
    return line[: max_len - 1].rstrip() + "…"


def _is_generic_line(line: str) -> bool:
    normalized = line.strip().lower()
    if not normalized:
        return True
    if len(normalized) < 8:
        return True
    if normalized in _GENERIC_PHRASES:
        return True
    if normalized.startswith("[instruction]"):
        return True
    return False


def _label_from_user_block(block: str) -> str | None:
    if not block.startswith(_USER_BLOCK_PREFIX):
        return None
    body = block[len(_USER_BLOCK_PREFIX) :].strip()
    if not body:
        return None
    line = body.split("\n")[0].strip()
    if _is_generic_line(line):
        return None
    return _truncate_label(line)


def _label_from_forward_block(block: str) -> str | None:
    lines = [line.strip() for line in block.split("\n") if line.strip()]
    if len(lines) < 2:
        return None
    if not lines[0].startswith("[Forwarded"):
        return None
    line = lines[1]
    if line.startswith("[") or _is_generic_line(line):
        return None
    return _truncate_label(line)


def label_from_prompt(prompt: str, *, max_len: int = _LABEL_MAX_LEN) -> str | None:
    """Pick a human label from the user's text, not system/forward boilerplate."""
    text = prompt.strip()
    if not text:
        return None

    if _USER_BLOCK_PREFIX in text:
        for block in text.split(_BLOCK_SEPARATOR):
            label = _label_from_user_block(block.strip())
            if label:
                return label

    if _BLOCK_SEPARATOR not in text and not text.startswith("["):
        line = text.split("\n")[0].strip()
        if not _is_generic_line(line):
            return _truncate_label(line, max_len=max_len)

    blocks = text.split(_BLOCK_SEPARATOR)
    for block in reversed(blocks):
        cleaned = block.strip()
        if not cleaned or cleaned.startswith("[Instruction]"):
            continue
        label = _label_from_user_block(cleaned)
        if label:
            return label
        label = _label_from_forward_block(cleaned)
        if label:
            return label

    return None


def slot_button_text(label: str, *, is_active: bool, max_len: int = 28) -> str:
    suffix = " ✓" if is_active else ""
    room = max_len - len(suffix)
    text = label if len(label) <= room else label[: room - 1].rstrip() + "…"
    return f"{text}{suffix}"
