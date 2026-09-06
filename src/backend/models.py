import os
import logging
import random
import threading
from typing import Any, Iterable

from sqlalchemy import Column, Integer, String, create_engine, text, event
from sqlalchemy.orm import sessionmaker, declarative_base
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_fixed, before_log

# [新增] OTel 指标相关导入
from opentelemetry import metrics
from opentelemetry.metrics import Observation

# [删除] from prometheus_client import Gauge

from logging_config import get_logger

logger: Any = get_logger(__name__)

Base = declarative_base()


class Task(Base):
    __tablename__ = 'tasks'
    id = Column(Integer, primary_key=True)
    title = Column(String(100), nullable=False)
    description = Column(String(500))
    status = Column(String(32), nullable=False, default="PENDING")


class TaskCreate(BaseModel):
    title: str
    description: str = ""


DATABASE_URL = os.getenv(
    'DATABASE_URL',
    "postgresql://taskflow:taskflowDatabase@localhost:5432/taskflow"
)

@retry(
    stop=stop_after_attempt(30),
    wait=wait_fixed(2),
    before=before_log(logger, logging.INFO),
    reraise=True
)
def create_engine_with_retry():
    # --- 增加高并发与高可用配置 ---
    temp_engine = create_engine(
        DATABASE_URL,
        pool_size=int(os.getenv("DB_POOL_SIZE", "20")),  # 连接数
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),  # 最大溢出连接数
        pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),  # 获取连接的最大等待时间（秒）
        pool_pre_ping=True,  # 悲观连接检测
    )

    try:
        with temp_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            logger.info("✅ Database connection established successfully!")
    except Exception as e:
        logger.warning(f"⚠️ Database not ready yet, retrying... Error: {e}")
        raise e

    return temp_engine


engine = create_engine_with_retry()

# ---------------------------------------------------------
# OTel 指标重构：维护本地状态与注册回调
# ---------------------------------------------------------

# 1. 维护线程安全的连接状态计数器
class DBPoolStats:
    def __init__(self):
        self.active_connections = 0
        self.total_connections = 0
        self.lock = threading.Lock()

pool_stats = DBPoolStats()

# 2. 精准监听真实连接池事件，更新本地状态
@event.listens_for(engine, 'checkout')
def receive_checkout(dbapi_connection, connection_record, connection_proxy):
    with pool_stats.lock:
        pool_stats.active_connections += 1

@event.listens_for(engine, 'checkin')
def receive_checkin(dbapi_connection, connection_record):
    with pool_stats.lock:
        pool_stats.active_connections -= 1

@event.listens_for(engine, 'connect')
def receive_connect(dbapi_connection, connection_record):
    with pool_stats.lock:
        pool_stats.total_connections += 1

@event.listens_for(engine, 'close')
def receive_close(dbapi_connection, connection_record):
    with pool_stats.lock:
        pool_stats.total_connections -= 1

# 3. 定义 OTel 所需的回调函数 (每次 OTel 导出数据时会调用它们)
def get_active_connections_callback(options) -> Iterable[Observation]:
    with pool_stats.lock:
        yield Observation(pool_stats.active_connections)

def get_pool_size_callback(options) -> Iterable[Observation]:
    with pool_stats.lock:
        yield Observation(pool_stats.total_connections)

# 4. 获取全局 Meter 并注册 ObservableGauge
# （只要 main.py 中优先执行了 setup_metrics 设置全局 Provider，这里就能顺利挂载）
meter = metrics.get_meter("taskflow-backend")

meter.create_observable_gauge(
    name="db_connection_pool_active",
    callbacks=[get_active_connections_callback],
    description="Number of database connections currently checked out from the pool"
)

meter.create_observable_gauge(
    name="db_connection_pool_size",
    callbacks=[get_pool_size_callback],
    description="Total number of database connections in the pool (active + idle)"
)

# [新增] OTel Counter for chaos slow query injection
chaos_slow_query_injected = meter.create_counter(
    name="chaos_slow_query_injected",
    description="Chaos slow query injection attempts (true/false branches)",
)


# ---------------------------------------------------------

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def maybe_inject_slow_query(db, span):
    """Chaos hook: hold a real DB connection for N seconds via pg_sleep, gated by SLOW_QUERY_ENABLED and probability."""
    is_enabled = os.getenv("SLOW_QUERY_ENABLED", "false").lower() == "true"
    probability = float(os.getenv("SLOW_QUERY_PROBABILITY", "0.2"))
    seconds = float(os.getenv("SLOW_QUERY_SECONDS", "3.0"))

    if is_enabled and random.random() < probability:
        span.set_attribute("chaos.slow_query.injected", True)
        span.set_attribute("chaos.slow_query.seconds", seconds)
        logger.warning(f"Injecting {seconds}s slow query into DB transaction...")
        db.execute(text("SELECT pg_sleep(:s)"), {"s": seconds})
        chaos_slow_query_injected.add(1, {"injected": "true"})
    else:
        span.set_attribute("chaos.slow_query.injected", False)
        chaos_slow_query_injected.add(1, {"injected": "false"})

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()