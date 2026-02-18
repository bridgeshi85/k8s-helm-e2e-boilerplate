import logging
import os
import sys

from context import get_request_id


class RequestIDFilter(logging.Filter):
    """Injects the request_id from the ContextVar into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def setup_logging() -> None:
    """Configure a stdout logger that understands request_id context."""
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return

    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    root_logger.setLevel(log_level)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | [%(request_id)s] | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(RequestIDFilter())
    root_logger.addHandler(console_handler)


def get_logger(name: str | None = None) -> logging.Logger:
    """Initialize logging once and return a named logger."""
    setup_logging()
    return logging.getLogger(name)
