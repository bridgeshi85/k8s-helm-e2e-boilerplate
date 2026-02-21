import os
import json
import time
import asyncio

import aio_pika
from sqlalchemy.orm import Session

from models import get_db, Task
from logging_config import get_logger
from context import set_request_id

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
        trace_id = message.headers.get("x-request-id")
        set_request_id(trace_id)
        logger.info("Worker received task", extra={"trace_id": trace_id})

        task_id = payload.get("task_id")
        if not task_id:
            return
        update_task_status(task_id, "RUNNING")
        await asyncio.sleep(5)
        update_task_status(task_id, "COMPLETED")
        logger.info("Worker completed task", extra={"trace_id": trace_id})


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
