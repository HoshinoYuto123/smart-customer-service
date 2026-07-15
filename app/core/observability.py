from __future__ import annotations

import uuid
import time
import contextvars
from functools import wraps
from typing import Callable, Awaitable

import structlog
from app.core.config import get_app_config


_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")
_session_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("session_id", default="")


def setup_logging():
    config = get_app_config()
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    if config.observability.log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(structlog.processors, config.observability.log_level.upper(), 20)
        ),
        context_class=dict,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    return structlog.get_logger(name or __name__)


def generate_trace_id() -> str:
    return str(uuid.uuid4())[:12]


def set_trace_id(trace_id: str):
    _trace_id_var.set(trace_id)


def get_trace_id() -> str:
    return _trace_id_var.get()


def set_session_id(session_id: str):
    _session_id_var.set(session_id)


def get_session_id() -> str:
    return _session_id_var.get()


def log_execution(func_name: str | None = None):
    """Decorator that logs function entry/exit with timing and trace_id."""

    def decorator(func: Callable[..., Awaitable]):
        name = func_name or func.__name__

        @wraps(func)
        async def wrapper(*args, **kwargs):
            logger = get_logger()
            trace_id = get_trace_id()
            start = time.perf_counter()

            logger.info(f"{name}.start", trace_id=trace_id)
            try:
                result = await func(*args, **kwargs)
                elapsed = (time.perf_counter() - start) * 1000
                logger.info(f"{name}.done", trace_id=trace_id, latency_ms=round(elapsed, 2))
                return result
            except Exception as e:
                elapsed = (time.perf_counter() - start) * 1000
                logger.error(f"{name}.error", trace_id=trace_id, error=str(e), latency_ms=round(elapsed, 2))
                raise

        return wrapper

    return decorator


# Initialize logging on import
setup_logging()
