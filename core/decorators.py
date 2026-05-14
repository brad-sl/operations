from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_log, after_log
from functools import wraps
from logging import getLogger
import asyncio

logger = getLogger(__name__)

def async_retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type(Exception),
    before=before_log(logger, logging.INFO),
    after=after_log(logger, logging.WARNING),
):
    """
    Decorator for async functions with exponential backoff retry.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await retry(
                stop=stop,
                wait=wait,
                retry=retry,
                before=before,
                after=after,
            )(func)(*args, **kwargs)
        return wrapper
    return decorator

# Sync version for non-async
def retry_sync(*args, **kwargs):
    return retry(*args, **kwargs)
