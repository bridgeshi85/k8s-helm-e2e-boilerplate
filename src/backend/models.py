import os
import logging
from typing import Any
from sqlalchemy import Column, Integer, String, create_engine, text, event
from sqlalchemy.orm import sessionmaker, \
    declarative_base
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_fixed, before_log
from prometheus_client import Gauge

# from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

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

# --- Prometheus Metrics 定义 ---
db_connection_pool_active = Gauge(
    "db_connection_pool_active",
    "Number of database connections currently checked out from the pool",
)
db_connection_pool_size = Gauge(
    "db_connection_pool_size",
    "Total number of database connections in the pool (active + idle)",
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
        pool_size=20,  # 连接数
        max_overflow=10,  # 最大溢出连接数
        pool_timeout=30,  # 获取连接的最大等待时间（秒）
        pool_pre_ping=True,  # 悲观连接检测（防止断网/DB重启导致拿到失效连接）
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


# --- 精准监听真实连接池事件 ---
@event.listens_for(engine, 'checkout')
def receive_checkout(dbapi_connection, connection_record, connection_proxy):
    db_connection_pool_active.inc()


@event.listens_for(engine, 'checkin')
def receive_checkin(dbapi_connection, connection_record):
    db_connection_pool_active.dec()


@event.listens_for(engine, 'connect')
def receive_connect(dbapi_connection, connection_record):
    db_connection_pool_size.inc()


@event.listens_for(engine, 'close')
def receive_close(dbapi_connection, connection_record):
    db_connection_pool_size.dec()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
