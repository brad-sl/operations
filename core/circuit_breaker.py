import time
from typing import Optional
from dataclasses import dataclass

@dataclass
class CircuitBreakerState:
    failure_count: int = 0
    last_failure_time: Optional[float] = None
    state: str = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        reset_timeout: int = 300,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.reset_timeout = reset_timeout
        self.state = CircuitBreakerState()

    def call(self, func, *args, **kwargs):
        if self.state.state == "OPEN":
            if time.time() - self.state.last_failure_time > self.recovery_timeout:
                self.state.state = "HALF_OPEN"
            else:
                raise Exception("Circuit breaker open")
        
        try:
            result = func(*args, **kwargs)
            if self.state.state == "HALF_OPEN":
                self.state.state = "CLOSED"
                self.state.failure_count = 0
            return result
        except Exception as e:
            self.state.failure_count += 1
            self.state.last_failure_time = time.time()
            if self.state.failure_count >= self.failure_threshold:
                self.state.state = "OPEN"
            raise

    def success(self):
        self.state.failure_count = 0
        if self.state.state == "HALF_OPEN":
            self.state.state = "CLOSED"
