"""Entry point: ``python -m beachops.windows_worker``."""

from __future__ import annotations

import asyncio
import logging
import sys

from beachops.windows_worker.daemon import run_daemon


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [windows-worker] %(message)s",
    )
    try:
        asyncio.run(run_daemon())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Stopped by user")
        sys.exit(0)


if __name__ == "__main__":
    main()
