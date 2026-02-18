from sqlalchemy import Column, Integer, String, create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_fixed, before_log
from logging_config import get_logger
import os
import logging

logger = get_logger(__name__)

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
    "postgresql://taskflow:changeme@localhost:5432/taskflow"
)

# 每两秒重试一次，最多重试30次，直到数据库连接成功为止
@retry(
    stop=stop_after_attempt(30),
    wait=wait_fixed(2),
    before=before_log(logger, logging.INFO),
    reraise=True
)
def create_engine_with_retry():
    temp_engine = create_engine(DATABASE_URL)
    # 尝试连接数据库，如果失败则重试
    try:
        with temp_engine.connect() as connection:
            # 执行一个简单的查询验证
            connection.execute(text("SELECT 1"))
            logger.info("✅ Database connection established successfully!")
    except Exception as e:
        logger.warning(f"⚠️ Database not ready yet, retrying... Error: {e}")
        raise e  # 抛出异常让 tenacity 捕获并重试

    return temp_engine


engine = create_engine_with_retry()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
