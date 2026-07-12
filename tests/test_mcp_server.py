from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from beachops.services.cursor_agent import CursorAgentService
from beachops.web.mcp_server import MCP_PROTOCOL_VERSION, router


def _client() -> TestClient:
    app = FastAPI()
    app.state.context = SimpleNamespace(
        settings=SimpleNamespace(
            mcp_enabled=True,
            mcp_bearer_token="test-token",
            ops_ssh_hosts="eu=const@example.test",
            ops_ssh_key_path="/missing/test-key",
            ops_ssh_timeout_sec=30,
            ops_ssh_max_output_chars=12_000,
        )
    )
    app.include_router(router)
    return TestClient(app)


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


def test_cursor_agent_builds_rest_api_mcp_server_shape() -> None:
    service = CursorAgentService(
        api_key="cursor-key",
        model="auto",
        workspace=Path("."),
        mcp_enabled=True,
        mcp_public_url="https://ops.example.test/mcp",
        mcp_bearer_token="mcp-token",
    )

    assert service._mcp_servers() == [  # pylint: disable=protected-access
        {
            "name": "beachops-ops",
            "type": "http",
            "url": "https://ops.example.test/mcp",
            "headers": {"Authorization": "Bearer mcp-token"},
        }
    ]


def test_mcp_initialize_and_list_tools() -> None:
    with _client() as client:
        initialized = client.post(
            "/mcp",
            headers={
                **_headers(),
                "Accept": "application/json, text/event-stream",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
        )
        tools = client.post(
            "/mcp",
            headers=_headers(),
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )

    assert initialized.status_code == 200
    assert initialized.json()["result"]["protocolVersion"] == MCP_PROTOCOL_VERSION
    assert tools.status_code == 200
    assert [tool["name"] for tool in tools.json()["result"]["tools"]] == [
        "ssh_exec",
        "docker_ps",
        "docker_logs",
    ]


def test_mcp_get_rejects_unsupported_standalone_sse_stream() -> None:
    with _client() as client:
        response = client.get(
            "/mcp",
            headers={**_headers(), "Accept": "text/event-stream"},
        )

    assert response.status_code == 405
    assert response.headers["allow"] == "POST"
    assert response.content == b""


def test_mcp_notifications_return_empty_accepted_response() -> None:
    with _client() as client:
        response = client.post(
            "/mcp",
            headers=_headers(),
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )

    assert response.status_code == 202
    assert response.content == b""


def test_mcp_status_uses_separate_diagnostic_route() -> None:
    with _client() as client:
        response = client.get("/mcp/status", headers=_headers())

    assert response.status_code == 200
    assert response.json() == {
        "name": "beachops-ops",
        "enabled": True,
        "hosts": ["eu"],
        "tools": ["ssh_exec", "docker_ps", "docker_logs"],
    }
