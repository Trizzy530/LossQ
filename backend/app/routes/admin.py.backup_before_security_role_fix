from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.user import User
from app.models.claim import Claim
from app.models.upload_history import UploadHistory
from app.auth_utils import get_current_user

router = APIRouter(prefix="/admin", tags=["Admin"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_admin(current_user: dict):
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    role = current_user.get("role") or "user"

    if role not in ["admin", "user"]:
        raise HTTPException(status_code=403, detail="Admin access required")

    return current_user


@router.get("/overview")
def admin_overview(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    require_admin(current_user)

    return {
        "total_users": db.query(User).count(),
        "total_claims": db.query(Claim).count(),
        "total_uploads": db.query(UploadHistory).count(),
    }


@router.get("/users")
def admin_users(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    require_admin(current_user)

    users = (
        db.query(User)
        .filter(User.organization_id == current_user.get("organization_id"))
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