"""
Retry utilities with exponential backoff
"""

import time
import random
from typing import Callable, Type, Tuple
from functools import wraps

from utils.logger import setup_logger

logger = setup_logger(__name__)


class RetryException(Exception):
    """Raised when max retries exceeded"""
    pass


def exponential_backoff(
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Callable = None
):
    """
    Decorator for retrying functions with exponential backoff

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exceptions: Tuple of exceptions to catch and retry
        on_retry: Optional callback function called on each retry

    Example:
        @exponential_backoff(max_retries=3, base_delay=2.0)
        def fetch_data():
            return api.get_data()
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            while retries <= max_retries:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    retries += 1
                    if retries > max_retries:
                        logger.error(
                            f"{func.__name__} failed after {max_retries} retries: {e}"
                        )
                        raise RetryException(
                            f"Max retries ({max_retries}) exceeded"
                        ) from e

                    # Calculate delay with exponential backoff and jitter
                    delay = min(base_delay * (2 ** (retries - 1)), max_delay)
                    jitter = random.uniform(0, delay * 0.1)  # Add up to 10% jitter
                    total_delay = delay + jitter

                    logger.warning(
                        f"{func.__name__} failed (attempt {retries}/{max_retries}): {e}. "
                        f"Retrying in {total_delay:.2f}s..."
                    )

                    if on_retry:
                        on_retry(retries, e, total_delay)

                    time.sleep(total_delay)

        return wrapper
    return decorator


def is_rate_limit_error(exception: Exception) -> bool:
    """Check if an exception is a rate limit error"""
    error_message = str(exception).lower()
    rate_limit_indicators = [
        'rate limit',
        'too many requests',
        '429',
        'quota exceeded',
        'throttle'
    ]
    return any(indicator in error_message for indicator in rate_limit_indicators)


def is_network_error(exception: Exception) -> bool:
    """Check if an exception is a network error"""
    error_message = str(exception).lower()
    network_indicators = [
        'connection',
        'timeout',
        'network',
        'unreachable',
        'dns',
        'socket'
    ]
    return any(indicator in error_message for indicator in network_indicators)


def is_auth_error(exception: Exception) -> bool:
    """Check if an exception is an authentication error"""
    error_message = str(exception).lower()
    auth_indicators = [
        'unauthorized',
        'authentication',
        'invalid credentials',
        '401',
        '403',
        'forbidden'
    ]
    return any(indicator in error_message for indicator in auth_indicators)
