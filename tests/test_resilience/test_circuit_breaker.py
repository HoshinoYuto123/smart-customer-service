from __future__ import annotations

import pytest
from app.resilience.circuit_breaker import CircuitBreaker, CircuitState, CircuitBreakerError


class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_initial_state_closed(self):
        cb = CircuitBreaker(name="test", failure_threshold=3, cooldown_seconds=60)
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    @pytest.mark.asyncio
    async def test_successful_call(self):
        cb = CircuitBreaker(name="test", failure_threshold=3, cooldown_seconds=60)

        async def succeed():
            return "ok"

        result = await cb.call(succeed)
        assert result == "ok"
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    @pytest.mark.asyncio
    async def test_opens_after_threshold(self):
        cb = CircuitBreaker(name="test", failure_threshold=2, cooldown_seconds=60)

        async def fail():
            raise ValueError("test error")

        for _ in range(2):
            with pytest.raises(ValueError):
                await cb.call(fail)

        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_rejects_when_open(self):
        cb = CircuitBreaker(name="test", failure_threshold=2, cooldown_seconds=60)
        cb.state = CircuitState.OPEN

        async def succeed():
            return "ok"

        with pytest.raises(CircuitBreakerError):
            await cb.call(succeed)

    @pytest.mark.asyncio
    async def test_half_open_probe_success(self):
        cb = CircuitBreaker(name="test", failure_threshold=2, cooldown_seconds=60)
        cb.state = CircuitState.OPEN
        cb.failure_count = 2

        # Simulate cooldown expired
        cb._last_failure_time = 0

        async def succeed():
            return "ok"

        result = await cb.call(succeed)
        assert result == "ok"
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_status_report(self):
        cb = CircuitBreaker(name="test", failure_threshold=5, cooldown_seconds=60)
        status = cb.status()
        assert status["name"] == "test"
        assert status["state"] == "closed"
        assert status["failure_count"] == 0

    @pytest.mark.asyncio
    async def test_non_retryable_errors_do_not_open_circuit(self):
        cb = CircuitBreaker(
            name="test",
            failure_threshold=2,
            cooldown_seconds=60,
            failure_predicate=lambda exc: not isinstance(exc, ValueError),
        )

        async def invalid_request():
            raise ValueError("bad request")

        for _ in range(3):
            with pytest.raises(ValueError):
                await cb.call(invalid_request)
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
