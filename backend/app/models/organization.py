from sqlalchemy import Column, DateTime, Integer, String, func
from app.database import Base


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)  # LOSSQ_ORG_NAME_NOT_UNIQUE_V1

    # Account ownership and team limits
    user_limit = Column(Integer, default=5, nullable=False)
    owner_user_id = Column(Integer, nullable=True)

    # LOSSQ_AGENCY_PROFILE_FIELDS_V1
    agency_contact_name = Column(String, nullable=True)
    agency_email = Column(String, nullable=True)
    agency_phone = Column(String, nullable=True)
    agency_address = Column(String, nullable=True)
    agency_city = Column(String, nullable=True)
    agency_state = Column(String, nullable=True)
    agency_zip = Column(String, nullable=True)
    agency_website = Column(String, nullable=True)
    agency_license_number = Column(String, nullable=True)
    agency_logo_url = Column(String, nullable=True)

    # Stripe / subscription billing
    plan = Column(String, default="free", nullable=False)
    subscription_status = Column(String, default="inactive", nullable=False)
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    stripe_price_id = Column(String, nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    upload_limit = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
