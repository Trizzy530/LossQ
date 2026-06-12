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

    role = str(current_user.get("role") or "user").strip().lower()

    if role not in ["owner", "admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")

    org_id = current_user.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=403, detail="Organization access required")

    return current_user


@router.get("/overview")
def admin_overview(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    require_admin(current_user)

    org_id = current_user.get("organization_id")

    return {
        "organization_id": org_id,
        "total_users": (
            db.query(User)
            .filter(User.organization_id == org_id)
            .count()
        ),
        "total_claims": (
            db.query(Claim)
            .filter(Claim.organization_id == org_id)
            .count()
        ),
        "total_uploads": (
            db.query(UploadHistory)
            .filter(UploadHistory.organization_id == org_id)
            .count()
        ),
    }


@router.get("/users")
def admin_users(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    require_admin(current_user)

    org_id = current_user.get("organization_id")

    users = (
        db.query(User)
        .filter(User.organization_id == org_id)
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
