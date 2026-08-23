import os
import json
import time
import asyncio

import aio_pika
from sqlalchemy.orm import Session

# 和 backend 一样，tracing 要在 models 之前初始化
from tracing import setup_tracing
from metrics import setup_metrics  # [新增] 引入 metrics 初始化模块

from opentelemetry import propagate, trace
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

tracer = setup_tracing("taskflow-worker")
meter = setup_metrics("taskflow-worker")  # [新增] 初始化全局指标配置打通 OTLP 通路

from models import get_db, Task, engine
from logging_config import get_logger
from context import set_request_id

SQLAlchemyInstrumentor().instrument(engine=engine)

logger = get_logger(__name__)

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
TASK_QUEUE_NAME = os.getenv("TASK_QUEUE_NAME", "task_queue")

# [新增] 定义 Worker 侧的业务吞吐量指标
tasks_processed_total = meter.create_counter(
    name="worker_tasks_processed_total",
    description="Total number of tasks processed by the worker",
)

task_processing_duration = meter.create_histogram(
    name="worker_task_processing_duration_seconds",
    description="Time spent processing a single task",
    unit="s",
)


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
                # [新增] 如果没有 task_id，记录为失败
                tasks_processed_total.add(1, {"status": "failed_missing_id"})
                return
            
            span.set_attribute("task.id", task_id)

            start_time = time.monotonic()
            try:
                with tracer.start_as_current_span("worker.mark_running"):
                    update_task_status(task_id, "RUNNING")

                await asyncio.sleep(5)

                with tracer.start_as_current_span("worker.mark_completed"):
                    update_task_status(task_id, "COMPLETED")

                logger.info("Worker completed task", extra={"trace_id": req_id})

                # [新增] 成功处理完任务，打上 success 标签并计数 +1
                tasks_processed_total.add(1, {"status": "success"})

            except Exception as e:
                # [新增] 处理异常，打上 failed 标签并计数 +1
                tasks_processed_total.add(1, {"status": "failed"})
                logger.error("Failed to process task_id=%s: %s", task_id, str(e))
                raise
            finally:
                task_processing_duration.record(time.monotonic() - start_time)


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