"""Entry point."""

from __future__ import annotations

import logging

from tg_cursor_bot.app import create_application
from tg_cursor_bot.config.settings import get_settings

logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    application = create_application(settings)
    logger.info("Starting bot (long polling)")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
