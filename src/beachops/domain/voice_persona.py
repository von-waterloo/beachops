"""BeachOps tone-of-voice for Mini App voice.

Spoken replies go through OpenAI TTS. Content is compressed into a short
conversational briefing — like a beach coworker, not a control-room ticker.
"""

from __future__ import annotations

import re

# Steer gpt-4o-mini-tts delivery (tone / pace / persona). Content stays in `input`.
SPARTAN_TTS_INSTRUCTIONS = """
You are BeachOps — a calm beach coworker who helps with coding ops.
Delivery: natural, warm, concise. Short spoken sentences. Light filler is ok.
No status-report voice, no military briefing, no cheerleading hype.
Speak clear Russian when the text is Russian; otherwise match the input language.
Conversational pace. Sound like you're talking to a friend on the beach.
Never whisper. Never sound apologetic or theatrical.
""".strip()

# Bias realtime / Audio STT toward BeachOps domain terms (short keyword list).
BEACHOPS_STT_PROMPT = (
    "Keywords: BeachOps, Cursor, composer, agent, slot, cloud, queue, plan, ask, do, "
    "approve, reject, revision, PR, pull request, branch, commit, deploy, rollback, "
    "migrate, postgres, redis, Mini App, Telegram, docker, logs, ssh, beach."
)

_CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_MD_HEADING_RE = re.compile(r"(?m)^#{1,6}\s+")
_MD_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*|__([^_]+)__")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_URL_RE = re.compile(r"https?://\S+")
_BULLET_RE = re.compile(r"(?m)^\s*[-*•]\s+")
_MULTI_SPACE_RE = re.compile(r"\s+")

# Only rare human-facing mid-run lines (metrics / tool chatter stay silent).
_STATUS_MILESTONES: dict[str, str] = {
    "awaiting_approval": "План готов — глянь и скажи, делать или нет.",
}


def spoken_ack(*, runtime: str | None = None, room: str | None = None) -> str:
    """Short human acknowledgement — no queue/runtime/metrics."""
    del runtime, room  # kept for call-site compatibility
    return "Ок, беру."


def milestone_line(
    *,
    status: str | None = None,
    previous_status: str | None = None,
    progress_text: str | None = None,
) -> str | None:
    """Map a job status change to a rare human spoken line.

    Progress chatter and routine statuses return None.
    """
    del progress_text
    current = (status or "").strip().lower() or None
    previous = (previous_status or "").strip().lower() or None

    if current and current != previous:
        return _STATUS_MILESTONES.get(current)
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
    """Compress agent output into a voice-ready conversational briefing."""
    value = (text or "").strip()
    if not value:
        return ""

    value = _CODE_BLOCK_RE.sub(" ", value)
    value = _MD_LINK_RE.sub(r"\1", value)
    value = _URL_RE.sub(" ", value)
    value = _INLINE_CODE_RE.sub(r"\1", value)
    value = _MD_HEADING_RE.sub("", value)
    value = _MD_BOLD_RE.sub(lambda m: m.group(1) or m.group(2) or "", value)
    value = _BULLET_RE.sub("", value)
    value = _MULTI_SPACE_RE.sub(" ", value).strip(" -•")

    if len(value) <= max_chars:
        return value

    cut = value[: max_chars + 1]
    for sep in (". ", "! ", "? ", "; "):
        idx = cut.rfind(sep)
        if idx >= max_chars // 2:
            return cut[: idx + 1].strip()
    space = cut.rfind(" ")
    if space >= max_chars // 2:
        return cut[:space].rstrip(" ,;:") + "."
    return cut[:max_chars].rstrip(" ,;:") + "."
