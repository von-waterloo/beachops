"""Telegram Mini App open URLs with optional cache-bust version."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def webapp_open_url(base_url: str, *, version: str | None = None) -> str:
    """Return HTTPS Mini App URL; append ?v= when version is set."""
    raw = (base_url or "").strip()
    if not raw:
        return ""
    ver = (version or "").strip()
    if not ver:
        return raw
    parts = urlsplit(raw)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["v"] = ver
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )
