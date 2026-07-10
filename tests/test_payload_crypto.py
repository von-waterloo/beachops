"""AES-GCM payload encryption."""

import base64

import pytest

pytest.importorskip("cryptography")

from beachops.services.payload_crypto import PayloadCrypto, PayloadCryptoError


def _crypto() -> PayloadCrypto:
    key = base64.urlsafe_b64encode(bytes(range(32))).decode("ascii")
    return PayloadCrypto.from_encoded_key(key)


def test_crypto_roundtrip_and_random_nonce() -> None:
    crypto = _crypto()
    payload = {"token": "not-logged", "unicode": "пляж"}

    first = crypto.encrypt_json(payload)
    second = crypto.encrypt_json(payload)

    assert first != second
    assert "not-logged" not in first
    assert crypto.decrypt_json(first) == payload


def test_crypto_rejects_tampering() -> None:
    crypto = _crypto()
    token = crypto.encrypt(b"payload")
    replacement = "A" if token[-1] != "A" else "B"

    with pytest.raises(PayloadCryptoError):
        crypto.decrypt(token[:-1] + replacement)


def test_crypto_rejects_wrong_key_size() -> None:
    encoded = base64.urlsafe_b64encode(b"too-short").decode("ascii")

    with pytest.raises(PayloadCryptoError):
        PayloadCrypto.from_encoded_key(encoded)

