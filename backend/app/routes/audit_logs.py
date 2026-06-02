from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth_utils import get_current_user
from app.database import SessionLocal
from app.models.audit_log import AuditLog

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])


def require_admin_user(current_user: dict):
    role = str(current_user.get("role") or "").lower()

    if role not in ["admin", "owner"]:
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to view audit logs.",
        )


@router.get("/")
def list_audit_logs(
    action: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    user_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    require_admin_user(current_user)

    organization_id = current_user["organization_id"]

    query = db.query(AuditLog).filter(
        AuditLog.organization_id == organization_id
    )

    if action:
        query = query.filter(AuditLog.action == action)

    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)

    if user_id:
        query = query.filter(AuditLog.user_id == user_id)

    logs = (
        query.order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )

    return {
        "count": len(logs),
        "audit_logs": [
            {
                "id": log.id,
                "organization_id": log.organization_id,
                "user_id": log.user_id,
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "details": log.details,
                "ip_address": log.ip_address,
                "user_agent": log.user_agent,
                "created_at": log.created_at,
            }
            for log in logs
        ],
    }


@router.get("/summary")
def audit_log_summary(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    require_admin_user(current_user)

    organization_id = current_user["organization_id"]

    logs = (
        db.query(AuditLog)
        .filter(AuditLog.organization_id == organization_id)
        .order_by(AuditLog.created_at.desc())
        .limit(250)
        .all()
    )

    action_counts = {}

    for log in logs:
        action_counts[log.action] = action_counts.get(log.action, 0) + 1

    return {
        "recent_event_count": len(logs),
        "actions": action_counts,
    }