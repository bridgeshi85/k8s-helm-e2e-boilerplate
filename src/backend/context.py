# context.py
from contextvars import ContextVar
import uuid

# 全局的 ContextVar，默认值为空
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    return request_id_ctx.get()


def set_request_id(request_id: str = None) -> str:
    if not request_id:
        request_id = str(uuid.uuid4())
    request_id_ctx.set(request_id)
    return request_id
