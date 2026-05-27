from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    email = Column(String, unique=True, index=True, nullable=False)

    password_hash = Column(String, nullable=False)

    role = Column(String, default="user")

    organization_id = Column(Integer, ForeignKey("organizations.id"))

    email_verified = Column(Boolean, default=False)

    onboarding_status = Column(String, default="pending")