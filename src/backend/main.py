from fastapi import FastAPI, Depends, status, Request
from sqlalchemy.orm import Session

import aio_pika
import os
import json

# tracing 要在 models 之前初始化：models 模块级会立刻跑 DB 重试连接逻辑并打日志，
# 需要保证 OTel 的 LoggingInstrumentor 已经就绪（即便晚了，logging_config.py 里
# 的 RequestIDFilter 也有默认值兜底，这里只是让 trace_id 尽量从最早的日志就开始带上）
from tracing import setup_tracing
from metrics import setup_metrics
from opentelemetry import baggage as otel_baggage
from opentelemetry import context as otel_context
from opentelemetry import propagate, trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

tracer = setup_tracing("taskflow-backend")
meter = setup_metrics("taskflow-backend")

from models import get_db, Task, Base, engine, TaskCreate, maybe_inject_slow_query
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

# RabbitMQ settings
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
TASK_QUEUE_NAME = os.getenv("TASK_QUEUE_NAME", "task_queue")

rabbitmq_messages_published_total = meter.create_counter(
    name="rabbitmq_messages_published_total",
    description="Number of tasks successfully published to RabbitMQ",
)

# [新增] 定义 Worker 侧的业务吞吐量指标
worker_tasks_processed_total = meter.create_counter(
    name="worker_tasks_processed_total",
    description="Total number of tasks processed by the worker",
)


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
                rabbitmq_messages_published_total.add(1)
                logger.info("TaskCreated event published successfully for task_id=%s", task_id)
        except Exception as e:
            logger.error("Failed to publish TaskCreated event for task_id=%s: %s", task_id, str(e))
            raise


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID")
    req_id = set_request_id(req_id)

    response = await call_next(request)

    response.headers["X-Request-ID"] = req_id
    return response


@app.middleware("http")
async def load_test_baggage_middleware(request: Request, call_next):
    """Puts X-Load-Test-ID into OTel Baggage so it propagates to every span
    in this request (and, via RabbitMQ header propagation, into the worker's
    spans too) as a `test.load_test_id` attribute — lets Tempo/Grafana filter
    a trace down to "which k6 load-test run produced it".
    """
    load_test_id = request.headers.get("X-Load-Test-ID")
    token = None
    if load_test_id:
        ctx = otel_baggage.set_baggage("test.load_test_id", load_test_id)
        token = otel_context.attach(ctx)

    try:
        response = await call_next(request)
    finally:
        if token is not None:
            otel_context.detach(token)

    if load_test_id:
        response.headers["X-Load-Test-ID"] = load_test_id
    return response


# Must run after the custom middlewares above are registered: Starlette's
# add_middleware() prepends, so registering this last makes OpenTelemetry's
# ASGI middleware the outermost layer. If it were innermost (e.g. registered
# before our middlewares, as it originally was), its root-span creation
# would call context.attach(propagate.extract(scope)) — which starts from a
# *fresh* Context() — and silently wipe out any Baggage our middlewares had
# just attached, since nothing runs after it to re-extract context again.
FastAPIInstrumentor.instrument_app(app)


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
    
    # 在提交事务前注入慢查询，模拟写入阻塞
    with tracer.start_as_current_span("chaos.slow_query") as span:
        maybe_inject_slow_query(db, span)
    
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
