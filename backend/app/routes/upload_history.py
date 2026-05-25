from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.upload_history import UploadHistory
from app.auth_utils import get_current_user

router = APIRouter(prefix="/upload-history", tags=["Upload History"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/")
def get_upload_history(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return db.query(UploadHistory).filter(
        UploadHistory.organization_id == current_user["organization_id"]
    ).order_by(UploadHistory.id.desc()).all()