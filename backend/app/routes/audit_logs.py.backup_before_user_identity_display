from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.database import Base, engine, SessionLocal
from app.models.audit_log import AuditLog
from app.routes.auth import get_current_user
from app.services.audit_service import write_audit_event


# This is the route your live Swagger/front-end expects:
# GET /audit-logs/
# GET /audit-logs/summary
router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])

# Compatibility routes for older frontend attempts:
# GET /audit/events
# GET /audit/logs
# GET /audit-log
# GET /auth/audit-log
compat_router = APIRouter(tags=["Audit Logs Compatibility"])


try:
    Base.metadata.create_all(bind=engine)
except Exception:
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def actor_value(current_user: Any, key: str, default: Any = None) -> Any:
    if isinstance(current_user, dict):
        return current_user.get(key, default)
    return getattr(current_user, key, default)


def iso_or_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    try:
        return value.isoformat()
    except Exception:
        return str(value)


def parse_json(value: Any) -> Any:
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


def table_names(db: Session) -> set[str]:
    try:
        return set(inspect(db.bind).get_table_names())
    except Exception:
        return set()


def columns_for(db: Session, table_name: str) -> set[str]:
    try:
        return {col["name"] for col in inspect(db.bind).get_columns(table_name)}
    except Exception:
        return set()


def safe_table_query(
    db: Session,
    table_name: str,
    wanted: list[str],
    limit: int,
    org_id: Any = None,
) -> list[dict]:
    cols = columns_for(db, table_name)
    if not cols:
        return []

    selected = [col for col in wanted if col in cols]

    if "id" in cols and "id" not in selected:
        selected.insert(0, "id")

    if not selected:
        return []

    order_col = None
    for candidate in ["created_at", "uploaded_at", "timestamp", "updated_at", "id"]:
        if candidate in cols:
            order_col = candidate
            break

    where = ""
    params = {"limit": limit}

    if org_id is not None and "organization_id" in cols:
        where = " WHERE organization_id = :org_id"
        params["org_id"] = org_id

    sql = f"SELECT {', '.join(selected)} FROM {table_name}{where}"

    if order_col:
        sql += f" ORDER BY {order_col} DESC"

    sql += " LIMIT :limit"

    try:
        rows = db.execute(text(sql), params).mappings().all()
        return [dict(row) for row in rows]
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return []


def normalize_audit_event(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "created_at": iso_or_string(row.get("created_at") or row.get("timestamp") or row.get("updated_at")),
        "user_email": row.get("user_email") or row.get("email") or "",
        "action": row.get("action") or "audit_event",
        "resource_type": row.get("resource_type") or "",
        "resource_id": row.get("resource_id") or "",
        "details": parse_json(row.get("details")),
    }


def normalize_upload_event(row: dict) -> dict:
    return {
        "id": f"upload-{row.get('id', '')}",
        "created_at": iso_or_string(row.get("created_at") or row.get("uploaded_at") or row.get("timestamp")),
        "user_email": row.get("user_email") or row.get("uploaded_by_email") or row.get("email") or "",
        "action": "loss_run_uploaded",
        "resource_type": "upload",
        "resource_id": str(row.get("id") or ""),
        "details": {
            "filename": row.get("filename") or row.get("file_name") or row.get("original_filename") or row.get("name") or "",
            "policy_number": row.get("policy_number") or row.get("policy") or "",
            "account_number": row.get("account_number") or row.get("customer_number") or "",
            "claims_saved": row.get("claims_saved") or row.get("claim_count") or row.get("claims_count"),
        },
    }


