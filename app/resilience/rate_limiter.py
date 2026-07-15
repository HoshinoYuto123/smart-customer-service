"""Token-bucket rate limiter for async callers."""

from __future__ import annotations

import asyncio
import time
from typing import Optional


class RateLimitExceeded(Exception):
    """Raised when a token cannot be acquired within the allowed wait time."""

    pass


class TokenBucketRateLimiter:
    """Token bucket algorithm for rate limiting.

    Tokens are refilled at a constant *rate* (tokens/sec) up to *capacity*.
    Each caller consumes one token; calls exceeding the bucket capacity are
    either rejected or queued until a token becomes available.

    Usage as context manager::

        limiter = TokenBucketRateLimiter(rate=10.0, capacity=20)
        async with limiter:
            await make_api_call()

    Usage with explicit acquire::

        if await limiter.acquire(wait=False):
            await make_api_call()
        else:
            raise RateLimitExceeded()
    """

    def __init__(self, rate: float, capacity: int) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        if capacity <= 0:
            raise ValueError("capacity must be positive")

        self.rate = float(rate)
        self.capacity = int(capacity)
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    # ── Public API ────────────────────────────────────────────────

    async def acquire(self, wait: bool = True, timeout: float | None = None) -> bool:
        """Attempt to consume a token.

        Args:
            wait: If True, wait until a token is available.
            timeout: Maximum seconds to wait (only when ``wait=True``).

        Returns:
            True if a token was consumed, False otherwise.
        """
        deadline = (time.monotonic() + timeout) if (wait and timeout) else None

        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True

            if not wait:
                return False

            # Calculate how long until the next token is available
            async with self._lock:
                wait_needed = max(0.0, (1.0 - self._tokens) / self.rate)

            now = time.monotonic()
            if deadline is not None and (now + wait_needed) > deadline:
                return False

            await asyncio.sleep(min(wait_needed, 0.05))

    # ── Async context manager ─────────────────────────────────────

    async def __aenter__(self) -> TokenBucketRateLimiter:
        acquired = await self.acquire(wait=True)
        if not acquired:
            raise RateLimitExceeded("Unable to acquire rate-limit token.")
        return self

    async def __aexit__(self, *args: object) -> None:
        pass  # Token already consumed in __aenter__

    # ── Internals ─────────────────────────────────────────────────

    def _refill(self) -> None:
        """Refill tokens based on elapsed time. Call under lock."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last_refill = now

    # ── Monitoring ────────────────────────────────────────────────

    @property
    def available_tokens(self) -> float:
        """Snapshot of currently available tokens (best-effort, not under lock)."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        return min(self.capacity, self._tokens + elapsed * self.rate)

    def status(self) -> dict:
        """Return a snapshot for monitoring."""
        return {
            "rate": self.rate,
            "capacity": self.capacity,
            "available_tokens": round(self.available_tokens, 2),
        }
