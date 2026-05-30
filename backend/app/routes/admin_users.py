from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.user import User
from app.role_utils import require_permission

router = APIRouter(prefix="/admin", tags=["Admin Users"])


class RoleUpdateRequest(BaseModel):
    role: str


ALLOWED_ROLES = ["admin", "broker", "underwriter", "viewer", "user"]


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/users")
def list_organization_users(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("manage_users")),
):
    users = (
        db.query(User)
        .filter(User.organization_id == current_user["organization_id"])
        .order_by(User.id.asc())
        .all()
    )

    return [
        {
            "id": user.id,
            "email": user.email,
            "role": user.role or "user",
            "organization_id": user.organization_id,
        }
        for user in users
    ]


@router.put("/users/{user_id}/role")
def update_user_role(
    user_id: int,
    data: RoleUpdateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("manage_users")),
):
    if data.role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")

    user = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.organization_id == current_user["organization_id"],
        )
        .first()
    )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.role = data.role
    db.commit()
    db.refresh(user)

    return {
        "message": "User role updated",
        "user": {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "organization_id": user.organization_id,
        },
    }