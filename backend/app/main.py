import os
from dotenv import load_dotenv
from fastapi import FastAPI
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
)

from app.models.user import User
from app.models.organization import Organization
from app.models.claim import Claim
from app.models.upload_history import UploadHistory
from app.models.account_profile import AccountProfile

Base.metadata.create_all(bind=engine)

app = FastAPI(title="LossQ API")



load_dotenv()

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

allow_origins=[
    FRONTEND_URL,
    "https://loss-q.vercel.app",
    "https://lossq.vercel.app",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
],
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
app.include_router(renewal.router)
app.include_router(account_profile.router)
app.include_router(timeline.router)

@app.get("/")
def root():
    return {"message": "LossQ API running"}