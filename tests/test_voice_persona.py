from beachops.domain.voice_persona import SPARTAN_TTS_INSTRUCTIONS, to_spoken_briefing


def test_spoken_briefing_strips_code_and_urls() -> None:
    raw = (
        "Готово.\n\n```python\nprint('x')\n```\n"
        "Смотри https://github.com/acme/app/pull/1 и файл `src/app.py`."
    )
    spoken = to_spoken_briefing(raw)
    assert "```" not in spoken
    assert "https://" not in spoken
    assert "Готово" in spoken
    assert "src/app.py" in spoken


def test_spoken_briefing_respects_max_chars_at_sentence() -> None:
    raw = "Первое предложение. " + ("Дальше много текста. " * 80)
    spoken = to_spoken_briefing(raw, max_chars=80)
    assert len(spoken) <= 81
    assert spoken.endswith(".")


def test_spartan_instructions_are_laconic() -> None:
    lower = SPARTAN_TTS_INSTRUCTIONS.lower()
    assert "laconic" in lower or "spartan" in lower or "calm" in lower
    assert "cheerfulness" in lower or "filler" in lower
    assert "war-room" not in lower and "war room" not in lower
