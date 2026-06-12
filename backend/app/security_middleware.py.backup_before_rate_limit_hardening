
import os
import time
from collections import defaultdict, deque
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


def parse_csv_env(name: str, fallback: str = ""):
    raw = os.getenv(name, fallback)
    return [item.strip() for item in raw.split(",") if item.strip()]


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["X-XSS-Protection"] = "0"

        # Only add HSTS over HTTPS.
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response


class TrustedHostGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        allowed_hosts = parse_csv_env(
            "ALLOWED_HOSTS",
            "lossq-production.up.railway.app,www.lossq.com,lossq.com,localhost,127.0.0.1",
        )

        host = request.headers.get("host", "").split(":")[0].lower()

        if host and host not in [item.lower() for item in allowed_hosts]:
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid host header."},
            )

        return await call_next(request)


class SimpleRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limit: int = 120, window_seconds: int = 60):
        super().__init__(app)
        self.limit = int(os.getenv("RATE_LIMIT_PER_MINUTE", str(limit)))
        self.window_seconds = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", str(window_seconds)))
        self.requests = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path.lower()

        # Rate limit sensitive/auth/upload/API routes.
        protected_prefixes = (
            "/auth/login",
            "/auth/register",
            "/auth/forgot-password",
            "/auth/reset-password",
            "/upload",
            "/api",
            "/platform-admin",
        )

        if not path.startswith(protected_prefixes):
            return await call_next(request)

        forwarded_for = request.headers.get("x-forwarded-for", "")
        client_ip = forwarded_for.split(",")[0].strip() if forwarded_for else ""
        if not client_ip and request.client:
            client_ip = request.client.host

        key = f"{client_ip}:{path}"
        now = time.time()
        bucket = self.requests[key]

        while bucket and bucket[0] <= now - self.window_seconds:
            bucket.popleft()

        if len(bucket) >= self.limit:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please wait and try again."},
            )

        bucket.append(now)
        return await call_next(request)
