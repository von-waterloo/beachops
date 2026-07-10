"""Passkey enrollment, login, and opaque browser sessions."""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Header, HTTPException, Request, Response, WebSocket
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from beachops.app_context import AppContext
from beachops.domain.security import Role
from beachops.web.telegram_auth import (
    TelegramInitDataError,
    TelegramPrincipal,
    extract_tma_authorization,
    validate_init_data,
)

SESSION_COOKIE = "__Host-beachops_session"
_CHALLENGE_PREFIX = "beachops:webauthn:challenge:"
_SESSION_PREFIX = "beachops:web-session:"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/passkeys/register/options")
async def registration_options(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    context = _context(request)
    principal = _require_owner_tma(context, authorization)
    rp_id, _ = _rp_config(context)
    existing = await context.passkeys.list_for_user(principal.user_id)
    challenge = secrets.token_bytes(32)
    challenge_id = await _store_challenge(
        context,
        kind="register",
        challenge=challenge,
        user_id=principal.user_id,
    )
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name="BeachOps",
        user_id=str(principal.user_id).encode("ascii"),
        user_name=principal.username or f"telegram-{principal.user_id}",
        user_display_name=principal.username or "BeachOps owner",
        challenge=challenge,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            require_resident_key=True,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=bytes(item["credential_id"]))
            for item in existing
        ],
    )
    return {
        "challengeId": challenge_id,
        "options": json.loads(options_to_json(options)),
    }


@router.post("/passkeys/register/verify")
async def registration_verify(
    body: dict,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    context = _context(request)
    principal = _require_owner_tma(context, authorization)
    challenge = await _consume_challenge(
        context,
        challenge_id=str(body.get("challengeId") or ""),
        kind="register",
        user_id=principal.user_id,
    )
    credential = body.get("credential")
    if not isinstance(credential, dict):
        raise HTTPException(status_code=400, detail="credential required")
    rp_id, origin = _rp_config(context)
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            require_user_verification=True,
        )
    except (WebAuthnException, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="passkey verification failed") from exc

    transports = credential.get("response", {}).get("transports", [])
    if not isinstance(transports, list):
        transports = []
    label = str(body.get("label") or "Passkey").strip()[:80] or "Passkey"
    await context.passkeys.create(
        credential_id=verified.credential_id,
        user_id=principal.user_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        device_type=verified.credential_device_type.value,
        backed_up=verified.credential_backed_up,
        transports=[str(item) for item in transports],
        label=label,
    )
    await context.audit.append(
        actor_id=principal.user_id,
        event_type="auth.passkey_registered",
        action="register",
        outcome="success",
        details={
            "credentialId": bytes_to_base64url(verified.credential_id)[:16],
            "deviceType": verified.credential_device_type.value,
            "backedUp": verified.credential_backed_up,
        },
    )
    return {"registered": True}


@router.post("/passkeys/login/options")
async def authentication_options(request: Request) -> dict:
    context = _context(request)
    await _check_public_rate_limit(context, request, "passkey_options", limit=10)
    rp_id, _ = _rp_config(context)
    challenge = secrets.token_bytes(32)
    challenge_id = await _store_challenge(
        context,
        kind="authenticate",
        challenge=challenge,
    )
    options = generate_authentication_options(
        rp_id=rp_id,
        challenge=challenge,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    return {
        "challengeId": challenge_id,
        "options": json.loads(options_to_json(options)),
    }


@router.post("/passkeys/login/verify")
async def authentication_verify(
    body: dict,
    request: Request,
    response: Response,
) -> dict:
    context = _context(request)
    await _check_public_rate_limit(context, request, "passkey_verify", limit=10)
    challenge = await _consume_challenge(
        context,
        challenge_id=str(body.get("challengeId") or ""),
        kind="authenticate",
    )
    credential = body.get("credential")
    if not isinstance(credential, dict):
        raise HTTPException(status_code=400, detail="credential required")
    try:
        credential_id = base64url_to_bytes(str(credential.get("id") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid credential") from exc
    stored = await context.passkeys.get(credential_id)
    if stored is None:
        raise HTTPException(status_code=401, detail="unknown passkey")
    user_id = int(stored["user_id"])
    if context.settings.role_for(user_id) != Role.OWNER:
        raise HTTPException(status_code=403, detail="owner role required")

    rp_id, origin = _rp_config(context)
    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=bytes(stored["public_key"]),
            credential_current_sign_count=int(stored["sign_count"]),
            require_user_verification=True,
        )
    except (WebAuthnException, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="passkey verification failed") from exc

    await context.passkeys.mark_used(
        verified.credential_id,
        sign_count=verified.new_sign_count,
        device_type=verified.credential_device_type.value,
        backed_up=verified.credential_backed_up,
    )
    token = secrets.token_urlsafe(32)
    await context.redis.set(
        _session_key(token),
        str(user_id).encode("ascii"),
        ex=context.settings.web_session_ttl_sec,
    )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=context.settings.web_session_ttl_sec,
        secure=True,
        httponly=True,
        samesite="strict",
        path="/",
    )
    await context.audit.append(
        actor_id=user_id,
        event_type="auth.passkey_login",
        action="login",
        outcome="success",
        details={"deviceType": verified.credential_device_type.value},
    )
    return {"authenticated": True}


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response) -> Response:
    context = _context(request)
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await context.redis.delete(_session_key(token))
    response.delete_cookie(
        SESSION_COOKIE,
        secure=True,
        httponly=True,
        samesite="strict",
        path="/",
    )
    return response


