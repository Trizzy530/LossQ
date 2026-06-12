
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
        # LOSSQ_TRUSTED_HOST_LOCKDOWN_V1
        # Production default only allows the real backend host and LossQ domains.
        # Add local development hosts through ALLOWED_HOSTS only when running development.
        allowed_hosts = parse_csv_env(
            "ALLOWED_HOSTS",
            "lossq-production.up.railway.app,www.lossq.com,lossq.com",
        )

        host = request.headers.get("host", "").split(":")[0].lower()

        if host and host not in [item.lower() for item in allowed_hosts]:
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid host header."},
            )

        return await call_next(request)


class SimpleRateLimitMiddleware(BaseHTTPMiddleware):
    # LOSSQ_RATE_LIMIT_HARDENING_V1
    # Route-specific in-memory rate limits.
    # This protects login, registration, password reset, demo upload, real upload,
    # and platform admin routes without slowing down normal dashboard reads.

    def __init__(self, app, limit: int = 120, window_seconds: int = 60):
        super().__init__(app)

        self.default_limit = int(os.getenv("RATE_LIMIT_PER_MINUTE", str(limit)))
        self.default_window_seconds = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", str(window_seconds)))

        self.route_limits = [
            # path prefix, max requests, window seconds
            ("/auth/login", int(os.getenv("RATE_LIMIT_LOGIN", "10")), 60),
            ("/auth/register", int(os.getenv("RATE_LIMIT_REGISTER", "5")), 300),
            ("/auth/forgot-password", int(os.getenv("RATE_LIMIT_FORGOT_PASSWORD", "5")), 900),
            ("/auth/reset-password", int(os.getenv("RATE_LIMIT_RESET_PASSWORD", "8")), 900),
            ("/auth/accept-invite", int(os.getenv("RATE_LIMIT_ACCEPT_INVITE", "10")), 900),
            ("/auth/verify-password", int(os.getenv("RATE_LIMIT_VERIFY_PASSWORD", "10")), 300),
            ("/auth/change-password", int(os.getenv("RATE_LIMIT_CHANGE_PASSWORD", "10")), 300),

            # Real uploads and upload-v2.
            ("/upload", int(os.getenv("RATE_LIMIT_UPLOAD", "20")), 300),

            # Public demo upload.
            ("/demo/analyze", int(os.getenv("RATE_LIMIT_DEMO_UPLOAD", "10")), 300),

            # Platform admin.
            ("/platform-admin", int(os.getenv("RATE_LIMIT_PLATFORM_ADMIN", "60")), 60),

            # General API fallback if future /api routes are added.
            ("/api", int(os.getenv("RATE_LIMIT_API", str(self.default_limit))), self.default_window_seconds),
        ]

        self.requests = defaultdict(deque)

    def match_limit(self, path: str):
        for prefix, limit, window_seconds in self.route_limits:
            if path.startswith(prefix):
                return int(limit), int(window_seconds), prefix
        return None

    def client_key(self, request: Request, path_group: str) -> str:
        forwarded_for = request.headers.get("x-forwarded-for", "")
        client_ip = forwarded_for.split(",")[0].strip() if forwarded_for else ""

        if not client_ip and request.client:
            client_ip = request.client.host

        if not client_ip:
            client_ip = "unknown"

        return f"{client_ip}:{path_group}"

    async def dispatch(self, request: Request, call_next):
        path = request.url.path.lower()
        matched = self.match_limit(path)

        if not matched:
            return await call_next(request)

        limit, window_seconds, path_group = matched
        key = self.client_key(request, path_group)

        now = time.time()
        bucket = self.requests[key]

        while bucket and bucket[0] <= now - window_seconds:
            bucket.popleft()

        if len(bucket) >= limit:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests. Please wait and try again.",
                    "retry_after_seconds": window_seconds,
                },
                headers={"Retry-After": str(window_seconds)},
            )

        bucket.append(now)
        return await call_next(request)
