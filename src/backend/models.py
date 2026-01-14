from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from pydantic import BaseModel
import os

Base = declarative_base()

class Task(Base):
    __tablename__ = 'tasks'

    id = Column(Integer, primary_key=True)
    title = Column(String(100), nullable=False)
    description = Column(String(500))

# ✅ 新增：用于接收前端 JSON 请求的 Pydantic 模型
class TaskCreate(BaseModel):
    title: str
    description: str = "" # 默认为空字符串

# Database URL should be configured via environment variables
DATABASE_URL = os.getenv(
    'DATABASE_URL', 
    "postgresql://taskflow:changeme@localhost:5432/taskflow"  # 本地开发 fallback，使用 localhost
)

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()