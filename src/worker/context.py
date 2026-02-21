# context.py
from contextvars import ContextVar
import uuid

# 定义一个全局的 ContextVar，默认值为空
# 它的作用域是“当前请求/协程”，不同请求互不干扰
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    return request_id_ctx.get()


def set_request_id(request_id: str = None) -> str:
    if not request_id:
        request_id = str(uuid.uuid4())
    token = request_id_ctx.set(request_id)
    return request_id
