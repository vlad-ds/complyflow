"""
Retry and timeout utilities for LLM calls.
"""

import functools
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Callable, ParamSpec, TypeVar

from api.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")
P = ParamSpec("P")


class LLMTimeoutError(Exception):
    """Raised when an LLM call times out."""

    def __init__(self, timeout_seconds: float, operation: str = "LLM call"):
        self.timeout_seconds = timeout_seconds
        self.operation = operation
        super().__init__(f"{operation} timed out after {timeout_seconds}s")


class LLMRetryExhaustedError(Exception):
    """Raised when all retry attempts have been exhausted."""

    def __init__(self, attempts: int, last_error: Exception, operation: str = "LLM call"):
        self.attempts = attempts
        self.last_error = last_error
        self.operation = operation
        super().__init__(
            f"{operation} failed after {attempts} attempts. Last error: {type(last_error).__name__}: {last_error}"
        )


def llm_retry(
    timeout_seconds: float = 120.0,
    max_retries: int = 3,
    retry_delay_seconds: float = 2.0,
    retryable_exceptions: tuple = (Exception,),
):
    """
    Decorator that adds timeout and retry logic to LLM calls.

    Args:
        timeout_seconds: Maximum time to wait for each attempt
        max_retries: Number of retry attempts
        retry_delay_seconds: Initial delay between retries (doubles each retry)
        retryable_exceptions: Exception types that should trigger a retry

    Usage:
        @llm_retry(timeout_seconds=120, max_retries=3)
        def call_openai(prompt: str) -> str:
            return client.chat.completions.create(...)
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            operation = func.__name__
            last_error: Exception | None = None
            delay = retry_delay_seconds

            for attempt in range(1, max_retries + 1):
                try:
                    logger.info(f"{operation} attempt {attempt}/{max_retries}")

                    # Use ThreadPoolExecutor for timeout on sync functions
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(func, *args, **kwargs)
                        try:
                            result = future.result(timeout=timeout_seconds)
                            if attempt > 1:
                                logger.info(f"{operation} succeeded on attempt {attempt}")
                            return result
                        except FuturesTimeoutError:
                            future.cancel()
                            raise LLMTimeoutError(timeout_seconds, operation)

                except LLMTimeoutError as e:
                    last_error = e
                    logger.warning(
                        f"{operation} timed out on attempt {attempt}/{max_retries} "
                        f"(timeout={timeout_seconds}s)"
                    )

                except retryable_exceptions as e:
                    last_error = e
                    logger.warning(
                        f"{operation} failed on attempt {attempt}/{max_retries}: "
                        f"{type(e).__name__}: {e}"
                    )

                # Don't sleep after the last attempt
                if attempt < max_retries:
                    logger.info(f"Retrying in {delay}s...")
                    time.sleep(delay)
                    delay *= 2  # Exponential backoff

            # All attempts exhausted
            raise LLMRetryExhaustedError(max_retries, last_error, operation)

        return wrapper
    return decorator
