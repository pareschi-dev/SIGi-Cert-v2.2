from __future__ import annotations

import time
from functools import wraps
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def retry(max_attempts: int = 3, delay_seconds: int = 5, backoff: float = 1.0):
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            attempts = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except Exception:
                    attempts += 1
                    if attempts >= max_attempts:
                        raise
                    time.sleep(delay_seconds * (backoff ** (attempts - 1)))
        return wrapper  # type: ignore[return-value]
    return decorator
