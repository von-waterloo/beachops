# BeachOps docs

Telegram + voice Mini App control plane for Cursor Cloud Agents: ask / plan / do,
agent slots, approvals, durable jobs, optional self-improve (`dev` → CI → prod).

## Contents

| Doc | Audience | What it covers |
|-----|----------|----------------|
| [Architecture](./ARCHITECTURE.md) | developers | stack, run pipeline, modules, DB |
| [User guide](./USER_GUIDE.md) | operators | Telegram commands, modes, scenarios |
| [Development](./DEVELOPMENT.md) | developers | local run, layout, tests |
| [Operations](./OPERATIONS.md) | DevOps | Docker, deploy, backups, migrate |
| [Ops MCP](./OPS_MCP.md) | DevOps / owners | SSH/docker logs MCP for cloud agents |
| [Self-deploy / CI](./SELF_DEPLOY.md) | DevOps / owner | main/dev → CI → auto-deploy; rollback |
| [Configuration](./CONFIGURATION.md) | everyone | environment variables, roles |
| [Threat model](./THREAT_MODEL.md) | security/ops | trust boundaries, controls |

## Quick start

1. Copy `.env.example` → `.env` and fill in keys.
2. Connect GitHub in the [Cursor Dashboard](https://cursor.com/dashboard).
3. Create an API key under [Integrations](https://cursor.com/dashboard/integrations).
4. Start compose; `migrate` applies schema, then bot/worker/API/webapp.
   Details: [CONFIGURATION.md](./CONFIGURATION.md).

Deploy your own copy: [OPERATIONS.md](./OPERATIONS.md) and the root
[README.md](../README.md). Maintainer CI on a self-hosted runner:
[SELF_DEPLOY.md](./SELF_DEPLOY.md) (not required for third-party installs).

Optional SSH/docker log tools for agents: [OPS_MCP.md](./OPS_MCP.md).
