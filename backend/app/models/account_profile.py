from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from app.database import Base


class AccountProfile(Base):
    __tablename__ = "account_profiles"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, index=True)

    business_name = Column(String, default="Business Name Not Set")
    carrier_name = Column(String, default="Carrier Not Set")
    agency_name = Column(String, default="Agency Not Set")
    policy_number = Column(String, index=True, default="Policy Not Set")
    effective_date = Column(String, default="Not Set")
    expiration_date = Column(String, default="Not Set")
    evaluation_date = Column(String, default="Not Set")

    created_at = Column(DateTime, default=datetime.utcnow)