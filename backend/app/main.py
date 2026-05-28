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
    carrier_packet,
)

from app.models.user import User
from app.models.organization import Organization
from app.models.claim import Claim
from app.models.upload_history import UploadHistory
from app.models.account_profile import AccountProfile

load_dotenv()

Base.metadata.create_all(bind=engine)

app = FastAPI(title="LossQ API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
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

@app.get("/version")
def version():
    return {"version": "carrier-packet-v2-6e80c7b"}

@app.get("/")
def root():
    return {"message": "LossQ API running", "version": "carrier-packet-live"}