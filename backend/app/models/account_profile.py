from sqlalchemy import Column, Integer, String, DateTime, Text
from datetime import datetime
from app.database import Base


class AccountProfile(Base):
    __tablename__ = "account_profiles"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, index=True)

    business_name = Column(String, default="Business Name Not Set")

    carrier_name = Column(String, default="Carrier Not Set")
    writing_carrier = Column(String, default="Carrier Not Set")

    agency_name = Column(String, default="Agency Not Set")
    account_number = Column(String, index=True, default="Account Not Set")
    customer_number = Column(String, default="Customer Not Set")
    producer_number = Column(String, default="Producer Not Set")

    policy_number = Column(String, index=True, default="Policy Not Set")

    effective_date = Column(String, default="Not Set")
    expiration_date = Column(String, default="Not Set")
    evaluation_date = Column(String, default="Not Set")

    policies = Column(Text, default="[]")
    validation = Column(Text, default="{}")
    raw_text_preview = Column(Text, default="")

    created_at = Column(DateTime, default=datetime.utcnow)