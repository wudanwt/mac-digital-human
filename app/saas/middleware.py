from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .settings import saas_settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Small rate limiter with Redis in cloud and process-local fallback in dev."""

    def __init__(self, app) -> None:
        super().__init__(app)
        self.limit = max(1, saas_settings.rate_limit_per_minute)
        self._memory: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()
        self._redis = None
        if saas_settings.worker_backend == "redis":
            try:
                import redis

                self._redis = redis.Redis.from_url(saas_settings.redis_url, decode_responses=True)
            except Exception:
                self._redis = None

    @staticmethod
    def _identity(request: Request) -> str:
        auth = request.headers.get("authorization", "")
        if auth:
            # Hashing is not needed here; the value only forms an internal key.
            return f"token:{hash(auth)}"
        client = request.client.host if request.client else "unknown"
        return f"ip:{client}"

    def _allow_memory(self, key: str) -> bool:
        now = time.time()
        cutoff = now - 60
        with self._lock:
            bucket = self._memory[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.limit:
                return False
            bucket.append(now)
        return True

    def _allow_redis(self, key: str) -> bool:
        try:
            minute = int(time.time() // 60)
            redis_key = f"saas:rate:{key}:{minute}"
            pipe = self._redis.pipeline(transaction=True)
            pipe.incr(redis_key)
            pipe.expire(redis_key, 70)
            count, _ = pipe.execute()
            return int(count) <= self.limit
        except Exception:
            return self._allow_memory(key)

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/") and request.url.path not in {"/api/saas/health"}:
            key = self._identity(request)
            allowed = self._allow_redis(key) if self._redis is not None else self._allow_memory(key)
            if not allowed:
                return JSONResponse(status_code=429, content={"detail": "Too many requests"})
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response
