from fastapi import FastAPI, Depends, status
from sqlalchemy.orm import Session
import aio_pika
import os
import json
import time
from models import get_db, Task, Base, engine, TaskCreate
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from logging_config import setup_logging
import logging

Base.metadata.create_all(bind=engine)
setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="TaskFlow Backend",
    version="1.0.0",
    root_path="/api"
)

# RabbitMQ settings
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
TASK_QUEUE_NAME = os.getenv("TASK_QUEUE_NAME", "task_queue")


async def publish_task_created(task_id: int) -> None:
    logger.info("Publishing TaskCreated event for task_id=%s", task_id)
    try:
        connection = await aio_pika.connect_robust(RABBITMQ_URL)
        async with connection:
            channel = await connection.channel()
            await channel.declare_queue(TASK_QUEUE_NAME, durable=True)
            message = aio_pika.Message(
                body=json.dumps({"task_id": task_id}).encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                type="TaskCreated",
            )
            await channel.default_exchange.publish(message, routing_key=TASK_QUEUE_NAME)
            logger.info("TaskCreated event published successfully for task_id=%s", task_id)
    except Exception as e:
        logger.error("Failed to publish TaskCreated event for task_id=%s: %s", task_id, str(e))
        raise


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




@app.get("/")
def read_root():
    http_requests_total.labels(method="GET", endpoint="/", status="200").inc()
    return {"message": "Welcome to TaskFlow API"}


@app.get("/tasks")
def get_tasks(db: Session = Depends(get_db)):
    http_requests_total.labels(method="GET", endpoint="/tasks", status="200").inc()
    # calc the request latency
    start_time = time.time()

    tasks = db.query(Task).all()
    tasks_data = [
        {
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "status": task.status,
        }
        for task in tasks
    ]

    # calculate the request latency
    latency = time.time() - start_time
    http_request_duration_seconds.labels(method="GET", endpoint="/tasks").observe(latency)

    return {"tasks": tasks_data}


@app.post("/tasks", status_code=status.HTTP_202_ACCEPTED)
async def create_task(task: TaskCreate, db: Session = Depends(get_db)):
    logger.info("Creating Task %s", task.title)
    http_requests_total.labels(method="POST", endpoint="/tasks", status="202").inc()

    start_time = time.time()

    new_task = Task(title=task.title, description=task.description, status="PENDING")

    db.add(new_task)
    db.commit()
    db.refresh(new_task)

    await publish_task_created(new_task.id)

    # calculate the request latency
    latency = time.time() - start_time
    http_request_duration_seconds.labels(method="POST", endpoint="/tasks").observe(latency)

    return {
        "task": {
            "id": new_task.id,
            "title": new_task.title,
            "description": new_task.description,
            "status": new_task.status,
        }
    }

# ========== Instrumental Setup ==========
Instrumentator().instrument(app).expose(app)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
