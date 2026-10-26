from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.loss_run_request import LossRunRequest, LossRunRequestEvent
from app.role_utils import require_permission
from app.services.audit import record_audit_event
from app.services.loss_run_requests import REQUEST_STATUSES, needs_attention, validate_transition


router = APIRouter(prefix="/loss-run-requests", tags=["Loss Run Requests"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class RequestCreate(BaseModel):
    insured_name: str = Field(min_length=1, max_length=200)
    carrier_name: str = Field(min_length=1, max_length=200)
    policy_number: str | None = Field(default=None, max_length=100)
    contact_name: str | None = Field(default=None, max_length=200)
    contact_email: EmailStr | None = None
    status: str = "draft"
    authorization_received: bool = False
    requested_at: datetime | None = None
    next_follow_up_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=5000)


class RequestUpdate(BaseModel):
    status: str | None = None
    authorization_received: bool | None = None
    next_follow_up_at: datetime | None = None
    received_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=5000)
    event_note: str | None = Field(default=None, max_length=1000)


def _clean(value: Any) -> str | None:
    cleaned = str(value or "").strip()
    return cleaned or None


def _serialize(row: LossRunRequest, now: datetime | None = None) -> dict[str, Any]:
    return {
        "id": row.id,
        "insured_name": row.insured_name,
        "carrier_name": row.carrier_name,
        "policy_number": row.policy_number,
        "contact_name": row.contact_name,
        "contact_email": row.contact_email,
        "status": row.status,
        "authorization_received": bool(row.authorization_received),
        "requested_at": row.requested_at,
        "next_follow_up_at": row.next_follow_up_at,
        "received_at": row.received_at,
        "notes": row.notes,
        "needs_attention": needs_attention(row.status, row.next_follow_up_at, now=now),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _get_request(db: Session, organization_id: int, request_id: int) -> LossRunRequest:
    row = (
        db.query(LossRunRequest)
        .filter(
            LossRunRequest.id == request_id,
            LossRunRequest.organization_id == organization_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Loss-run request not found.")
    return row


def _add_event(
    db: Session,
    *,
    row: LossRunRequest,
    user_id: int | None,
    event_type: str,
    from_status: str | None = None,
    to_status: str | None = None,
    note: str | None = None,
) -> None:
    db.add(
        LossRunRequestEvent(
            organization_id=row.organization_id,
            request_id=row.id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            note=_clean(note),
            created_by_user_id=user_id,
        )
    )


@router.get("")
def list_requests(
    status: str | None = Query(default=None),
    attention_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("read")),
):
    if status is not None and status not in REQUEST_STATUSES:
        raise HTTPException(status_code=422, detail="Unknown loss-run request status.")
    query = db.query(LossRunRequest).filter(
        LossRunRequest.organization_id == current_user["organization_id"]
    )
    if status:
        query = query.filter(LossRunRequest.status == status)
    rows = query.order_by(LossRunRequest.updated_at.desc(), LossRunRequest.id.desc()).all()
    now = datetime.now(timezone.utc)
    items = [_serialize(row, now=now) for row in rows]
    if attention_only:
        items = [item for item in items if item["needs_attention"]]
    return {
        "items": items,
        "counts": {
            "total": len(rows),
            "attention": sum(1 for row in rows if needs_attention(row.status, row.next_follow_up_at, now=now)),
            "received": sum(1 for row in rows if row.status in {"received", "processing"}),
            "completed": sum(1 for row in rows if row.status == "completed"),
        },
    }


@router.post("", status_code=201)
def create_request(
    payload: RequestCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("edit")),
):
    if payload.status not in REQUEST_STATUSES:
        raise HTTPException(status_code=422, detail="Unknown loss-run request status.")
    if payload.status not in {"draft", "authorization_needed", "requested"}:
        raise HTTPException(status_code=422, detail="New requests must start as draft, authorization_needed, or requested.")
    if payload.status == "requested" and not payload.authorization_received:
        raise HTTPException(status_code=422, detail="Confirm authorization before marking a request as requested.")
    row = LossRunRequest(
        organization_id=current_user["organization_id"],
        insured_name=payload.insured_name.strip(),
        carrier_name=payload.carrier_name.strip(),
        policy_number=_clean(payload.policy_number),
        contact_name=_clean(payload.contact_name),
        contact_email=str(payload.contact_email) if payload.contact_email else None,
        status=payload.status,
        authorization_received=payload.authorization_received,
        requested_at=payload.requested_at or (datetime.now(timezone.utc) if payload.status == "requested" else None),
        next_follow_up_at=payload.next_follow_up_at,
        notes=_clean(payload.notes),
        created_by_user_id=current_user.get("user_id"),
    )
    db.add(row)
    db.flush()
    _add_event(db, row=row, user_id=current_user.get("user_id"), event_type="created", to_status=row.status)
    db.commit()
    db.refresh(row)
    record_audit_event(
        db,
        current_user=current_user,
        action="loss_run_request_created",
        resource_type="loss_run_request",
        resource_id=str(row.id),
        details={"insured_name": row.insured_name, "carrier_name": row.carrier_name, "status": row.status},
    )
    return _serialize(row)


@router.patch("/{request_id}")
def update_request(
    request_id: int,
    payload: RequestUpdate = Body(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("edit")),
):
    row = _get_request(db, current_user["organization_id"], request_id)
    original_status = row.status
    target_status = payload.status or row.status
    try:
        validate_transition(original_status, target_status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    authorization = row.authorization_received if payload.authorization_received is None else payload.authorization_received
    if target_status == "requested" and not authorization:
        raise HTTPException(status_code=422, detail="Confirm authorization before marking a request as requested.")

    row.status = target_status
    row.authorization_received = authorization
    if "next_follow_up_at" in payload.model_fields_set:
        row.next_follow_up_at = payload.next_follow_up_at
    if "received_at" in payload.model_fields_set:
        row.received_at = payload.received_at
    if "notes" in payload.model_fields_set:
        row.notes = _clean(payload.notes)
    if target_status == "requested" and row.requested_at is None:
        row.requested_at = datetime.now(timezone.utc)
    if target_status in {"received", "processing", "completed"} and row.received_at is None:
        row.received_at = datetime.now(timezone.utc)

    event_type = "status_changed" if target_status != original_status else "updated"
    _add_event(
        db,
        row=row,
        user_id=current_user.get("user_id"),
        event_type=event_type,
        from_status=original_status,
        to_status=target_status,
        note=payload.event_note,
    )
    db.commit()
    db.refresh(row)
    record_audit_event(
        db,
        current_user=current_user,
        action="loss_run_request_updated",
        resource_type="loss_run_request",
        resource_id=str(row.id),
        details={"from_status": original_status, "to_status": target_status},
    )
    return _serialize(row)


@router.get("/{request_id}/events")
def request_events(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("read")),
):
    _get_request(db, current_user["organization_id"], request_id)
    rows = (
        db.query(LossRunRequestEvent)
        .filter(
            LossRunRequestEvent.request_id == request_id,
            LossRunRequestEvent.organization_id == current_user["organization_id"],
        )
        .order_by(LossRunRequestEvent.created_at.desc(), LossRunRequestEvent.id.desc())
        .all()
    )
    return {"items": [{
        "id": row.id,
        "event_type": row.event_type,
        "from_status": row.from_status,
        "to_status": row.to_status,
        "note": row.note,
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at,
    } for row in rows]}
