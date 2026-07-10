"""Entry point: ``python -m beachops.windows_worker``."""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from beachops.services.logging_config import configure_logging
from beachops.windows_worker.daemon import run_daemon


def main() -> None:
    configure_logging(os.getenv("LOG_LEVEL", "INFO"), service="windows-worker")
    try:
        asyncio.run(run_daemon())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Stopped by user")
        sys.exit(0)


if __name__ == "__main__":
    main()
