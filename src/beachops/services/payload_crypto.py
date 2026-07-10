"""Authenticated encryption for persisted control-plane payloads."""

from __future__ import annotations

import base64
import binascii
import json
import os
from collections.abc import Mapping
from typing import Any

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:  # pragma: no cover - exercised only in incomplete installations
    AESGCM = None  # type: ignore[assignment, misc]

_VERSION = "v1"
_NONCE_BYTES = 12
_DEFAULT_AAD = b"beachops:payload:v1"


class PayloadCryptoError(ValueError):
    """A deliberately non-sensitive encryption/decryption error."""


class PayloadCrypto:
    __slots__ = ("_cipher",)

    def __init__(self, key: bytes) -> None:
        if AESGCM is None:
            raise RuntimeError("cryptography is required for AES-GCM payload encryption")
        if len(key) != 32:
            raise PayloadCryptoError("DATA_ENCRYPTION_KEY must decode to exactly 32 bytes")
        self._cipher = AESGCM(key)

    def __repr__(self) -> str:
        return "PayloadCrypto(AES-256-GCM)"

    @classmethod
    def from_encoded_key(cls, encoded_key: str) -> PayloadCrypto:
        return cls(_decode_key(encoded_key))

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        variable: str = "DATA_ENCRYPTION_KEY",
    ) -> PayloadCrypto:
        source = os.environ if env is None else env
        encoded_key = source.get(variable, "")
        if not encoded_key:
            raise PayloadCryptoError(f"{variable} is required")
        return cls.from_encoded_key(encoded_key)

    def encrypt(self, plaintext: bytes, *, aad: bytes = _DEFAULT_AAD) -> str:
        nonce = os.urandom(_NONCE_BYTES)
        ciphertext = self._cipher.encrypt(nonce, plaintext, aad)
        token = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")
        return f"{_VERSION}:{token}"

    def decrypt(self, token: str, *, aad: bytes = _DEFAULT_AAD) -> bytes:
        try:
            version, encoded = token.split(":", 1)
            if version != _VERSION:
                raise PayloadCryptoError("unsupported encrypted payload version")
            packed = base64.urlsafe_b64decode(_add_padding(encoded))
            if len(packed) <= _NONCE_BYTES:
                raise PayloadCryptoError("invalid encrypted payload")
            return self._cipher.decrypt(
                packed[:_NONCE_BYTES],
                packed[_NONCE_BYTES:],
                aad,
            )
        except PayloadCryptoError:
            raise
        except (ValueError, binascii.Error) as exc:
            raise PayloadCryptoError("invalid encrypted payload") from exc
        except Exception as exc:
            raise PayloadCryptoError("encrypted payload authentication failed") from exc

    def encrypt_json(self, payload: Mapping[str, Any]) -> str:
        raw = json.dumps(
            payload,
            separators=(",", ":"),
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
        return self.encrypt(raw)

    def decrypt_json(self, token: str) -> dict[str, Any]:
        try:
            value = json.loads(self.decrypt(token).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PayloadCryptoError("decrypted payload is not valid JSON") from exc
        if not isinstance(value, dict):
            raise PayloadCryptoError("decrypted payload must be a JSON object")
        return value


def _decode_key(encoded_key: str) -> bytes:
    value = encoded_key.strip()
    if not value:
        raise PayloadCryptoError("DATA_ENCRYPTION_KEY is required")
    if len(value) == 64:
        try:
            return bytes.fromhex(value)
        except ValueError:
            pass
    try:
        return base64.urlsafe_b64decode(_add_padding(value))
    except (ValueError, binascii.Error) as exc:
        raise PayloadCryptoError("DATA_ENCRYPTION_KEY must be base64url or hex") from exc


def _add_padding(value: str) -> str:
    return value + ("=" * (-len(value) % 4))