def normalize_claim_event(row: dict) -> dict:
    return {
        "id": f"claim-{row.get('id', '')}",
        "created_at": iso_or_string(row.get("created_at") or row.get("uploaded_at") or row.get("updated_at")),
        "user_email": row.get("user_email") or row.get("uploaded_by_email") or row.get("email") or "",
        "action": "claim_record_saved",
        "resource_type": "claim",
        "resource_id": str(row.get("id") or row.get("claim_number") or ""),
        "details": {
            "claim_number": row.get("claim_number") or row.get("claim_id") or "",
            "policy_number": row.get("policy_number") or "",
            "line_of_business": row.get("line_of_business") or "",
            "status": row.get("status") or "",
            "paid_amount": row.get("paid_amount"),
            "reserve_amount": row.get("reserve_amount"),
            "total_incurred": row.get("total_incurred") or row.get("incurred_amount"),
            "uploaded_at": iso_or_string(row.get("uploaded_at")),
        },
    }


def existing_event_keys(events: list[dict]) -> set[tuple[str, str, str]]:
    keys: set[tuple[str, str, str]] = set()
    for event in events:
        keys.add(
            (
                str(event.get("resource_type") or "").lower(),
                str(event.get("resource_id") or ""),
                str(event.get("action") or "").lower(),
            )
        )
    return keys


def add_claim_events(db: Session, events: list[dict], names: set[str], org_id: Any, limit: int) -> None:
    """
    Display-only claim audit coverage.

    This does NOT write to the claims table.
    This does NOT change upload/parser/dashboard behavior.
    It only reads existing claims and turns them into audit timeline events.
    """

    if "claims" not in names:
        return

    remaining = max(limit - len(events), 0)

    # Keep the audit page useful even when audit_logs is already full of upload events.
    # Pull up to 100 recent claims, but never exceed the requested API limit once merged.
    claim_limit = min(max(remaining, 25), 100)

    rows = safe_table_query(
        db,
        "claims",
        [
            "id",
            "created_at",
            "uploaded_at",
            "updated_at",
            "claim_number",
            "claim_id",
            "policy_number",
            "line_of_business",
            "status",
            "paid_amount",
            "reserve_amount",
            "total_incurred",
            "incurred_amount",
            "user_email",
            "uploaded_by_email",
            "email",
            "organization_id",
        ],
        claim_limit,
        org_id,
    )

    if not rows:
        return

    keys = existing_event_keys(events)

    for row in rows:
        claim_event = normalize_claim_event(row)
        claim_key = (
            str(claim_event.get("resource_type") or "").lower(),
            str(claim_event.get("resource_id") or ""),
            str(claim_event.get("action") or "").lower(),
        )

        if claim_key in keys:
            continue

        events.append(claim_event)
        keys.add(claim_key)


def build_events(db: Session, current_user: Any, limit: int) -> tuple[list[dict], str]:
    org_id = actor_value(current_user, "organization_id")
    names = table_names(db)
    events: list[dict] = []
    sources: list[str] = []

    if "audit_logs" in names:
        rows = safe_table_query(
            db,
            "audit_logs",
            [
                "id",
                "created_at",
                "user_email",
                "action",
                "resource_type",
                "resource_id",
                "details",
                "organization_id",
            ],
            limit,
            org_id,
        )
        audit_events = [normalize_audit_event(row) for row in rows]
        events.extend(audit_events)

        if audit_events:
            sources.append("audit_logs")

    # Important:
    # Before this patch, the function returned immediately when audit_logs had rows.
    # That made the Audit Log summary show Claims: 0 even though the claims table had records.
    # Now we always derive recent claim events for display only.
    add_claim_events(db=db, events=events, names=names, org_id=org_id, limit=limit)

    if any(event.get("resource_type") == "claim" for event in events):
        sources.append("claims")

    # Keep the old upload fallback behavior for accounts without formal audit_logs rows.
    if not events:
        upload_table = None
        for candidate in ["upload_history", "upload_histories", "uploads", "uploaded_files"]:
            if candidate in names:
                upload_table = candidate
                break

        if upload_table:
            rows = safe_table_query(
                db,
                upload_table,
                [
                    "id",
                    "created_at",
                    "uploaded_at",
                    "timestamp",
                    "filename",
                    "file_name",
                    "original_filename",
                    "name",
                    "policy_number",
                    "policy",
                    "account_number",
                    "customer_number",
                    "claims_saved",
                    "claim_count",
                    "claims_count",
                    "user_email",
                    "uploaded_by_email",
                    "email",
                    "organization_id",
                ],
                limit,
                org_id,
            )
            upload_events = [normalize_upload_event(row) for row in rows]
            events.extend(upload_events)

            if upload_events:
                sources.append("existing_uploads")

        add_claim_events(db=db, events=events, names=names, org_id=org_id, limit=limit)

        if any(event.get("resource_type") == "claim" for event in events):
            sources.append("claims")

    events.sort(key=lambda item: item.get("created_at") or "", reverse=True)

    source = "_with_".join(dict.fromkeys(sources)) if sources else "no_events_found"
    return events[:limit], source


