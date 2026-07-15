"""Circuit breaker – state machine that protects downstream services.

State transitions:
    CLOSED --> (failures >= threshold) --> OPEN
    OPEN   --> (cooldown elapsed)      --> HALF_OPEN
    HALF_OPEN --> (success)            --> CLOSED
    HALF_OPEN --> (failure)            --> OPEN
"""

from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import Any, Callable, Coroutine, TypeVar

from app.core.config import get_app_config

R = TypeVar("R")


class CircuitState(str, Enum):
    CLOSED = "closed"         # Normal operation – requests pass through
    OPEN = "open"             # Failing – requests are rejected immediately
    HALF_OPEN = "half_open"   # Probing – limited requests allowed to test recovery


class CircuitBreakerError(Exception):
    """Raised when a call is rejected because the circuit is open."""

    def __init__(self, breaker_name: str) -> None:
        self.breaker_name = breaker_name
        super().__init__(f"Circuit '{breaker_name}' is OPEN – call rejected.")


class CircuitBreaker:
    """Async circuit breaker protecting a single downstream dependency."""

    def __init__(
        self,
        name: str,
        failure_threshold: int | None = None,
        cooldown_seconds: float | None = None,
        half_open_max_calls: int | None = None,
    ) -> None:
        config = get_app_config().circuit_breaker

        self.name = name
        self.failure_threshold = failure_threshold or config.failure_threshold
        self.cooldown_seconds = cooldown_seconds or config.cooldown_seconds
        self.half_open_max_calls = half_open_max_calls or config.half_open_max_calls

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self._last_failure_time: float = time.monotonic()
        self._lock = asyncio.Lock()

        # Track half-open probes so we don't exceed the limit
        self._half_open_probes: int = 0

    # ── Public API ────────────────────────────────────────────────

    async def call(
        self,
        func: Callable[..., Coroutine[Any, Any, R]],
        *args: Any,
        **kwargs: Any,
    ) -> R:
        """Execute *func* with circuit-breaker protection.

        Returns the result of *func* on success.

        Raises:
            CircuitBreakerError: If the circuit is OPEN and refuses the call.
            Exception: Any exception raised by *func* is re-raised.
        """
        async with self._lock:
            if self.state == CircuitState.OPEN:
                if self._cooldown_elapsed():
                    self._transition_to(CircuitState.HALF_OPEN)
                else:
                    raise CircuitBreakerError(self.name)

            if self.state == CircuitState.HALF_OPEN:
                if self._half_open_probes >= self.half_open_max_calls:
                    raise CircuitBreakerError(self.name)
                self._half_open_probes += 1

        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception:
            await self._on_failure()
            raise

    # ── Async context manager ─────────────────────────────────────

    async def __aenter__(self) -> CircuitBreaker:
        """Enter the circuit breaker context.

        Usage:
            async with breaker:
                # breaker is protecting this block
        """
        async with self._lock:
            if self.state == CircuitState.OPEN:
                if self._cooldown_elapsed():
                    self._transition_to(CircuitState.HALF_OPEN)
                else:
                    raise CircuitBreakerError(self.name)

            if self.state == CircuitState.HALF_OPEN:
                if self._half_open_probes >= self.half_open_max_calls:
                    raise CircuitBreakerError(self.name)
                self._half_open_probes += 1

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool:
        """Handle context-manager exit: record success or failure."""
        if exc_type is None:
            await self._on_success()
        else:
            await self._on_failure()
        return False  # Don't suppress the exception

    # ── Internals ─────────────────────────────────────────────────

    async def _on_success(self) -> None:
        """Handle a successful call."""
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self._half_open_probes = max(0, self._half_open_probes - 1)
                self._transition_to(CircuitState.CLOSED)
            elif self.state == CircuitState.CLOSED:
                self.failure_count = 0

    async def _on_failure(self) -> None:
        """Handle a failed call."""
        async with self._lock:
            self.failure_count += 1
            self._last_failure_time = time.monotonic()

            if self.state == CircuitState.HALF_OPEN:
                self._half_open_probes = max(0, self._half_open_probes - 1)
                self._transition_to(CircuitState.OPEN)
            elif (
                self.state == CircuitState.CLOSED
                and self.failure_count >= self.failure_threshold
            ):
                self._transition_to(CircuitState.OPEN)

    def _transition_to(self, new_state: CircuitState) -> None:
        """Atomically update the circuit state."""
        old = self.state
        self.state = new_state
        if new_state == CircuitState.CLOSED:
            self.failure_count = 0
        # Logging could be added here for observability.

    def _cooldown_elapsed(self) -> bool:
        """Check whether the cooldown period has passed since the last failure."""
        return (time.monotonic() - self._last_failure_time) >= self.cooldown_seconds

    # ── Introspection helpers ─────────────────────────────────────

    def status(self) -> dict:
        """Return a snapshot of the breaker's internal state for monitoring."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "half_open_probes": self._half_open_probes,
        }
