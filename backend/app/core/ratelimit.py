"""Small fixed-window rate limiter for credential endpoints (per client IP, per process).

Enough for a single API process. With several replicas the limit is per replica; a shared
store (Redis or a database table) would be needed for a global limit.
"""

import time
from collections import defaultdict
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request

from app.core.errors import AppError


class TooManyRequests(AppError):
    status_code = 429
    code = "rate_limited"


_hits: dict[tuple[str, str], list[float]] = defaultdict(list)


def reset() -> None:
    """Test hook."""
    _hits.clear()


def limit(
    name: str, max_requests: int, window_seconds: float
) -> Callable[[Request], Coroutine[Any, Any, None]]:
    async def dependency(request: Request) -> None:
        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        key = (name, ip)
        recent = [t for t in _hits[key] if now - t < window_seconds]
        if len(recent) >= max_requests:
            retry = int(window_seconds - (now - recent[0])) + 1
            _hits[key] = recent
            raise TooManyRequests(
                f"Too many {name} attempts; try again in {retry} seconds",
                {"retry_after_seconds": retry},
            )
        recent.append(now)
        _hits[key] = recent

    return dependency
