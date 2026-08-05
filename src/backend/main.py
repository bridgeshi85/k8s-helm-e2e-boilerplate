from fastapi import FastAPI, Depends, status, Request
from sqlalchemy.orm import Session

import aio_pika
import os
import json

# tracing 要在 models 之前初始化：models 模块级会立刻跑 DB 重试连接逻辑并打日志，
# 需要保证 OTel 的 LoggingInstrumentor 已经就绪（即便晚了，logging_config.py 里
# 的 RequestIDFilter 也有默认值兜底，这里只是让 trace_id 尽量从最早的日志就开始带上）
from tracing import setup_tracing
from opentelemetry import propagate, trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

tracer = setup_tracing("taskflow-backend")

from models import get_db, Task, Base, engine, TaskCreate
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Counter
from logging_config import get_logger
from context import set_request_id, get_request_id

SQLAlchemyInstrumentor().instrument(engine=engine)

# 建立数据库表结构
Base.metadata.create_all(bind=engine)

logger = get_logger(__name__)

app = FastAPI(
    title="TaskFlow Backend",
    version="1.0.0",
    root_path="/api"
)
FastAPIInstrumentor.instrument_app(app)

# RabbitMQ settings
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
TASK_QUEUE_NAME = os.getenv("TASK_QUEUE_NAME", "task_queue")


async def publish_task_created(task_id: int) -> None:
    with tracer.start_as_current_span("rabbitmq.publish") as span:
        span.set_attribute("messaging.system", "rabbitmq")
        span.set_attribute("messaging.destination", TASK_QUEUE_NAME)
        span.set_attribute("task.id", task_id)

        logger.info("Publishing TaskCreated event for task_id=%s", task_id)

        try:
            connection = await aio_pika.connect_robust(RABBITMQ_URL)
            current_req_id = get_request_id()  # 获取当前上下文的 ID

            # 把当前 trace context 注入 message headers，worker 消费时用它续上链路
            trace_headers: dict = {}
            propagate.inject(trace_headers)

            async with connection:
                channel = await connection.channel()
                await channel.declare_queue(TASK_QUEUE_NAME, durable=True)
                message = aio_pika.Message(
                    body=json.dumps({"task_id": task_id}).encode(),
                    content_type="application/json",
                    headers={"x-request-id": current_req_id, **trace_headers},
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    type="TaskCreated",
                )
                await channel.default_exchange.publish(message, routing_key=TASK_QUEUE_NAME)
                rabbitmq_messages_published_total.inc()
                logger.info("TaskCreated event published successfully for task_id=%s", task_id)
        except Exception as e:
            logger.error("Failed to publish TaskCreated event for task_id=%s: %s", task_id, str(e))
            raise


rabbitmq_messages_published_total = Counter(
    'rabbitmq_messages_published_total',
    'Number of tasks successfully published to RabbitMQ',
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID")
    req_id = set_request_id(req_id)

    response = await call_next(request)

    response.headers["X-Request-ID"] = req_id
    return response


@app.get("/")
def read_root():
    return {"message": "Welcome to TaskFlow API"}


@app.get("/tasks")
def get_tasks(db: Session = Depends(get_db)):
    logger.info("Getting tasks")
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
    return {"tasks": tasks_data}


@app.post("/tasks", status_code=status.HTTP_202_ACCEPTED)
async def create_task(task: TaskCreate, db: Session = Depends(get_db)):
    logger.info("Creating Task %s", task.title)

    new_task = Task(title=task.title, description=task.description, status="PENDING")
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    logger.info("Created Task in database %s", new_task)

    # 触发异步消息发送
    await publish_task_created(new_task.id)

    return {
        "task": {
            "id": new_task.id,
            "title": new_task.title,
            "description": new_task.description,
            "status": new_task.status,
        }
    }


# 使用 prometheus_fastapi_instrumentator 自动为 FastAPI 应用添加 Prometheus 指标
Instrumentator().instrument(app).expose(app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
