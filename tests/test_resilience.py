from pico.resilience import CircuitBreaker, retry_with_backoff


def test_circuit_breaker_opens_after_threshold():
    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout_sec=60)
    assert breaker.allow_request() is True
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.allow_request() is False


def test_retry_with_backoff_retries_until_success():
    attempts = {"count": 0}

    def flaky_call():
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise RuntimeError("temporary")
        return "ok"

    assert retry_with_backoff(flaky_call, max_attempts=3, base_delay_sec=0) == "ok"
    assert attempts["count"] == 2
