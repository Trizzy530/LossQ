from __future__ import annotations
import json
from typing import Any
from fastapi import Request
from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog


def safe_json(data: dict[str, Any] | None) -> str | None:
    if not data:
        return None
    try:
        return json.dumps(data, default=str)
    except Exception:
        return json.dumps({"error": "Unable to serialize audit details"})


def record_audit_event(
    db: Session,
    *,
    current_user: dict | None = None,
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
            organization_id = None
            user_id = None
            user_email = None
            if current_user:
                organization_id = current_user.get("organization_id")
                user_id = current_user.get("id") or current_user.get("user_id")
                user_email = (
                    current_user.get("email")
                    or current_user.get("user_email")
                    or current_user.get("sub")
                )
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
                action=action,
                resource_type=resource_type,
                resource_id=str(resource_id) if resource_id is not None else None,
                details=safe_json(details),
                ip_address=ip_address,
                user_agent=user_agent,
            )
            audit_db.add(audit)
            audit_db.commit()
        except Exception:
            audit_db.rollback()
        finally:
            audit_db.close()
    except Exception:
        return