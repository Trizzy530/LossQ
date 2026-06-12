from __future__ import annotations

import json
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def actor_value(current_user: Any, key: str, default: Any = None) -> Any:
    if current_user is None:
        return default

    if isinstance(current_user, dict):
        if key == "id":
            return current_user.get("id", current_user.get("user_id", default))
        if key == "email":
            return current_user.get("email", current_user.get("user_email", current_user.get("sub", default)))
        return current_user.get(key, default)

    if key == "id":
        return getattr(current_user, "id", getattr(current_user, "user_id", default))
    if key == "email":
        return getattr(current_user, "email", getattr(current_user, "user_email", default))

    return getattr(current_user, key, default)


def ensure_audit_log_storage(db: Session) -> None:
    try:
        AuditLog.__table__.create(bind=db.bind, checkfirst=True)

        inspector = inspect(db.bind)
        existing = {column["name"] for column in inspector.get_columns("audit_logs")}

        required = {
            "organization_id": "INTEGER",
            "user_id": "INTEGER",
            "user_email": "VARCHAR",
            "action": "VARCHAR",
            "resource_type": "VARCHAR",
            "resource_id": "VARCHAR",
            "details": "TEXT",
            "ip_address": "VARCHAR",
            "user_agent": "VARCHAR",
            "created_at": "TIMESTAMP",
        }

        for column_name, column_type in required.items():
            if column_name not in existing:
                db.execute(text(f"ALTER TABLE audit_logs ADD COLUMN {column_name} {column_type}"))

        db.commit()

    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        print(f"LOSSQ AUDIT SERVICE STORAGE REPAIR FAILED: {type(exc).__name__}: {exc}")


def write_audit_event(
    db: Session,
    current_user: Any,
    action: str,
    resource_type: str = "",
    resource_id: str = "",
    details: Any = None,
    request: Any = None,
) -> AuditLog | None:
    try:
        ensure_audit_log_storage(db)

        details_text = None if details is None else (
            details if isinstance(details, str) else json.dumps(details, default=str)
        )

        event = AuditLog(
            organization_id=actor_value(current_user, "organization_id"),
            user_id=actor_value(current_user, "id"),
            user_email=actor_value(current_user, "email"),
            action=str(action or "audit_event"),
            resource_type=resource_type,
            resource_id=str(resource_id or ""),
            details=details_text,
            ip_address=request.client.host if request and getattr(request, "client", None) else None,
            user_agent=request.headers.get("user-agent") if request and getattr(request, "headers", None) else None,
        )

        db.add(event)
        db.commit()
        db.refresh(event)
        return event

    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        print(f"LOSSQ AUDIT SERVICE WRITE FAILED: {type(exc).__name__}: {exc}")
        return None
