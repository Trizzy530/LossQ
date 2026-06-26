from sqlalchemy import Column, Integer, String, Text, DateTime, Text
from datetime import datetime
from app.database import Base


class AccountProfile(Base):
    __tablename__ = "account_profiles"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, index=True)

    business_name = Column(String, default="Business Name Not Set")

    carrier_name = Column(String, default="Carrier Not Set")
    writing_carrier = Column(String, default="Carrier Not Set")

    agency_name = Column(String, default="")
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


    # LOSSQ_ACCOUNT_PROFILE_EXPOSURE_COLUMNS_V1
    current_premium = Column(String, nullable=True)
    expiring_premium = Column(String, nullable=True)
    target_renewal_premium = Column(String, nullable=True)
    line_of_business = Column(String, nullable=True)
    state = Column(String, nullable=True)
    class_code = Column(String, nullable=True)
    class_codes = Column(String, nullable=True)
    limits = Column(String, nullable=True)
    coverage_limit = Column(String, nullable=True)
    deductible = Column(String, nullable=True)
    retention = Column(String, nullable=True)
    payroll = Column(String, nullable=True)
    revenue = Column(String, nullable=True)
    sales = Column(String, nullable=True)
    receipts = Column(String, nullable=True)
    employee_count = Column(String, nullable=True)
    # LOSSQ_ACCOUNT_PROFILE_PHYSICIAN_COUNT_COLUMN_V2
    physician_count = Column(String, nullable=True)
    vehicle_count = Column(String, nullable=True)
    driver_count = Column(String, nullable=True)
    property_tiv = Column(String, nullable=True)
    tiv = Column(String, nullable=True)
    building_value = Column(String, nullable=True)
    contents_value = Column(String, nullable=True)
    square_footage = Column(String, nullable=True)
    location_count = Column(String, nullable=True)
    # LOSSQ_MODEL_LIQUOR_EXPOSURE_FIELDS_V1
    liquor_sales = Column(String, nullable=True)
    alcohol_sales = Column(String, nullable=True)
    unit_count = Column(String, nullable=True)
    cargo_limit = Column(String, nullable=True)
    umbrella_limit = Column(String, nullable=True)
    experience_mod = Column(String, nullable=True)
    mod = Column(String, nullable=True)
    exposure_change_percent = Column(String, nullable=True)
    cyber_revenue = Column(String, nullable=True)
    professional_revenue = Column(String, nullable=True)
    exposure_basis = Column(String, nullable=True)
    underwriter_notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
