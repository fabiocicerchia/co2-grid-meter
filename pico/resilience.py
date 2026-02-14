import logging
import time
from dataclasses import dataclass

LOGGER = logging.getLogger(__name__)


@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    recovery_timeout_sec: int = 120
    failure_count: int = 0
    opened_at: float = 0.0

    def allow_request(self) -> bool:
        if self.failure_count < self.failure_threshold:
            return True
        return (time.time() - self.opened_at) >= self.recovery_timeout_sec

    def record_success(self) -> None:
        self.failure_count = 0
        self.opened_at = 0.0

    def record_failure(self) -> None:
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold and self.opened_at == 0.0:
            self.opened_at = time.time()


def retry_with_backoff(callable_fn, max_attempts=3, base_delay_sec=0.5):
    last_error = None
    for attempt_index in range(max_attempts):
        try:
            return callable_fn()
        except Exception as error:  # noqa: BLE001
            last_error = error
            if attempt_index == max_attempts - 1:
                break
            delay = base_delay_sec * (2**attempt_index)
            LOGGER.warning(
                "Retrying after provider error",
                extra={
                    "attempt": attempt_index + 1,
                    "delay": delay,
                    "error": str(error),
                },
            )
            time.sleep(delay)
    raise last_error
