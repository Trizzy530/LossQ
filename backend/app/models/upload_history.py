from sqlalchemy import Column, Integer, String, ForeignKey
from app.database import Base

class UploadHistory(Base):
    __tablename__ = "upload_history"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String)
    stored_path = Column(String)
    content_type = Column(String)
    claims_saved = Column(Integer)
    uploaded_at = Column(String)
    uploaded_by_user_id = Column(Integer, ForeignKey("users.id"))
    organization_id = Column(Integer, ForeignKey("organizations.id"))