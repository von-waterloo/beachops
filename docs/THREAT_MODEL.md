# Threat model BeachOps

## Assets

- private repository code and PR diffs;
- Telegram/Cursor/OpenAI/GitHub credentials;
- encrypted job payloads and audit trail;
- production host and PostgreSQL data.

## Trust boundaries

- Telegram update and Mini App `initData` are untrusted until server validation;
- Telegram Login Widget payloads are untrusted until HMAC (SHA256 bot token) and
  `auth_date` checks pass;
- legacy browser Passkey assertions remain untrusted until WebAuthn challenge, RP ID,
  origin, user verification, signature and sign counter checks pass;
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
- **exception, opt-in only:** `AGENT_SSH_*` (see `docs/CONFIGURATION.md`) — when an
  operator explicitly configures a host/user/key, the Cursor cloud agent receives
  that SSH private key via `CloudAgentOptions.env_vars` and is instructed
  (`domain/prompts.server_ssh_block`) to use it for read-only `docker
  ps/logs/inspect/stats` diagnostics only. Unset by default; the operator who enables
  it accepts the residual risk below instead of the "never provides production
  credentials" guarantee;
- opaque callback digest, actor/action binding, TTL and atomic consume;
- Redis rate limits/idempotency and one active run per actor;
- output redaction before Telegram, memory, audit, API, GitHub diff and TTS;
- append-only database audit trigger;
- `/cancel` stops active runs; owner `/rollback` for prod SHA recovery.

## Residual risks

- Cursor Cloud Agent may use repository-local shell tools internally; BeachOps
  never provides a raw-shell endpoint or production credentials **unless
  `AGENT_SSH_*` is explicitly configured** (see above) — in that case the agent
  holds a live SSH key for the run's duration. The prompt-level restriction to
  read-only docker commands is a soft instruction to the LLM, not a technical
  control: a sufficiently crafted prompt (including injected content from a
  repo, forwarded message or photo) could get the agent to run other commands
  over that SSH session. Mitigate by using a dedicated, non-sudo, ideally
  forced-command-restricted key/user — never the operator's own admin key.
- Full Mini App operation requires HTTPS. Until `WEBAPP_BASE_URL` is configured,
  `/dashboard` remains disabled.
- Browser login uses Telegram Login Widget (or Mini App session mint); there is no
  public password endpoint. Domain must be registered in BotFather `/setdomain`.
- Legacy Passkey enrollment remains owner-only behind TMA session.
- Telegram polling bot is intentionally single-instance; worker/API may scale,
  but distributed tests are required before increasing worker count.
- Existing legacy media queue is in-process; write mode is never allowed there.

## Incident response

1. Owner runs `/cancel` for active actors and reviews `/jobs` / `/approvals`.
2. Rotate affected external key in its provider; update server `.env`.
3. Review append-only `audit_events` and redacted container logs.
4. Restore DB from the pre-deploy dump if schema/data integrity is affected.
5. Use `/rollback` only after root cause is understood and a safe SHA is chosen.
