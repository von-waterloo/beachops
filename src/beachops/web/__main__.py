from __future__ import annotations

import uvicorn

from beachops.config.settings import get_settings
from beachops.services.logging_config import configure_logging


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, service="api")
    uvicorn.run(
        "beachops.web.app:create_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
        log_config=None,
    )


if __name__ == "__main__":
    main()
