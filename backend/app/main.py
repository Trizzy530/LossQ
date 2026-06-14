import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.security_middleware import SecurityHeadersMiddleware, TrustedHostGuardMiddleware, SimpleRateLimitMiddleware
from app.routes import (
    auth,
    upload,
    upload_v2,
    claims,    
    summary,
    upload_history,
    reports,
    admin,
    analytics,
    copilot,
    renewal,
    account_profile,
    timeline,
    carrier_packet,
    admin_users,
    submission_builder,
    audit_logs,
    billing,
    platform_admin,
)

from app.models.user import User
from app.models.organization import Organization
from app.models.claim import Claim
from app.models.upload_history import UploadHistory
from app.models.account_profile import AccountProfile
from app.models.audit_log import AuditLog

load_dotenv()

# LOSSQ_CORS_LOCKDOWN_V1
# Production default only allows the real LossQ domains and the current Vercel production project.
DEFAULT_ALLOWED_ORIGINS = "https://www.lossq.com,https://lossq.com,https://loss-q.vercel.app"

ALLOWED_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv("ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS).split(",")
    if origin.strip()
]

ALLOWED_LOSSQ_ORIGINS = set(ALLOWED_ORIGINS)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="LossQ API", redirect_slashes=False)

# Security Phase 1 middleware
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(TrustedHostGuardMiddleware)
app.add_middleware(SimpleRateLimitMiddleware)

def lossq_origin_allowed(origin: str | None) -> bool:
    if not origin:
        return False
    return origin.rstrip("/") in ALLOWED_LOSSQ_ORIGINS

def lossq_emergency_cors_headers(origin: str | None) -> dict:
    if not lossq_origin_allowed(origin):
        return {}
    clean_origin = origin.rstrip("/")
    return {
        "Access-Control-Allow-Origin": clean_origin,
        "Vary": "Origin",
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Authorization, Content-Type, Accept, Origin, X-Requested-With",
        "Access-Control-Max-Age": "86400",
    }

@app.middleware("http")
async def lossq_emergency_cors_middleware(request: Request, call_next):
    origin = request.headers.get("origin")
    headers = lossq_emergency_cors_headers(origin)
    if request.method == "OPTIONS":
        return Response(status_code=200, headers=headers)
    try:
        response = await call_next(request)
    except Exception as exc:
        print(f"LOSSQ_BACKEND_ERROR: {type(exc).__name__}: {exc}")
        response = Response(content='{"detail":"Internal server error"}', status_code=500, media_type="application/json")
    for key, value in headers.items():
        response.headers[key] = value
    return response
# Production CORS - must stay before route registration.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
    max_age=86400,
)

app.include_router(auth.router)
app.include_router(platform_admin.router)
app.include_router(upload.router)
app.include_router(upload_v2.router)
app.include_router(claims.router)
app.include_router(summary.router)
app.include_router(upload_history.router)
app.include_router(reports.router)
app.include_router(admin.router)
app.include_router(analytics.router)

app.include_router(copilot.router)
app.include_router(renewal.router)
app.include_router(account_profile.router)
app.include_router(timeline.router)
app.include_router(carrier_packet.router)
app.include_router(admin_users.router)
app.include_router(submission_builder.router)
app.include_router(audit_logs.router)
app.include_router(audit_logs.compat_router)
app.include_router(billing.router)

@app.get("/version")
def version():
    return {"version": "billing-stripe-v1"}

@app.get("/")
def root():
    return {"message": "LossQ API running", "version": "billing-stripe-live"}
