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
from app.routes.auth import get_current_user, require_admin_or_owner


router = APIRouter(prefix="/audit", tags=["Audit Log"])

# Make sure the table exists even if an older main.py did not import the model before create_all.
Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def safe_get(obj: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if hasattr(obj, name):
            value = getattr(obj, name)
            if value is not None:
                return value
    return default


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


def normalize_audit_row(row: AuditLog) -> dict:
    return {
        "id": row.id,
        "created_at": iso_or_string(row.created_at),
        "user_email": row.user_email or "",
        "action": row.action,
        "resource_type": row.resource_type or "",
        "resource_id": row.resource_id or "",
        "details": parse_details(row.details),
    }


def upload_history_event(row: Any) -> dict:
    filename = safe_get(row, "filename", "file_name", "original_filename", "name", default="")
    policy_number = safe_get(row, "policy_number", "policy", default="")
    account_number = safe_get(row, "account_number", "customer_number", default="")
    claims_saved = safe_get(row, "claims_saved", "claim_count", "claims_count", default=None)
    created_at = safe_get(row, "created_at", "uploaded_at", "timestamp", default=None)
    user_email = safe_get(row, "user_email", "uploaded_by_email", "email", default="")

    details = {
        "filename": filename,
        "policy_number": policy_number,
        "account_number": account_number,
    }

    if claims_saved is not None:
        details["claims_saved"] = claims_saved

    return {
        "id": f"upload-{safe_get(row, 'id', default='')}",
        "created_at": iso_or_string(created_at),
        "user_email": user_email,
        "action": "loss_run_uploaded",
        "resource_type": "upload",
        "resource_id": str(safe_get(row, "id", default="")),
        "details": details,
    }


def claim_event(row: Any) -> dict:
    created_at = safe_get(row, "created_at", "uploaded_at", "updated_at", default=None)
    claim_number = safe_get(row, "claim_number", "claim_id", default="")
    policy_number = safe_get(row, "policy_number", default="")
    total_incurred = safe_get(row, "total_incurred", "incurred_amount", default=None)

    return {
        "id": f"claim-{safe_get(row, 'id', default='')}",
        "created_at": iso_or_string(created_at),
        "user_email": "",
        "action": "claim_record_available",
        "resource_type": "claim",
        "resource_id": str(safe_get(row, "id", default=claim_number)),
        "details": {
            "claim_number": claim_number,
            "policy_number": policy_number,
            "total_incurred": total_incurred,
        },
    }


def create_audit_event(
    db: Session,
    current_user: Any,
    action: str,
    resource_type: str = "",
    resource_id: str = "",
    details: Any = None,
    request: Request | None = None,
) -> AuditLog:
    if details is None:
        details_text = None
    elif isinstance(details, str):
        details_text = details
    else:
        details_text = json.dumps(details, default=str)

    event = AuditLog(
        organization_id=getattr(current_user, "organization_id", None),
        user_id=getattr(current_user, "id", None),
        user_email=getattr(current_user, "email", None),
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id or ""),
        details=details_text,
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )

    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def build_fallback_events(db: Session, current_user: Any, limit: int) -> list[dict]:
    """
    If no formal AuditLog rows exist yet, build useful activity from existing uploads and claims.
    This makes the Audit Log useful immediately without breaking the current upload pipeline.
    """

    events: list[dict] = []
    org_id = getattr(current_user, "organization_id", None)

    try:
        upload_query = db.query(UploadHistory)

        if hasattr(UploadHistory, "organization_id") and org_id is not None:
            upload_query = upload_query.filter(UploadHistory.organization_id == org_id)
        elif hasattr(UploadHistory, "user_id") and getattr(current_user, "id", None) is not None:
            upload_query = upload_query.filter(UploadHistory.user_id == current_user.id)

        if hasattr(UploadHistory, "created_at"):
            upload_query = upload_query.order_by(UploadHistory.created_at.desc())
        elif hasattr(UploadHistory, "uploaded_at"):
            upload_query = upload_query.order_by(UploadHistory.uploaded_at.desc())
        elif hasattr(UploadHistory, "id"):
            upload_query = upload_query.order_by(UploadHistory.id.desc())

        for row in upload_query.limit(limit).all():
            events.append(upload_history_event(row))

    except Exception:
        pass

    if len(events) < limit:
        try:
            claim_query = db.query(Claim)

            if hasattr(Claim, "organization_id") and org_id is not None:
                claim_query = claim_query.filter(Claim.organization_id == org_id)

            if hasattr(Claim, "created_at"):
                claim_query = claim_query.order_by(Claim.created_at.desc())
            elif hasattr(Claim, "id"):
                claim_query = claim_query.order_by(Claim.id.desc())

            for row in claim_query.limit(max(0, limit - len(events))).all():
                events.append(claim_event(row))

        except Exception:
            pass

    events.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return events[:limit]


@router.get("/events")
def get_audit_events(
    limit: int = Query(100, ge=1, le=250),
    current_user=Depends(require_admin_or_owner),
    db: Session = Depends(get_db),
):
    query = db.query(AuditLog)

    if getattr(current_user, "organization_id", None) is not None:
        query = query.filter(AuditLog.organization_id == current_user.organization_id)

    rows = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).all()
    events = [normalize_audit_row(row) for row in rows]

    if not events:
        events = build_fallback_events(db, current_user, limit)

    return {
        "events": events,
        "count": len(events),
        "source": "audit_logs" if rows else "derived_from_existing_activity",
    }


@router.get("/logs")
def get_audit_logs(
    limit: int = Query(100, ge=1, le=250),
    current_user=Depends(require_admin_or_owner),
    db: Session = Depends(get_db),
):
    return get_audit_events(limit=limit, current_user=current_user, db=db)


@router.post("/events")
def record_audit_event(
    payload: dict,
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    event = create_audit_event(
        db=db,
        current_user=current_user,
        action=str(payload.get("action") or "custom_event"),
        resource_type=str(payload.get("resource_type") or ""),
        resource_id=str(payload.get("resource_id") or ""),
        details=payload.get("details") or {},
        request=request,
    )

    return {"event": normalize_audit_row(event)}
