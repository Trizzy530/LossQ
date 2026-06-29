from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.organization import Organization
from app.models.user import User
from app.routes.auth import get_current_user, require_admin_or_owner, public_user
from app.services.audit_service import write_audit_event

router = APIRouter(prefix="/admin-users", tags=["Admin Users"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/")
def list_admin_users(
    current_user: User = Depends(require_admin_or_owner),
    db: Session = Depends(get_db),
):
    users = (
        db.query(User)
        .filter(User.organization_id == current_user.organization_id)
        .order_by(User.role.asc(), User.email.asc())
        .all()
    )

    return {"users": [public_user(user) for user in users]}


@router.get("/me")
def admin_me(current_user: User = Depends(get_current_user)):
    return {"user": public_user(current_user)}


@router.delete("/organizations/{organization_id}/users/{user_id}/permanent")
def permanently_delete_org_user(
    organization_id: int,
    user_id: int,
    request: Request,
    current_user: User = Depends(require_admin_or_owner),
    db: Session = Depends(get_db),
):
    # LOSSQ_ADMIN_USER_PERMANENT_DELETE_BY_ORG_AND_USER_ID_V1
    current_role = str(current_user.role or "user").strip().lower()
    current_org_id = int(current_user.organization_id or 0)

    if not current_org_id:
        raise HTTPException(status_code=403, detail="Organization access required")

    if int(organization_id) != current_org_id:
        raise HTTPException(
            status_code=403,
            detail="Admins can only permanently delete users from their own organization",
        )

    organization = db.query(Organization).filter(Organization.id == organization_id).first()
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")

    target_user = (
        db.query(User)
        .filter(User.id == user_id, User.organization_id == organization_id)
        .first()
    )

    if not target_user:
        raise HTTPException(status_code=404, detail="User not found for this organization")

    target_role = str(target_user.role or "user").strip().lower()

    if target_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot permanently delete yourself")
    if target_role == "owner":
        raise HTTPException(status_code=403, detail="Owner accounts cannot be permanently deleted here")
    if current_role == "admin" and target_role != "user":
        raise HTTPException(status_code=403, detail="Admins can only permanently delete normal users")

    deleted_user = {
        "id": target_user.id,
        "email": target_user.email,
        "role": target_user.role or "user",
        "first_name": target_user.first_name or "",
        "last_name": target_user.last_name or "",
        "organization_id": target_user.organization_id,
    }

    db.delete(target_user)
    db.commit()

    write_audit_event(
        db,
        current_user=current_user,
        action="user_permanently_deleted",
        resource_type="user",
        resource_id=str(user_id),
        details={
            "event": "user_permanently_deleted",
            "deleted_user": deleted_user,
            "organization_id": organization_id,
            "organization_name": organization.name,
            "required_identifiers": {
                "organization_id": organization_id,
                "user_id": user_id,
            },
        },
        request=request,
    )

    return {
        "message": f"{deleted_user['email']} was permanently deleted from {organization.name}.",
        "deleted_user_id": user_id,
        "organization_id": organization_id,
    }
