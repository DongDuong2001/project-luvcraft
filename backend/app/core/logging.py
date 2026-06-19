import logging
import sys

from app.core.config import settings


def setup_logging(level: int = logging.INFO) -> None:
    """
    Configure global logging with timestamp, level, and module context.
    Satisfies Task 3.6 acceptance criteria:
    - Errors are logged properly
    - Logs include timestamps and context
    """
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Avoid duplicate handlers if called more than once
    if not root_logger.handlers:
        root_logger.addHandler(handler)
    else:
        root_logger.handlers.clear()
        root_logger.addHandler(handler)

    # Keep third-party HTTP clients from logging full URLs with query-string credentials
    # unless a developer explicitly enables HTTP debug logging.
    http_client_level = logging.DEBUG if settings.DEBUG_HTTP else logging.WARNING
    logging.getLogger("httpx").setLevel(http_client_level)
    logging.getLogger("httpcore").setLevel(http_client_level)
