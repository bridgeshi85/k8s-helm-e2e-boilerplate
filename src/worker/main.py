import os
import json
import time

import aio_pika
from sqlalchemy.orm import Session

from models import get_db, Task


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
        task_id = payload.get("task_id")
        if not task_id:
            return
        update_task_status(task_id, "RUNNING")
        await asyncio.sleep(5)
        update_task_status(task_id, "COMPLETED")


async def main() -> None:
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=1)
        queue = await channel.declare_queue(TASK_QUEUE_NAME, durable=True)
        await queue.consume(process_message)
        await asyncio.Future()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
