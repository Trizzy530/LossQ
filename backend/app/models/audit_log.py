from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, index=True, nullable=True)
    user_id = Column(Integer, index=True, nullable=True)
    user_email = Column(String, index=True, nullable=True)

    action = Column(String, index=True, nullable=False)
    resource_type = Column(String, index=True, nullable=True)
    resource_id = Column(String, index=True, nullable=True)
    details = Column(Text, nullable=True)

    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
