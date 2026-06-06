import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.routes import (
    auth,
    upload,
    claims,
    summary,
    upload_history,
    reports,
    admin,
    analytics,
    demo,
    copilot,
    renewal,
    account_profile,
    timeline,
    carrier_packet,
    admin_users,
    submission_builder,
    audit_logs,
    billing,
)

from app.models.user import User
from app.models.organization import Organization
from app.models.claim import Claim
from app.models.upload_history import UploadHistory
from app.models.account_profile import AccountProfile
from app.models.audit_log import AuditLog

load_dotenv()

Base.metadata.create_all(bind=engine)

app = FastAPI(title="LossQ API", redirect_slashes=False)



ALLOWED_LOSSQ_ORIGINS = {
    "https://lossq.com",
    "https://www.lossq.com",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
}

def lossq_emergency_cors_headers(origin: str | None) -> dict:
    if not origin:
        return {}
    allowed = origin in ALLOWED_LOSSQ_ORIGINS or (origin.startswith("https://") and origin.endswith(".vercel.app"))
    if not allowed:
        return {}
    return {
        "Access-Control-Allow-Origin": origin,
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
        response = Response(content=f'{{"detail":"Internal server error","error":"{str(exc)}"}}', status_code=500, media_type="application/json")
    for key, value in headers.items():
        response.headers[key] = value
    return response
# Production CORS - must stay before route registration.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://lossq.com",
        "https://www.lossq.com",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(claims.router)
app.include_router(summary.router)
app.include_router(upload_history.router)
app.include_router(reports.router)
app.include_router(admin.router)
app.include_router(analytics.router)
app.include_router(demo.router)
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
