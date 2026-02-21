from __future__ import annotations
import logging
import os
import sys
from context import get_request_id


class RequestIDFilter(logging.Filter):
    """自动将 ContextVar 中的 request_id 注入到日志记录中"""

    def filter(self, record):
        record.request_id = get_request_id()
        return True


def setup_logging() -> None:
    """
    配置基础日志系统。
    仅输出到标准输出 (Console/stdout)
    """
    # 获取根记录器 (Root Logger)
    # 如果已经有 Handler (比如 Uvicorn 已经配置过)，则不再重复添加
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return

    # 确定日志级别 (从环境变量读取，默认为 INFO)
    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    root_logger.setLevel(log_level)

    # 定义日志格式化器 (Formatter)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | [%(request_id)s] | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 配置控制台处理器 (StreamHandler)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(RequestIDFilter())

    # 挂载处理器
    root_logger.addHandler(console_handler)


def get_logger(name: str | None = None) -> logging.Logger:
    """Initialize logging once and return a named logger."""
    setup_logging()
    return logging.getLogger(name)
