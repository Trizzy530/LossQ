from __future__ import annotations
import json
from datetime import datetime
from typing import Any
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from app.database import Base, engine, SessionLocal
from app.models.audit_log import AuditLog
from app.models.claim import Claim
from app.models.upload_history import UploadHistory
from app.routes.auth import get_current_user
from app.services.audit_service import write_audit_event

router = APIRouter(prefix="/audit", tags=["Audit Log"])
compat_router = APIRouter(tags=["Audit Log Compatibility"])
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def actor_value(current_user: Any, key: str, default: Any = None) -> Any:
    return current_user.get(key, default) if isinstance(current_user, dict) else getattr(current_user, key, default)

def iso_or_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    try:
        return value.isoformat()
    except Exception:
        return str(value)

def parse_details(value: Any) -> Any:
    if value is None:
        return {}
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return str(value)

def safe_get(obj: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if hasattr(obj, name):
            value = getattr(obj, name)
            if value is not None:
                return value
    return default

def normalize_audit_row(row: AuditLog) -> dict:
    return {"id": row.id, "created_at": iso_or_string(row.created_at), "user_email": row.user_email or "", "action": row.action, "resource_type": row.resource_type or "", "resource_id": row.resource_id or "", "details": parse_details(row.details)}

def upload_history_event(row: Any) -> dict:
    return {"id": f"upload-{safe_get(row, 'id', default='')}", "created_at": iso_or_string(safe_get(row, "created_at", "uploaded_at", "timestamp")), "user_email": safe_get(row, "user_email", "uploaded_by_email", "email", default=""), "action": "loss_run_uploaded", "resource_type": "upload", "resource_id": str(safe_get(row, "id", default="")), "details": {"filename": safe_get(row, "filename", "file_name", "original_filename", "name", default=""), "policy_number": safe_get(row, "policy_number", "policy", default=""), "account_number": safe_get(row, "account_number", "customer_number", default=""), "claims_saved": safe_get(row, "claims_saved", "claim_count", "claims_count", default=None)}}

def claim_event(row: Any) -> dict:
    return {"id": f"claim-{safe_get(row, 'id', default='')}", "created_at": iso_or_string(safe_get(row, "created_at", "uploaded_at", "updated_at")), "user_email": "", "action": "claim_record_saved", "resource_type": "claim", "resource_id": str(safe_get(row, "id", default=safe_get(row, "claim_number", default=""))), "details": {"claim_number": safe_get(row, "claim_number", "claim_id", default=""), "policy_number": safe_get(row, "policy_number", default=""), "total_incurred": safe_get(row, "total_incurred", "incurred_amount", default=None)}}

def org_filter(model: Any, current_user: Any):
    org_id = actor_value(current_user, "organization_id")
    if org_id is not None and hasattr(model, "organization_id"):
        return model.organization_id == org_id
    return None

def build_fallback_events(db: Session, current_user: Any, limit: int) -> list[dict]:
    events = []
    try:
        q = db.query(UploadHistory)
        f = org_filter(UploadHistory, current_user)
        if f is not None:
            q = q.filter(f)
        if hasattr(UploadHistory, "created_at"):
            q = q.order_by(UploadHistory.created_at.desc())
        elif hasattr(UploadHistory, "uploaded_at"):
            q = q.order_by(UploadHistory.uploaded_at.desc())
        elif hasattr(UploadHistory, "id"):
            q = q.order_by(UploadHistory.id.desc())
        events += [upload_history_event(row) for row in q.limit(limit).all()]
    except Exception as exc:
        events.append({"id":"upload-fallback-error","created_at":"","user_email":"","action":"audit_upload_history_unavailable","resource_type":"system","resource_id":"","details":{"error":str(exc)}})
    if len(events) < limit:
        try:
            q = db.query(Claim)
            f = org_filter(Claim, current_user)
            if f is not None:
                q = q.filter(f)
            if hasattr(Claim, "created_at"):
                q = q.order_by(Claim.created_at.desc())
            elif hasattr(Claim, "id"):
                q = q.order_by(Claim.id.desc())
            events += [claim_event(row) for row in q.limit(limit-len(events)).all()]
        except Exception as exc:
            events.append({"id":"claim-fallback-error","created_at":"","user_email":"","action":"audit_claim_history_unavailable","resource_type":"system","resource_id":"","details":{"error":str(exc)}})
    events.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return events[:limit]

def payload(limit: int, current_user: Any, db: Session) -> dict:
    q = db.query(AuditLog)
    org_id = actor_value(current_user, "organization_id")
    if org_id is not None:
        q = q.filter(AuditLog.organization_id == org_id)
    rows = q.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).all()
    events = [normalize_audit_row(row) for row in rows]
    if not events:
        events = build_fallback_events(db, current_user, limit)
    return {"events": events, "count": len(events), "source": "audit_logs" if rows else "derived_from_existing_uploads_and_claims"}

@router.get("/events")
def get_audit_events(limit: int = Query(100, ge=1, le=250), current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return payload(limit, current_user, db)

@router.get("/logs")
def get_audit_logs(limit: int = Query(100, ge=1, le=250), current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return payload(limit, current_user, db)

@router.post("/events")
def record_audit_event(payload_body: dict, request: Request, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    event = write_audit_event(db, current_user, str(payload_body.get("action") or "custom_event"), str(payload_body.get("resource_type") or ""), str(payload_body.get("resource_id") or ""), payload_body.get("details") or {}, request)
    return {"event": normalize_audit_row(event) if event else None, "saved": bool(event)}

@compat_router.get("/audit-log")
def get_audit_log_compat(limit: int = Query(100, ge=1, le=250), current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return payload(limit, current_user, db)

@compat_router.get("/auth/audit-log")
def get_auth_audit_log_compat(limit: int = Query(100, ge=1, le=250), current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return payload(limit, current_user, db)
