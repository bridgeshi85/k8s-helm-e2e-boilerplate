import os
import json
import time
import asyncio

import aio_pika
from sqlalchemy.orm import Session

# 和 backend 一样，tracing 要在 models 之前初始化（见 backend/main.py 里的注释）
from tracing import setup_tracing
from metrics import setup_metrics
from opentelemetry import propagate, trace
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

tracer = setup_tracing("taskflow-worker")
meter = setup_metrics("taskflow-worker")

from models import get_db, Task, engine
from logging_config import get_logger
from context import set_request_id

SQLAlchemyInstrumentor().instrument(engine=engine)

logger = get_logger(__name__)


RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
TASK_QUEUE_NAME = os.getenv("TASK_QUEUE_NAME", "task_queue")


def update_task_status(task_id: int, status: str) -> None:
    db: Session = next(get_db())
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if task:
            task.status = status
            db.commit()
    finally:
        db.close()


async def process_message(message: aio_pika.IncomingMessage) -> None:
    async with message.process():
        payload = json.loads(message.body.decode())
        req_id = message.headers.get("x-request-id")
        set_request_id(req_id)

        # 从 backend 塞进 message headers 的 trace context 续上链路
        otel_ctx = propagate.extract(message.headers)

        with tracer.start_as_current_span("worker.process_task", context=otel_ctx) as span:
            span.set_attribute("messaging.system", "rabbitmq")
            span.set_attribute("messaging.destination", TASK_QUEUE_NAME)

            logger.info("Worker received task", extra={"trace_id": req_id})

            task_id = payload.get("task_id")
            if not task_id:
                return
            span.set_attribute("task.id", task_id)

            with tracer.start_as_current_span("worker.mark_running"):
                update_task_status(task_id, "RUNNING")
            await asyncio.sleep(5)
            with tracer.start_as_current_span("worker.mark_completed"):
                update_task_status(task_id, "COMPLETED")

            logger.info("Worker completed task", extra={"trace_id": req_id})


async def main() -> None:
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=1)
        queue = await channel.declare_queue(TASK_QUEUE_NAME, durable=True)
        await queue.consume(process_message)
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
