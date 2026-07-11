"""BeachOps tone-of-voice for the voice orchestrator.

Spoken replies go through OpenAI gpt-4o-mini-tts (Dec 2025 snapshot) with
steerable `instructions`. Content is compressed into a laconic briefing
before synthesis — the model speaks status, not markdown novels.
"""

from __future__ import annotations

import re

# Steer gpt-4o-mini-tts delivery (tone / pace / persona). Content stays in `input`.
SPARTAN_TTS_INSTRUCTIONS = """
You are BeachOps — a private AI coding orchestrator.
Delivery: calm, laconic, precise. Short sentences. No filler.
No cheerfulness, no customer-support warmth, no hype, no theatrics.
Speak clear Russian when the text is Russian; otherwise match the input language.
Measured pace, firm and calm. Status first, then the next move.
Never whisper. Never sound apologetic or theatrical.
""".strip()

# Bias realtime / Audio STT toward BeachOps domain terms (short keyword list).
BEACHOPS_STT_PROMPT = (
    "Keywords: BeachOps, control room, Cursor, composer, agent, slot, runtime, "
    "cloud, Windows, worker, queue, plan, ask, do, approve, reject, revision, "
    "PR, pull request, branch, commit, deploy, rollback, migrate, postgres, "
    "redis, Mini App, Telegram, webhook, polling, job, blocked, awaiting approval."
)

_CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_MD_HEADING_RE = re.compile(r"(?m)^#{1,6}\s+")
_MD_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*|__([^_]+)__")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_URL_RE = re.compile(r"https?://\S+")
_BULLET_RE = re.compile(r"(?m)^\s*[-*•]\s+")
_MULTI_SPACE_RE = re.compile(r"\s+")

# Status transitions worth speaking mid-run (terminal / ack-covered skipped).
_STATUS_MILESTONES: dict[str, str] = {
    "planning": "Строю план.",
    "approved": "Approve получен. Запускаю.",
    "running": "Агент в работе.",
    "awaiting_approval": "Ждёт вашего approve.",
    "review_required": "Нужен review.",
    "revision_requested": "Нужна revision.",
    "paused": "Пауза.",
    "blocked": "Задача заблокирована.",
}

_PROGRESS_AGENT_RE = re.compile(
    r"agent\s+started|агент\s+запущ|connecting|подключ",
    re.IGNORECASE,
)
_PROGRESS_EDIT_RE = re.compile(
    r"\btool\b|редактир|пишу\s+файл|writing\s+file|editing",
    re.IGNORECASE,
)


def spoken_ack(*, runtime: str | None = None, room: str | None = None) -> str:
    """Short take-job acknowledgement for Mini App mid-run voice."""
    bits = ["Взял."]
    rt = (runtime or "").strip().lower()
    if rt == "windows":
        bits.append("Windows.")
    elif rt:
        bits.append("Cloud.")
    room_bit = (room or "").strip()
    if room_bit:
        bits.append(room_bit)
    return " ".join(bits)


def milestone_line(
    *,
    status: str | None = None,
    previous_status: str | None = None,
    progress_text: str | None = None,
) -> str | None:
    """Map a job status change / progress caption to a laconic spoken line.

    Returns None for noise (no change, queued, terminal, empty progress).
    """
    current = (status or "").strip().lower() or None
    previous = (previous_status or "").strip().lower() or None

    if current and current != previous:
        line = _STATUS_MILESTONES.get(current)
        if line:
            return line

    text = (progress_text or "").strip()
    if not text:
        return None
    if _PROGRESS_AGENT_RE.search(text):
        return "Агент на связи."
    if _PROGRESS_EDIT_RE.search(text):
        return "Правит код."
    return None


class MilestoneGate:
    """Anti-spam gate for mid-run TTS (interval + max count per job)."""

    def __init__(self, *, min_interval_sec: float, max_per_job: int) -> None:
        self.min_interval_sec = max(0.0, float(min_interval_sec))
        self.max_per_job = max(0, int(max_per_job))
        self.count = 0
        self.last_spoke_at: float | None = None
        self.last_line: str | None = None

    def allow(self, now: float, line: str | None) -> bool:
        if not line:
            return False
        if line == self.last_line:
            return False
        if self.count >= self.max_per_job:
            return False
        if (
            self.last_spoke_at is not None
            and (now - self.last_spoke_at) < self.min_interval_sec
        ):
            return False
        return True

    def mark(self, now: float, line: str, *, count: bool = True) -> None:
        if count:
            self.count += 1
        self.last_spoke_at = now
        self.last_line = line


def to_spoken_briefing(text: str, *, max_chars: int = 900) -> str:
    """Compress agent output into a voice-ready laconic briefing."""
    value = (text or "").strip()
    if not value:
        return ""

    value = _CODE_BLOCK_RE.sub(" Код на экране. ", value)
    value = _MD_LINK_RE.sub(r"\1", value)
    value = _URL_RE.sub(" ссылка на экране ", value)
    value = _INLINE_CODE_RE.sub(r"\1", value)
    value = _MD_HEADING_RE.sub("", value)
    value = _MD_BOLD_RE.sub(lambda m: m.group(1) or m.group(2) or "", value)
    value = _BULLET_RE.sub("", value)
    value = _MULTI_SPACE_RE.sub(" ", value).strip(" -•")

    if len(value) <= max_chars:
        return value

    cut = value[: max_chars + 1]
    # Prefer a sentence boundary near the limit.
    for sep in (". ", "! ", "? ", "; "):
        idx = cut.rfind(sep)
        if idx >= max_chars // 2:
            return cut[: idx + 1].strip()
    space = cut.rfind(" ")
    if space >= max_chars // 2:
        return cut[:space].rstrip(" ,;:") + "."
    return cut[:max_chars].rstrip(" ,;:") + "."
