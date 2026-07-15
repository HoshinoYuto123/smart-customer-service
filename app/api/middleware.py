from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.observability import generate_trace_id, set_trace_id, set_session_id, get_logger

logger = get_logger(__name__)


class TraceMiddleware(BaseHTTPMiddleware):
    """Inject trace_id into every request and log request/response."""

    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("X-Trace-Id", generate_trace_id())
        session_id = request.headers.get("X-Session-Id", "")

        set_trace_id(trace_id)
        if session_id:
            set_session_id(session_id)

        start = time.perf_counter()

        try:
            response = await call_next(request)
            elapsed = (time.perf_counter() - start) * 1000

            response.headers["X-Trace-Id"] = trace_id
            logger.info(
                "request.done",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                latency_ms=round(elapsed, 2),
                trace_id=trace_id,
            )
            return response

        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error(
                "request.error",
                method=request.method,
                path=request.url.path,
                error=str(e),
                latency_ms=round(elapsed, 2),
                trace_id=trace_id,
            )
            return JSONResponse(
                status_code=500,
                content={
                    "error": "服务器内部错误",
                    "message": "系统处理请求时发生未预期的错误，请稍后重试。",
                    "trace_id": trace_id,
                },
            )
