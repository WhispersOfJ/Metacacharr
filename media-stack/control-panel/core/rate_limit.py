"""Simple in-memory rate limiter — per-IP sliding-window counters. No external
dependency (avoids adding slowai/redis to a LAN-only home stack). Sliding-window
rather than fixed-window to avoid the burst-at-boundary problem.

Not distributed (in-process only), which is fine for a single-worker uvicorn
deployment — this panel never runs under gunicorn or multiple workers.
"""

import time
from collections import defaultdict
from typing import Callable

from fastapi import HTTPException, Request


def rate_limit(*, max_requests: int, window_seconds: int) -> Callable:
    """Returns a FastAPI dependency that limits `max_requests` per
    `window_seconds` per client IP. Uses a sliding window (not fixed
    bucket) to close the classic boundary burst.

    Usage:
        @router.post("/api/auth/login")
        def login(
            payload: LoginRequest,
            response: Response,
            db: Session = Depends(get_db),
            _rate: None = Depends(rate_limit(max_requests=5, window_seconds=60)),
        ):
    """
    # defaultdict(list) — one list of float timestamps per IP.
    buckets: dict[str, list[float]] = defaultdict(list)

    def _check(request: Request) -> None:
        now = time.monotonic()
        ip = request.client.host if request.client else "unknown"
        window = buckets[ip]

        # Drop timestamps older than the window
        cutoff = now - window_seconds
        while window and window[0] < cutoff:
            window.pop(0)

        if len(window) >= max_requests:
            retry_after = int(window[0] + window_seconds - now) + 1
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Retry after {retry_after}s.",
                headers={"Retry-After": str(retry_after)},
            )

        window.append(now)

    return _check