from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def actor_value(current_user: Any, key: str, default: Any = None) -> Any:
    if isinstance(current_user, dict):
        return current_user.get(key, default)
    return getattr(current_user, key, default)


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
        details_text = None if details is None else (
            details if isinstance(details, str) else json.dumps(details, default=str)
        )

        event = AuditLog(
            organization_id=actor_value(current_user, "organization_id"),
            user_id=actor_value(current_user, "id"),
            user_email=actor_value(current_user, "email"),
            action=action,
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

    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return None
