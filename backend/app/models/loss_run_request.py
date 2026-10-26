from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from app.database import Base


class LossRunRequest(Base):
    __tablename__ = "loss_run_requests"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    insured_name = Column(String, index=True, nullable=False)
    carrier_name = Column(String, nullable=False)
    policy_number = Column(String, nullable=True)
    contact_name = Column(String, nullable=True)
    contact_email = Column(String, nullable=True)
    status = Column(String, default="draft", index=True, nullable=False)
    authorization_received = Column(Boolean, default=False, nullable=False)
    requested_at = Column(DateTime(timezone=True), nullable=True)
    next_follow_up_at = Column(DateTime(timezone=True), index=True, nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class LossRunRequestEvent(Base):
    __tablename__ = "loss_run_request_events"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    request_id = Column(Integer, ForeignKey("loss_run_requests.id"), index=True, nullable=False)
    event_type = Column(String, nullable=False)
    from_status = Column(String, nullable=True)
    to_status = Column(String, nullable=True)
    note = Column(Text, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
