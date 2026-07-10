"""Outbound Windows worker for BeachOps local Cursor agents."""

from __future__ import annotations

__all__ = ["run_daemon"]


def __getattr__(name: str):
    if name == "run_daemon":
        from beachops.windows_worker.daemon import run_daemon

        return run_daemon
    raise AttributeError(name)