def audit_payload(limit: int, current_user: Any, db: Session) -> dict:
    try:
        events, source = build_events(db, current_user, limit)
        return {
            "events": events,
            "count": len(events),
            "source": source,
        }
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass

        return {
            "events": [
                {
                    "id": "audit-endpoint-error",
                    "created_at": "",
                    "user_email": "",
                    "action": "audit_endpoint_error",
                    "resource_type": "system",
                    "resource_id": "",
                    "details": {"error": str(exc)},
                }
            ],
            "count": 1,
            "source": "safe_error_payload",
        }


def audit_summary_payload(limit: int, current_user: Any, db: Session) -> dict:
    payload = audit_payload(limit=limit, current_user=current_user, db=db)
    events = payload.get("events", [])

    uploads = sum(1 for event in events if event.get("resource_type") == "upload" or "upload" in str(event.get("action", "")).lower())
    claims = sum(1 for event in events if event.get("resource_type") == "claim" or "claim" in str(event.get("action", "")).lower())
    report_action_words = ("export", "report", "packet", "memo", "generated")
    exports = sum(
        1
        for event in events
        if event.get("resource_type") == "report"
        or any(word in str(event.get("action", "")).lower() for word in report_action_words)
    )
    users = sum(1 for event in events if event.get("resource_type") == "user" or "user" in str(event.get("action", "")).lower())

    return {
        "total_events": len(events),
        "uploads": uploads,
        "claims": claims,
        "exports": exports,
        "users": users,
        "last_event_at": events[0].get("created_at") if events else "",
        "source": payload.get("source", ""),
    }


@router.get("/")
def list_audit_logs(
    limit: int = Query(100, ge=1, le=250),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return audit_payload(limit=limit, current_user=current_user, db=db)


@router.get("")
def list_audit_logs_no_slash(
    limit: int = Query(100, ge=1, le=250),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return audit_payload(limit=limit, current_user=current_user, db=db)


@router.get("/summary")
def audit_log_summary(
    limit: int = Query(250, ge=1, le=500),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return audit_summary_payload(limit=limit, current_user=current_user, db=db)


@compat_router.get("/audit/events")
def get_audit_events_compat(
    limit: int = Query(100, ge=1, le=250),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return audit_payload(limit=limit, current_user=current_user, db=db)


@compat_router.get("/audit/logs")
def get_audit_logs_compat(
    limit: int = Query(100, ge=1, le=250),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return audit_payload(limit=limit, current_user=current_user, db=db)


@compat_router.get("/audit-log")
def get_audit_log_compat(
    limit: int = Query(100, ge=1, le=250),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return audit_payload(limit=limit, current_user=current_user, db=db)


@compat_router.get("/auth/audit-log")
def get_auth_audit_log_compat(
    limit: int = Query(100, ge=1, le=250),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return audit_payload(limit=limit, current_user=current_user, db=db)


@router.post("/")
def record_audit_event(
    payload: dict,
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    event = write_audit_event(
        db=db,
        current_user=current_user,
        action=str(payload.get("action") or "custom_event"),
        resource_type=str(payload.get("resource_type") or ""),
        resource_id=str(payload.get("resource_id") or ""),
        details=payload.get("details") or {},
        request=request,
    )

    return {"saved": bool(event)}

