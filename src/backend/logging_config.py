"""Centralized logging configuration that forwards structured logs to Loki when configured."""
from __future__ import annotations

import json
import logging
import os
import sys
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
    """
    配置基础日志系统。
    仅输出到标准输出 (Console/stdout)，移除 Loki 直接推送逻辑。
    """
    # 1. 获取根记录器 (Root Logger)
    root_logger = logging.getLogger()

    # 2. 如果已经有 Handler (比如 Uvicorn 已经配置过)，则不再重复添加
    #    这样可以避免一条日志打印两次 (Duplicate Logs)
    if root_logger.handlers:
        return

    # 3. 确定日志级别 (从环境变量读取，默认为 INFO)
    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    root_logger.setLevel(log_level)

    # 4. 配置控制台处理器 (StreamHandler)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    # 5. 挂载处理器
    root_logger.addHandler(console_handler)
