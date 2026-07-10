# Threat model BeachOps

## Assets

- private repository code and PR diffs;
- Telegram/Cursor/OpenAI/GitHub credentials;
- encrypted job payloads and audit trail;
- production host and PostgreSQL data.

## Trust boundaries

- Telegram update and Mini App `initData` are untrusted until server validation;
- browser Passkey assertions are untrusted until WebAuthn challenge, RP ID, origin,
  user verification, signature and sign counter checks pass;
- Cursor/OpenAI/GitHub outputs are untrusted and pass redaction/policy;
- browser receives no provider keys;
- browser sessions use opaque Redis-backed tokens in `Secure`, `HttpOnly`,
  `SameSite=Strict` cookies; unsafe HTTP methods and WebSocket additionally require
  the configured origin;
- Redis contains dispatch metadata, not plaintext job prompts;
- PostgreSQL payloads use AES-256-GCM; key exists only in environment.

## Enforced controls

- private-chat-only and explicit viewer/operator/owner allowlists;
- repository URL must be exact GitHub HTTPS; empty policy is open mode,
  non-empty policy is an allowlist; writes to `main`/`master` are blocked;
- `/do` works on the selected base branch (`work_on_current_branch`) except
  when the base is `main`/`master` (isolated branch + PR);
- no merge, deploy, force-push, branch deletion, production DB, secrets or IAM
  operations from the control plane;
- opaque callback digest, actor/action binding, TTL and atomic consume;
- Redis rate limits/idempotency and one active run per actor;
- output redaction before Telegram, memory, audit, API, GitHub diff and TTS;
- append-only database audit trigger;
- `/panic` cancels durable/active work and blocks new writes; `/unpanic`
  requires a separate one-time owner callback.

## Residual risks

- Cursor Cloud Agent may use repository-local shell tools internally; BeachOps
  never provides a raw-shell endpoint or production credentials.
- Full Mini App operation requires HTTPS. Until `WEBAPP_BASE_URL` is configured,
  `/dashboard` remains disabled.
- Passkey enrollment is owner-only and requires a fresh signed Telegram Mini App
  session; there is no public password/bootstrap endpoint.
- Telegram polling bot is intentionally single-instance; worker/API may scale,
  but distributed tests are required before increasing worker count.
- Existing legacy media queue is in-process; write mode is never allowed there.

## Incident response

1. Owner runs `/panic`.
2. Verify `system_state.panic.enabled=true`, ARQ queue and Cursor run cancellation.
3. Rotate affected external key in its provider; update server `.env`.
4. Review append-only `audit_events` and redacted container logs.
5. Restore DB from the pre-deploy dump if schema/data integrity is affected.
6. Use `/unpanic` only after root cause and policy are corrected.
