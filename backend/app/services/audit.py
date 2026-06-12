from __future__ import annotations

import json
from typing import Any

from fastapi import Request
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def safe_json(data: dict[str, Any] | None) -> str | None:
    if not data:
        return None
    try:
        return json.dumps(data, default=str)
    except Exception:
        return json.dumps({"error": "Unable to serialize audit details"})


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
    """
    LOSSQ_AUDIT_STORAGE_REPAIR_V1

    Repairs older live audit_logs tables before saving audit events.
    This prevents profile delete, login, upload, and export audit writes from silently failing.
    """
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
        print(f"LOSSQ AUDIT STORAGE REPAIR FAILED: {type(exc).__name__}: {exc}")


def record_audit_event(
    db: Session,
    *,
    current_user: Any | None = None,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    try:
        from app.database import SessionLocal

        audit_db = SessionLocal()

        try:
            ensure_audit_log_storage(audit_db)

            organization_id = actor_value(current_user, "organization_id")
            user_id = actor_value(current_user, "id")
            user_email = actor_value(current_user, "email")

            ip_address = None
            user_agent = None

            if request:
                if request.client:
                    ip_address = request.client.host
                user_agent = request.headers.get("user-agent")

            audit = AuditLog(
                organization_id=organization_id,
                user_id=user_id,
                user_email=user_email,
                action=str(action or "audit_event"),
                resource_type=resource_type,
                resource_id=str(resource_id) if resource_id is not None else None,
                details=safe_json(details),
                ip_address=ip_address,
                user_agent=user_agent,
            )

            audit_db.add(audit)
            audit_db.commit()

        except Exception as exc:
            try:
                audit_db.rollback()
            except Exception:
                pass
            print(f"LOSSQ AUDIT WRITE FAILED: {type(exc).__name__}: {exc}")
        finally:
            audit_db.close()

    except Exception as exc:
        print(f"LOSSQ AUDIT OUTER FAILURE: {type(exc).__name__}: {exc}")
        return
