"""Centralized logging configuration that forwards structured logs to Loki when configured."""
from __future__ import annotations

import json
import logging
import os
from typing import Dict, Optional, Tuple

try:
    from logging_loki import LokiHandler  # type: ignore
except ImportError:  # pragma: no cover - handled gracefully at runtime
    LokiHandler = None  # type: ignore

_LokiAuth = Optional[Tuple[str, str]]


def _parse_labels() -> Dict[str, str]:
    base_labels = {
        "app": os.getenv("APP_NAME", "taskflow-backend"),
        "environment": os.getenv("ENVIRONMENT", "dev"),
    }
    raw_labels = os.getenv("LOKI_EXTRA_LABELS")
    if not raw_labels:
        return base_labels

    try:
        extra_labels = json.loads(raw_labels)
        if isinstance(extra_labels, dict):
            base_labels.update({str(k): str(v) for k, v in extra_labels.items()})
    except json.JSONDecodeError:
        logging.getLogger(__name__).warning("LOKI_EXTRA_LABELS is not valid JSON; ignoring")
    return base_labels


def _build_auth() -> _LokiAuth:
    user = os.getenv("LOKI_BASIC_AUTH_USER")
    password = os.getenv("LOKI_BASIC_AUTH_PASS")
    if user and password:
        return user, password
    return None


def setup_logging() -> None:
    """Attach a Loki handler to the root logger when LOKI_URL is present."""
    loki_url = os.getenv("LOKI_URL")
    if not loki_url:
        return

    if LokiHandler is None:
        logging.getLogger(__name__).warning(
            "python-logging-loki is not installed; skipping Loki setup"
        )
        return

    root_logger = logging.getLogger()
    if any(isinstance(handler, LokiHandler) for handler in root_logger.handlers):
        return

    handler = LokiHandler(
        url=loki_url.rstrip("/"),
        version="1",
        tags=_parse_labels(),
        auth=_build_auth(),
    )

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    handler.setLevel(getattr(logging, log_level, logging.INFO))
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )

    root_logger.setLevel(min(root_logger.level or logging.INFO, handler.level))
    root_logger.addHandler(handler)

