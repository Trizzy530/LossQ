from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)

    # Roles: owner, admin, user
    role = Column(String, default="user", nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)

    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)

    is_email_verified = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    last_login_at = Column(DateTime(timezone=True), nullable=True)

    # LOSSQ_SINGLE_ACTIVE_SESSION_MODEL_V1
    active_session_id = Column(String, nullable=True)
    active_session_started_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
