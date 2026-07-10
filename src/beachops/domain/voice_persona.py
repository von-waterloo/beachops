"""Spartan tone-of-voice for the BeachOps voice orchestrator.

Spoken replies go through OpenAI gpt-4o-mini-tts with steerable `instructions`.
Content is compressed into a laconic briefing before synthesis — the model
speaks status, not markdown novels.
"""

from __future__ import annotations

import re

# Steer gpt-4o-mini-tts delivery (tone / pace / persona). Content stays in `input`.
SPARTAN_TTS_INSTRUCTIONS = """
You are BeachOps — a private super-AI orchestrator in a war room.
Delivery: laconic Spartan commander. Short sentences. Steel composure.
No cheerfulness, no customer-support warmth, no filler, no hype.
Speak clear Russian when the text is Russian; otherwise match the input language.
Measured pace, firm and calm. Status first, then the next move.
Never whisper. Never sound apologetic or theatrical.
""".strip()

_CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_MD_HEADING_RE = re.compile(r"(?m)^#{1,6}\s+")
_MD_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*|__([^_]+)__")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_URL_RE = re.compile(r"https?://\S+")
_BULLET_RE = re.compile(r"(?m)^\s*[-*•]\s+")
_MULTI_SPACE_RE = re.compile(r"\s+")


def to_spoken_briefing(text: str, *, max_chars: int = 900) -> str:
    """Compress agent output into a voice-ready Spartan briefing."""
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
