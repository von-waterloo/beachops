"""Web / payload image helpers."""

from __future__ import annotations

import base64

import pytest

from beachops.services.telegram_images import (
    WebImageError,
    decode_payload_images,
    encode_images_for_payload,
)
from beachops.web.schemas import PromptRequest


def _png_b64() -> str:
    # 1x1 PNG
    raw = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    return base64.b64encode(raw).decode("ascii")


def test_encode_and_decode_roundtrip() -> None:
    encoded = encode_images_for_payload(
        [{"mimeType": "image/png", "data": _png_b64()}]
    )
    assert len(encoded) == 1
    assert encoded[0]["mime"] == "image/png"
    images = decode_payload_images(encoded)
    assert len(images) == 1


def test_encode_accepts_data_url() -> None:
    encoded = encode_images_for_payload(
        [{"mimeType": "image/png", "data": f"data:image/png;base64,{_png_b64()}"}]
    )
    assert encoded[0]["mime"] == "image/png"


def test_encode_rejects_svg() -> None:
    with pytest.raises(WebImageError, match="PNG"):
        encode_images_for_payload([{"mimeType": "image/svg+xml", "data": _png_b64()}])


def test_prompt_request_defaults_text_when_images() -> None:
    body = PromptRequest(
        prompt="",
        images=[{"mimeType": "image/png", "data": _png_b64()}],
    )
    assert "скриншот" in body.resolved_prompt().lower()


def test_prompt_request_empty_without_images() -> None:
    body = PromptRequest(prompt="  ")
    assert body.resolved_prompt() == ""
