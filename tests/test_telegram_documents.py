"""Tests for Telegram document extraction helpers."""

from __future__ import annotations

from io import BytesIO

import fitz
from docx import Document

from beachops.services.telegram_documents import (
    build_document_prompt,
    build_prompt_text,
    extract_text_from_bytes,
    truncate_document_text,
)


def _make_pdf_bytes(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def _make_docx_bytes(*lines: str) -> bytes:
    doc = Document()
    for line in lines:
        doc.add_paragraph(line)
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def test_extract_pdf_text():
    data = _make_pdf_bytes("Hello PDF world")
    text = extract_text_from_bytes(data, kind="pdf")
    assert "Hello PDF world" in text


def test_extract_docx_text():
    data = _make_docx_bytes("First line", "Second line")
    text = extract_text_from_bytes(data, kind="docx")
    assert "First line" in text
    assert "Second line" in text


def test_truncate_document_text():
    text, truncated = truncate_document_text("abcdef", max_chars=3)
    assert truncated is True
    assert text.startswith("abc")
    assert "обрезан" in text

    same, truncated = truncate_document_text("abc", max_chars=10)
    assert truncated is False
    assert same == "abc"


def test_build_prompt_text_uses_caption():
    assert build_prompt_text("  summarize  ") == "summarize"


def test_build_prompt_text_default_without_caption():
    assert "документ" in build_prompt_text(None).lower()


def test_build_document_prompt_wraps_attachment():
    prompt = build_document_prompt(
        caption="Что в договоре?",
        filename="contract.pdf",
        text="Clause 1",
    )
    assert "--- Вложение: contract.pdf ---" in prompt
    assert "Clause 1" in prompt
    assert "Что в договоре?" in prompt
