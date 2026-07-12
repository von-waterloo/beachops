"""Minimal Streamable-HTTP MCP server for BeachOps ops tools."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from beachops.app_context import AppContext
from beachops.services.ops_ssh import OpsSshError, OpsSshService, parse_ops_ssh_hosts

logger = logging.getLogger(__name__)

router = APIRouter(tags=["mcp"])
MCP_PROTOCOL_VERSION = "2024-11-05"

TOOLS = [
    {
        "name": "ssh_exec",
        "description": (
            "Run a shell command on an allowlisted host alias from OPS_SSH_HOSTS. "
            "Typical aliases: eu (BeachOps), mt-dev (AI-ContentMaker DEV), "
            "ru (AI-ContentMaker PROD)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": "Host alias: eu | mt-dev | ru (see OPS_SSH_HOSTS).",
                },
                "command": {"type": "string", "description": "Shell command to run."},
            },
            "required": ["host", "command"],
        },
    },
    {
        "name": "docker_ps",
        "description": (
            "List Docker containers on an allowlisted host. "
            "Use eu for BeachOps, mt-dev for AI-ContentMaker DEV "
            "(mt_*_dev), ru for AI-ContentMaker PROD (ai-contentmaker-*)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": "Host alias: eu | mt-dev | ru.",
                },
            },
            "required": ["host"],
        },
    },
    {
        "name": "docker_logs",
        "description": (
            "Fetch recent Docker logs. Prefer docker_ps first for exact names. "
            "DEV examples: mt_backend_dev, mt_worker_dev. "
            "PROD examples: ai-contentmaker-backend-1, ai-contentmaker-worker-1."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": "Host alias: eu | mt-dev | ru.",
                },
                "container": {"type": "string"},
                "tail": {"type": "integer", "default": 100},
            },
            "required": ["host", "container"],
        },
    },
]


def _context(request: Request) -> AppContext:
    return request.app.state.context


def _ops(context: AppContext) -> OpsSshService:
    return OpsSshService(
        hosts=parse_ops_ssh_hosts(context.settings.ops_ssh_hosts),
        key_path=context.settings.ops_ssh_key_path,
        timeout_sec=context.settings.ops_ssh_timeout_sec,
        max_output_chars=context.settings.ops_ssh_max_output_chars,
    )


async def _require_mcp_auth(
    request: Request,
    authorization: str | None = Header(default=None),
) -> AppContext:
    context = getattr(request.app.state, "context", None)
    if context is None:
        raise HTTPException(status_code=503, detail="app not ready")
    if not context.settings.mcp_enabled:
        raise HTTPException(status_code=404, detail="MCP disabled")
    expected = (context.settings.mcp_bearer_token or "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="MCP token not configured")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="bearer token required")
    token = authorization.split(" ", 1)[1].strip()
    if token != expected:
        raise HTTPException(status_code=401, detail="invalid token")
    return context


def _rpc_result(req_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _rpc_error(req_id: Any, code: int, message: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": code, "message": message},
    }


async def _call_tool(ops: OpsSshService, name: str, arguments: dict[str, Any]) -> str:
    if name == "ssh_exec":
        return await ops.ssh_exec(str(arguments.get("host") or ""), str(arguments.get("command") or ""))
    if name == "docker_ps":
        return await ops.docker_ps(str(arguments.get("host") or ""))
    if name == "docker_logs":
        return await ops.docker_logs(
            str(arguments.get("host") or ""),
            str(arguments.get("container") or ""),
            tail=int(arguments.get("tail") or 100),
        )
    raise OpsSshError(f"unknown tool: {name}")


@router.post("/mcp")
@router.post("/api/mcp")
async def mcp_rpc(
    request: Request,
    context: AppContext = Depends(_require_mcp_auth),
) -> Response:
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid JSON") from exc

    if isinstance(body, list):
        # Batch not needed for agents; reject clearly.
        return JSONResponse(_rpc_error(None, -32600, "batch not supported"), status_code=400)
    if not isinstance(body, dict):
        return JSONResponse(_rpc_error(None, -32600, "invalid request"), status_code=400)

    req_id = body.get("id")
    method = str(body.get("method") or "")
    params = body.get("params") or {}
    ops = _ops(context)

    if method == "initialize":
        return JSONResponse(
            _rpc_result(
                req_id,
                {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "beachops-ops", "version": "1.0.0"},
                },
            )
        )
    if method == "notifications/initialized":
        return Response(status_code=202)
    if method == "ping":
        return JSONResponse(_rpc_result(req_id, {}))
    if method == "tools/list":
        return JSONResponse(_rpc_result(req_id, {"tools": TOOLS}))
    if method == "tools/call":
        name = str(params.get("name") or "")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {}
        try:
            text = await _call_tool(ops, name, arguments)
            await context.audit.append(
                actor_id=None,
                event_type="mcp.tool",
                action=name,
                outcome="ok",
                details={"host": arguments.get("host")},
            )
            return JSONResponse(
                _rpc_result(
                    req_id,
                    {"content": [{"type": "text", "text": text}], "isError": False},
                )
            )
        except OpsSshError as exc:
            return JSONResponse(
                _rpc_result(
                    req_id,
                    {
                        "content": [{"type": "text", "text": exc.message}],
                        "isError": True,
                    },
                )
            )
        except Exception:
            logger.exception("MCP tool failed: %s", name)
            return JSONResponse(_rpc_error(req_id, -32000, "tool failed"))

    if method.startswith("notifications/"):
        return Response(status_code=202)

    return JSONResponse(_rpc_error(req_id, -32601, f"method not found: {method}"))


@router.get("/mcp")
@router.get("/api/mcp")
async def mcp_stream(
    context: AppContext = Depends(_require_mcp_auth),
) -> Response:
    del context
    # This server is intentionally stateless and returns each JSON-RPC response
    # on POST. Streamable HTTP requires a server without a standalone SSE
    # stream to reject GET instead of returning an application/json probe.
    return Response(status_code=405, headers={"Allow": "POST"})


@router.get("/mcp/status")
@router.get("/api/mcp/status")
async def mcp_status(
    context: AppContext = Depends(_require_mcp_auth),
) -> dict:
    ops = _ops(context)
    return {
        "name": "beachops-ops",
        "enabled": True,
        "hosts": ops.list_aliases(),
        "tools": [t["name"] for t in TOOLS],
    }
