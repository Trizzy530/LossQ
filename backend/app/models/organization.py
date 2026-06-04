from sqlalchemy import Column, DateTime, Integer, String, func
from app.database import Base


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)

    # Default user cap. Later this can be tied to paid plan/billing.
    user_limit = Column(Integer, default=5, nullable=False)
    owner_user_id = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
