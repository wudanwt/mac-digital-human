from __future__ import annotations

import hashlib
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .settings import saas_settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiter with Redis in cloud and process-local fallback in development."""

    # Frequent, advisory UI polling must not consume the same allowance as
    # interactive API calls such as saving a course. Keep it rate-limited, but
    # isolate its counter so a stuck or duplicated browser tab cannot block
    # writes for the signed-in user.
    _POLLING_PATHS = {"/api/saas/workers/status", "/api/saas/jobs"}
    _POLLING_PREFIXES = (
        "/api/saas/jobs/",
        "/api/saas/avatar-matting/",
        "/api/saas/course-tools/speech-previews/",
    )
    _MEDIA_PREFIXES = (
        "/api/saas/assets/",
        "/api/saas/course-tools/ppt/",
    )
    _WORKER_PREFIX = "/api/saas/internal/render/"

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
            digest = hashlib.sha256(auth.encode("utf-8")).hexdigest()[:32]
            return f"token:{digest}"
        client = request.client.host if request.client else "unknown"
        return f"ip:{client}"

    @classmethod
    def _traffic_class(cls, request: Request) -> str:
        path = request.url.path
        if path.startswith(cls._WORKER_PREFIX):
            return "worker"
        if request.method == "GET" and path.startswith(cls._MEDIA_PREFIXES):
            return "media"
        if request.method == "GET" and (
            path in cls._POLLING_PATHS or path.startswith(cls._POLLING_PREFIXES)
        ):
            return "poll"
        return "interactive"

    @classmethod
    def _bucket_key(cls, request: Request) -> str:
        traffic_class = cls._traffic_class(request)
        return f"{traffic_class}:{cls._identity(request)}"

    def _limit_for(self, traffic_class: str) -> int:
        if traffic_class == "media":
            return max(self.limit * 10, 1200)
        if traffic_class == "worker":
            return max(self.limit * 5, 600)
        if traffic_class == "poll":
            return max(self.limit * 3, 360)
        return self.limit

    def _allow_memory(self, key: str, limit: int) -> bool:
        now = time.time()
        cutoff = now - 60
        with self._lock:
            bucket = self._memory[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
        return True

    def _allow_redis(self, key: str, limit: int) -> bool:
        try:
            minute = int(time.time() // 60)
            redis_key = f"saas:rate:{key}:{minute}"
            pipe = self._redis.pipeline(transaction=True)
            pipe.incr(redis_key)
            pipe.expire(redis_key, 70)
            count, _ = pipe.execute()
            return int(count) <= limit
        except Exception:
            return self._allow_memory(key, limit)

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/") and request.url.path not in {"/api/saas/health"}:
            traffic_class = self._traffic_class(request)
            key = self._bucket_key(request)
            limit = self._limit_for(traffic_class)
            allowed = (
                self._allow_redis(key, limit)
                if self._redis is not None
                else self._allow_memory(key, limit)
            )
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests"},
                    headers={"Retry-After": "60"},
                )
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        # Voice recording is a first-party feature of the digital-human UI.
        # Keep other sensitive capabilities disabled while allowing the page
        # itself to request microphone access from the browser.
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(self), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; "
            "connect-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
        )
        if saas_settings.is_production:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response
