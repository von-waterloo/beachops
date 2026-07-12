# BeachOps ops MCP (SSH / Docker logs)

Optional HTTP MCP server that lets **Cursor cloud agents** run allowlisted
SSH commands and read Docker logs on **your** hosts — without embedding
private keys in the agent VM or in git.

Default: **off**. Enable only if you understand the trust boundary.

## What you get

Tools exposed as MCP server `beachops-ops`:

| Tool | Purpose |
|------|---------|
| `ssh_exec` | Run a shell command on an allowlisted host alias |
| `docker_ps` | List containers on that host |
| `docker_logs` | Tail logs for one container name |

BeachOps keeps the SSH private key on the API host. Cloud agents only call
your public HTTPS MCP URL with a bearer token.

## Environment

See also [CONFIGURATION.md](./CONFIGURATION.md).

| Variable | Required | Notes |
|----------|----------|--------|
| `MCP_ENABLED` | yes (`true`) | Turns on `/mcp` and injects MCP into cloud runs |
| `MCP_PUBLIC_URL` | yes | Public HTTPS URL, usually `{WEBAPP_BASE_URL}/mcp` |
| `MCP_BEARER_TOKEN` | yes | Long random secret; sent as `Authorization: Bearer …` |
| `OPS_SSH_HOSTS` | yes | Allowlist of aliases (see below) |
| `OPS_SSH_KEY_PATH` | yes | Path **inside the api container** (default mount: `/run/beachops-ssh/id_ed25519`) |
| `OPS_SSH_KEY_HOST_PATH` | for compose overlay | Absolute path to the private key **on the Docker host** |
| `OPS_SSH_TIMEOUT_SEC` | no (`30`) | Per-command timeout |
| `OPS_SSH_MAX_OUTPUT_CHARS` | no (`12000`) | Truncate tool output |

## Host allowlist (`OPS_SSH_HOSTS`)

Format (comma-separated):

```text
alias=user@host[:port]
alias=user@host:port/via=otheralias
```

- `alias` — short name the agent passes as `host` (`eu`, `mt-dev`, `ru`, …)
- `/via=otheralias` — OpenSSH `ProxyCommand` jump through another allowlisted
  alias (useful when the API container cannot reach a reverse-tunnel port on
  the Docker host, but can SSH to `otheralias` on port 22)

### Suggested alias map (customize names/containers for your fleet)

| Alias | Typical use | Example containers |
|-------|-------------|--------------------|
| `eu` | BeachOps stack host | `tg-cursor-bot-bot-1`, `tg-cursor-bot-api-1`, … |
| `mt-dev` | App **dev** stack on the same (or another) host | e.g. `mt_backend_dev`, `mt_worker_dev`, `mt_frontend_dev` |
| `ru` | App **prod** host (often behind a jump/tunnel) | e.g. `…-backend-1`, `…-worker-1` |

Multiple aliases may point at the **same** SSH target when that clarifies
intent for the agent (BeachOps vs app-dev on one machine).

Do **not** put production IPs or usernames into public docs beyond placeholders.
Put real values only in your private `.env` / secret store.

## Compose overlay (public-repo safe)

Base `docker-compose.yml` does **not** mount an SSH key (so clones without ops
still start).

1. Generate a dedicated ed25519 key on the BeachOps host (not your laptop key).
2. Install the public key in `authorized_keys` on every allowlisted target.
3. Set in `.env`:

   ```env
   OPS_SSH_KEY_HOST_PATH=/absolute/path/to/beachops_ops_private_key
   OPS_SSH_KEY_PATH=/run/beachops-ssh/id_ed25519
   ```

4. Start with the overlay:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.ops.yml up -d
   ```

`docker-compose.ops.yml` binds `${OPS_SSH_KEY_HOST_PATH}` read-only into the
api container. Never commit the private key file.

CI/deploy for this project includes the overlay automatically when
`OPS_SSH_KEY_HOST_PATH` is set in the prod env secret.

## Reverse tunnels and jumps

If host A cannot open TCP to host B:22 (common across regions/providers), but
B can SSH to A:

1. On B, run a reverse tunnel, e.g. publish B’s sshd on A as `127.0.0.1:2222`.
2. Allowlist something like:
   `ru=root@127.0.0.1:2222/via=eu`
   so the api container SSHs to `eu` first, then to `127.0.0.1:2222` on that
   jump host.

Direct `host.docker.internal:2222` from the api container often fails (bridge
isolation); prefer `/via=` when that happens.

## Agent guidance

Prompts tell the cloud agent to use MCP `beachops-ops` for logs/SSH and which
alias matches BeachOps vs app-dev vs app-prod. Tool schemas list the same
aliases. MCP is attached to every cloud run when enabled — independent of
Cursor API key presets (`mt` / `mt2` / `mt3`).

## Security notes

- Treat `MCP_BEARER_TOKEN` like a root-adjacent credential.
- Keep `OPS_SSH_HOSTS` minimal; prefer a dedicated ops key with no interactive
  shell extras beyond what Docker/ops need.
- Redaction still runs on tool output, but never print secrets into Telegram
  on purpose.
- Public repo: document patterns and placeholders only; live IPs/keys stay in
  private env / host files.

## Smoke test

```bash
TOKEN=…  # MCP_BEARER_TOKEN
curl -sS -H "Authorization: Bearer $TOKEN" "$MCP_PUBLIC_URL"
# expect JSON listing enabled tools and host aliases

curl -sS -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"docker_ps","arguments":{"host":"mt-dev"}}}' \
  "$MCP_PUBLIC_URL"
```
