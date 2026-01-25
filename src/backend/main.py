from fastapi import FastAPI, Depends, Body
from sqlalchemy.orm import Session
import redis
import os
import json
from models import get_db, Task, Base, engine, TaskCreate
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="TaskFlow Backend",
    version="1.0.0",
    root_path="/api"
)

# Redis connection
redis_client = redis.Redis(host=os.getenv('REDIS_HOST', 'localhost'), port=6379, decode_responses=True)

# ========== Custom Prometheus Metrics (RED Method) ==========

# Rate - Request counter
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

# Errors - Error counter
http_errors_total = Counter(
    'http_errors_total',
    'Total HTTP errors',
    ['method', 'endpoint', 'status_code']
)

# Duration - Request latency histogram
http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['method', 'endpoint'],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0]
)

# Cache hit/miss metrics
cache_hits_total = Counter(
    'cache_hits_total',
    'Total cache hits',
    ['endpoint']
)

cache_misses_total = Counter(
    'cache_misses_total',
    'Total cache misses',
    ['endpoint']
)

# Database query metrics
db_queries_total = Counter(
    'db_queries_total',
    'Total database queries',
    ['operation', 'table']
)

# Active connections gauge
active_connections = Gauge(
    'active_connections',
    'Number of active connections'
)

# ========== Instrumentator Setup ==========
instrumentator = Instrumentator(
    should_group_status_codes=False,
    should_ignore_untemplated=True,
    should_group_untemplated=True,
    should_instrument_requests_inprogress=True,
    should_instrument_requests_duration=True,
    excluded_handlers=["/metrics"],
    env_var_name="ENABLE_METRICS",
    inprogress_name="fastapi_inprogress",
    inprogress_labels=True,
)

instrumentator.instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

# Redis connection
redis_client = redis.Redis(host=os.getenv('REDIS_HOST', 'localhost'), port=6379, decode_responses=True)


@app.get("/")
def read_root():
    http_requests_total.labels(method="GET", endpoint="/", status="200").inc()
    return {"message": "Welcome to TaskFlow API"}

@app.get("/tasks")
def get_tasks(db: Session = Depends(get_db)):
    # Try to get from cache
    cached_tasks = redis_client.get("all_tasks")
    if cached_tasks:
        cache_hits_total.labels(endpoint="/tasks").inc()
        db_queries_total.labels(operation="none", table="none").inc()
        return {"tasks": json.loads(cached_tasks)}

    # Cache miss
    cache_misses_total.labels(endpoint="/tasks").inc()

    # If not in cache, get from DB
    db_queries_total.labels(operation="select", table="tasks").inc()
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

    db_queries_total.labels(operation="insert", table="tasks").inc()

    # 清除缓存
    try:
        redis_client.delete("all_tasks")
    except Exception:
        pass

    return {"task": {"id": new_task.id, "title": new_task.title, "description": new_task.description}}

@app.get("/cache/{key}")
def get_cache(key: str):
    value = redis_client.get(key)
    if value:
        cache_hits_total.labels(endpoint="/cache/{key}").inc()
    else:
        cache_misses_total.labels(endpoint="/cache/{key}").inc()
    return {"key": key, "value": value}

@app.post("/cache")
def set_cache(key: str, value: str):
    redis_client.set(key, value)
    return {"message": "Cached successfully"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)