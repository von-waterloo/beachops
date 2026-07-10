"""Redact secrets before text or metadata crosses a trust boundary."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import PurePath
from typing import Any

REDACTED = "[REDACTED]"

_SENSITIVE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "credentials.json",
    "secrets.json",
    "id_rsa",
    "id_ed25519",
    "known_hosts",
    "netrc",
    ".netrc",
}
_SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".ppk")
_SENSITIVE_PARTS = {".aws", ".ssh", ".gnupg"}

_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----",
    re.DOTALL,
)
_BEARER_RE = re.compile(r"(?i)(\b(?:authorization\s*:\s*)?bearer\s+)[^\s,;]+")
_ASSIGNMENT_RE = re.compile(
    r"""(?ix)
    (
      ["']?
      (?:api[_-]?key|token|secret|password|passwd|private[_-]?key|
         client[_-]?secret|access[_-]?key|github[_-]?token)
      ["']?
      \s*(?:=|:)\s*
    )
    (["']?)([^"'\s,;}]+)\2
    """
)
_KNOWN_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    r"gh[pousr]_[A-Za-z0-9_]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|"
    r"sk-[A-Za-z0-9_-]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{10,}"
    r")"
)
_URL_PASSWORD_RE = re.compile(
    r"(?i)\b([a-z][a-z0-9+.-]*://[^/\s:@]+:)([^@\s/]+)(@)"
)


def is_sensitive_path(path: str | PurePath) -> bool:
    normalized = str(path).replace("\\", "/")
    parts = tuple(part.lower() for part in PurePath(normalized).parts)
    name = parts[-1] if parts else ""
    if name in _SENSITIVE_NAMES or name.startswith(".env."):
        return True
    return any(name.endswith(suffix) for suffix in _SENSITIVE_SUFFIXES) or any(
        part in _SENSITIVE_PARTS for part in parts
    )


def redact_text(value: str) -> str:
    redacted = _PRIVATE_KEY_RE.sub(REDACTED, value)
    redacted = _BEARER_RE.sub(rf"\1{REDACTED}", redacted)
    redacted = _ASSIGNMENT_RE.sub(rf"\1{REDACTED}", redacted)
    redacted = _KNOWN_TOKEN_RE.sub(REDACTED, redacted)
    return _URL_PASSWORD_RE.sub(rf"\1{REDACTED}\3", redacted)


def redact_file_content(path: str | PurePath, content: str) -> str:
    if is_sensitive_path(path):
        return REDACTED
    return redact_text(content)


def redact_value(value: Any) -> Any:
    """Recursively redact log-safe metadata without mutating the input."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {
            key: (
                REDACTED
                if _is_sensitive_key(str(key))
                else redact_value(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [redact_value(item) for item in value]
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(
        marker in normalized
        for marker in ("token", "secret", "password", "passwd", "api_key", "private_key")
    )

