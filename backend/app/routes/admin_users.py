from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.user import User
from app.routes.auth import get_current_user, require_admin_or_owner, public_user

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