async def resolve_request_principal(
    request: Request,
    authorization: str | None,
) -> TelegramPrincipal:
    context = _context(request)
    if authorization and authorization.lower().startswith("tma "):
        return _validate_tma(context, authorization)
    principal = await _session_principal(
        context,
        request.cookies.get(SESSION_COOKIE),
    )
    if request.method.upper() not in _SAFE_METHODS:
        _, origin = _rp_config(context)
        if request.headers.get("origin") != origin:
            raise TelegramInitDataError("invalid request origin")
    return principal


async def resolve_websocket_principal(
    websocket: WebSocket,
    authorization: str | None,
) -> TelegramPrincipal:
    context: AppContext = websocket.app.state.context
    if authorization and authorization.lower().startswith("tma "):
        return _validate_tma(context, authorization)
    _, origin = _rp_config(context)
    if websocket.headers.get("origin") != origin:
        raise TelegramInitDataError("invalid websocket origin")
    return await _session_principal(
        context,
        websocket.cookies.get(SESSION_COOKIE),
    )


def _require_owner_tma(
    context: AppContext,
    authorization: str | None,
) -> TelegramPrincipal:
    try:
        principal = _validate_tma(context, authorization)
    except TelegramInitDataError as exc:
        raise HTTPException(status_code=401, detail="Telegram owner session required") from exc
    if context.settings.role_for(principal.user_id) != Role.OWNER:
        raise HTTPException(status_code=403, detail="owner role required")
    return principal


def _validate_tma(
    context: AppContext,
    authorization: str | None,
) -> TelegramPrincipal:
    raw = extract_tma_authorization(authorization)
    principal = validate_init_data(
        raw,
        context.settings.tg_bot_token,
        max_age_sec=context.settings.web_auth_max_age_sec,
    )
    if context.settings.role_for(principal.user_id) is None:
        raise TelegramInitDataError("user is not allowlisted")
    return principal


async def _session_principal(
    context: AppContext,
    token: str | None,
) -> TelegramPrincipal:
    if not token:
        raise TelegramInitDataError("missing browser session")
    raw_user_id = await context.redis.get(_session_key(token))
    if not raw_user_id:
        raise TelegramInitDataError("expired browser session")
    try:
        user_id = int(raw_user_id)
    except (TypeError, ValueError) as exc:
        raise TelegramInitDataError("invalid browser session") from exc
    if context.settings.role_for(user_id) != Role.OWNER:
        raise TelegramInitDataError("browser session is not owner")
    return TelegramPrincipal(
        user_id=user_id,
        username=None,
        auth_date=int(time.time()),
        query_id=None,
        auth_method="passkey",
    )


async def _store_challenge(
    context: AppContext,
    *,
    kind: str,
    challenge: bytes,
    user_id: int | None = None,
) -> str:
    challenge_id = secrets.token_urlsafe(24)
    payload = {
        "kind": kind,
        "challenge": bytes_to_base64url(challenge),
        "userId": user_id,
    }
    await context.redis.set(
        f"{_CHALLENGE_PREFIX}{challenge_id}",
        json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        ex=context.settings.web_auth_challenge_ttl_sec,
    )
    return challenge_id


async def _consume_challenge(
    context: AppContext,
    *,
    challenge_id: str,
    kind: str,
    user_id: int | None = None,
) -> bytes:
    if not challenge_id or len(challenge_id) > 128:
        raise HTTPException(status_code=400, detail="invalid challenge")
    raw = await context.redis.getdel(f"{_CHALLENGE_PREFIX}{challenge_id}")
    if not raw:
        raise HTTPException(status_code=400, detail="challenge expired")
    try:
        payload = json.loads(raw)
        if payload.get("kind") != kind or payload.get("userId") != user_id:
            raise ValueError("challenge binding mismatch")
        return base64url_to_bytes(str(payload["challenge"]))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="invalid challenge") from exc


async def _check_public_rate_limit(
    context: AppContext,
    request: Request,
    action: str,
    *,
    limit: int,
) -> None:
    subject = request.client.host if request.client else "unknown"
    result = await context.rate_limiter.check(
        subject=subject,
        action=action,
        limit=limit,
        window_sec=60,
    )
    if not result.allowed:
        raise HTTPException(status_code=429, detail="too many authentication attempts")


def _session_key(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"{_SESSION_PREFIX}{digest}"


def _rp_config(context: AppContext) -> tuple[str, str]:
    parsed = urlsplit(context.settings.webapp_base_url.strip())
    if not parsed.hostname or not parsed.scheme:
        raise HTTPException(status_code=503, detail="WebAuthn origin is not configured")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise HTTPException(status_code=503, detail="WebAuthn requires HTTPS")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return parsed.hostname, origin


def _context(request: Request) -> AppContext:
    return request.app.state.context
