"""Retry decorator for async functions with optional exponential backoff."""

from __future__ import annotations

import asyncio
import logging
import random
from functools import wraps
from typing import Any, Callable, Coroutine, TypeVar

from app.core.config import get_app_config

R = TypeVar("R")
logger = logging.getLogger(__name__)


def is_retryable_error(exc: Exception) -> bool:
    """Provider-neutral retry classification using common SDK attributes."""
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code in {408, 409, 425, 429} or status_code >= 500
    if isinstance(exc, (TimeoutError, ConnectionError, OSError, asyncio.TimeoutError)):
        return True
    name = type(exc).__name__.lower()
    return "timeout" in name or "connection" in name or "ratelimit" in name


def retry_on_failure(
    max_retries: int | None = None,
    base_delay: float | None = None,
    exponential: bool = True,
    jitter: bool = True,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
):
    """Decorator for async functions. Retries on exception with optional
    exponential backoff and jitter.

    Args:
        max_retries: Maximum number of retry attempts. Defaults to the
            ``tool_max_retries`` setting in app_config.yaml.
        base_delay: Initial delay in seconds. Defaults to the
            ``tool_delay`` setting in app_config.yaml.
        exponential: If True, multiply the delay by 2 on each retry.
        jitter: If True, add +/- 25% random jitter to the delay.
        retryable_exceptions: Tuple of exception types that trigger a retry.
    """
    # Resolve defaults from app config
    _cfg = get_app_config().retry
    _max_retries = max_retries if max_retries is not None else _cfg.tool_max_retries
    _base_delay = base_delay if base_delay is not None else _cfg.tool_delay

    def decorator(
        func: Callable[..., Coroutine[Any, Any, R]],
    ) -> Callable[..., Coroutine[Any, Any, R]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> R:
            last_exception: Exception | None = None
            for attempt in range(_max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as exc:
                    last_exception = exc
                    if attempt >= _max_retries:
                        logger.warning(
                            "Retry exhausted for '%s' after %d attempts: %s",
                            func.__name__,
                            attempt + 1,
                            exc,
                        )
                        raise

                    delay = _base_delay * (2 ** attempt) if exponential else _base_delay
                    if jitter:
                        delay *= random.uniform(0.75, 1.25)

                    logger.info(
                        "Retry %d/%d for '%s' after %.2fs: %s",
                        attempt + 1,
                        _max_retries,
                        func.__name__,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)

            # Should be unreachable; satisfy type checker
            if last_exception is not None:
                raise last_exception
            raise RuntimeError("Unexpected retry exhaustion")

        return wrapper

    return decorator
