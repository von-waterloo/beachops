"""Entry point."""

from __future__ import annotations

import logging

from beachops.app import create_application
from beachops.config.settings import get_settings
from beachops.services.logging_config import configure_logging

logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, service="bot")
    application = create_application(settings)
    logger.info("Starting bot (long polling)")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
