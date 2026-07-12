"""Owner-server SSH helpers for BeachOps MCP tools.

Keys stay on the BeachOps host; cloud agents never see private keys.
"""

from __future__ import annotations

import asyncio
import logging
import shlex
from dataclasses import dataclass
from pathlib import Path

from beachops.services.redaction import redact_text

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SshHost:
    alias: str
    user: str
    host: str
    port: int = 22
    # Optional jump host alias (e.g. ru via eu when direct path is firewalled).
    via: str | None = None


def parse_ops_ssh_hosts(raw: str) -> dict[str, SshHost]:
    """Parse ``alias=user@host:port`` allowlist.

    Optional jump: ``alias=user@host:port/via=otheralias`` (ProxyCommand via
    the other allowlisted host). Example for RU behind a reverse tunnel on EU::

        eu=const@185.244.49.94,ru=root@127.0.0.1:2222/via=eu
    """
    hosts: dict[str, SshHost] = {}
    for chunk in (raw or "").split(","):
        item = chunk.strip()
        if not item or "=" not in item:
            continue
        alias, target = item.split("=", 1)
        alias = alias.strip().lower()
        target = target.strip()
        if not alias or "@" not in target:
            continue
        via: str | None = None
        if "/via=" in target:
            target, via_raw = target.rsplit("/via=", 1)
            via = via_raw.strip().lower() or None
            target = target.strip()
        user, hostport = target.split("@", 1)
        host = hostport
        port = 22
        if ":" in hostport:
            host, port_s = hostport.rsplit(":", 1)
            try:
                port = int(port_s)
            except ValueError:
                continue
        if user and host:
            hosts[alias] = SshHost(
                alias=alias, user=user, host=host, port=port, via=via
            )
    return hosts


class OpsSshError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class OpsSshService:
    def __init__(
        self,
        *,
        hosts: dict[str, SshHost],
        key_path: str,
        timeout_sec: int = 30,
        max_output_chars: int = 12_000,
    ) -> None:
        self._hosts = hosts
        self._key_path = (key_path or "").strip()
        self._timeout_sec = timeout_sec
        self._max_output_chars = max_output_chars

    @property
    def enabled(self) -> bool:
        return bool(self._hosts and self._key_path and Path(self._key_path).is_file())

    def list_aliases(self) -> list[str]:
        return sorted(self._hosts)

    def _proxy_command(self, jump: SshHost) -> str:
        """OpenSSH ProxyCommand that dials %h:%p through ``jump``."""
        parts = [
            "ssh",
            "-i",
            self._key_path,
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-W",
            "%h:%p",
            "-p",
            str(jump.port),
            f"{jump.user}@{jump.host}",
        ]
        return " ".join(shlex.quote(p) for p in parts)

    async def ssh_exec(self, host_alias: str, command: str) -> str:
        alias = (host_alias or "").strip().lower()
        host = self._hosts.get(alias)
        if host is None:
            raise OpsSshError(
                f"unknown host alias '{host_alias}'; "
                f"allowed: {', '.join(self.list_aliases()) or 'none'}"
            )
        cmd = (command or "").strip()
        if not cmd:
            raise OpsSshError("command is required")
        if not self.enabled:
            raise OpsSshError("SSH ops not configured (OPS_SSH_HOSTS / OPS_SSH_KEY_PATH)")

        ssh_cmd = [
            "ssh",
            "-i",
            self._key_path,
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-p",
            str(host.port),
        ]
        if host.via:
            jump = self._hosts.get(host.via)
            if jump is None:
                raise OpsSshError(
                    f"jump host '{host.via}' for '{alias}' is not in OPS_SSH_HOSTS"
                )
            if jump.via:
                raise OpsSshError(f"nested jumps not supported ({alias} via {host.via})")
            ssh_cmd.extend(["-o", f"ProxyCommand={self._proxy_command(jump)}"])
        ssh_cmd.extend([f"{host.user}@{host.host}", cmd])
        return await self._run(ssh_cmd)

    async def docker_ps(self, host_alias: str) -> str:
        return await self.ssh_exec(
            host_alias, "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'"
        )

    async def docker_logs(
        self,
        host_alias: str,
        container: str,
        *,
        tail: int = 100,
    ) -> str:
        name = (container or "").strip()
        if not name or any(ch in name for ch in " \t\n;&|`$"):
            raise OpsSshError("invalid container name")
        n = max(1, min(int(tail or 100), 500))
        return await self.ssh_exec(
            host_alias,
            f"docker logs --tail {n} {shlex.quote(name)}",
        )

    async def _run(self, ssh_cmd: list[str]) -> str:
        try:
            proc = await asyncio.create_subprocess_exec(
                *ssh_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(),
                timeout=self._timeout_sec,
            )
        except TimeoutError as exc:
            raise OpsSshError(f"SSH timed out after {self._timeout_sec}s") from exc
        except FileNotFoundError as exc:
            raise OpsSshError("ssh binary not found on BeachOps host") from exc
        except Exception as exc:
            logger.exception("SSH exec failed")
            raise OpsSshError(str(exc)) from exc

        out = (stdout_b or b"").decode("utf-8", errors="replace")
        err = (stderr_b or b"").decode("utf-8", errors="replace")
        text = out
        if err.strip():
            text = f"{out}\n{err}".strip() if out.strip() else err
        text = redact_text(text)
        if len(text) > self._max_output_chars:
            text = text[: self._max_output_chars] + "\n…(truncated)"
        if proc.returncode not in (0, None):
            return f"exit={proc.returncode}\n{text}".strip()
        return text.strip() or "(empty)"
