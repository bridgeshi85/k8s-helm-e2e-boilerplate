from fastapi import FastAPI, Depends, Body
from sqlalchemy.orm import Session
import redis
import os
import json
from contextlib import asynccontextmanager # 导入这个
from models import get_db, Task, Base, engine, TaskCreate 

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="TaskFlow Backend",
    version="1.0.0",
    root_path="/api"
)

# Redis connection
redis_client = redis.Redis(host=os.getenv('REDIS_HOST', 'localhost'), port=6379, decode_responses=True)


@app.get("/")
def read_root():
    return {"message": "Welcome to TaskFlow API"}

@app.get("/tasks")
def get_tasks(db: Session = Depends(get_db)):
    # Try to get from cache
    cached_tasks = redis_client.get("all_tasks")
    if cached_tasks:
        return {"tasks": json.loads(cached_tasks)}

    # If not in cache, get from DB
    tasks = db.query(Task).all()
    tasks_data = [{"id": task.id, "title": task.title, "description": task.description} for task in tasks]
    
    # Store in cache for 60 seconds
    redis_client.setex("all_tasks", 60, json.dumps(tasks_data))
    
    return {"tasks": tasks_data}

@app.post("/tasks")
def create_task(task: TaskCreate, db: Session = Depends(get_db)):
    new_task = Task(title=task.title, description=task.description)
    
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    
    # 清除缓存
    try:
        redis_client.delete("all_tasks")
    except Exception:
        pass
    
    return {"task": {"id": new_task.id, "title": new_task.title, "description": new_task.description}}

@app.get("/cache/{key}")
def get_cache(key: str):
    value = redis_client.get(key)
    return {"key": key, "value": value}

@app.post("/cache")
def set_cache(key: str, value: str):
    redis_client.set(key, value)
    return {"message": "Cached successfully"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)