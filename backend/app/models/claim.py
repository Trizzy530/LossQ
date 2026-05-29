from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey
from app.database import Base

class Claim(Base):
    __tablename__ = "claims"

    id = Column(Integer, primary_key=True, index=True)
    claim_number = Column(String, index=True)
    policy_id = Column(Integer)
    policy_number = Column(String, index=True, nullable=True)

    line_of_business = Column(String)
    claim_type = Column(String)
    cause_of_loss = Column(String)
    claimant_type = Column(String)

    date_of_loss = Column(String)
    date_reported = Column(String)
    date_closed = Column(String)
    open_days = Column(Integer)
    claim_age = Column(Integer)

    status = Column(String)
    description = Column(String)

    paid_amount = Column(Float)
    reserve_amount = Column(Float)
    total_incurred = Column(Float)

    litigation = Column(Boolean)
    litigation_status = Column(String)
    attorney_assigned = Column(Boolean)
    suit_filed = Column(Boolean)
    venue_state = Column(String)
    injury_type = Column(String)
    flag = Column(String)

    organization_id = Column(Integer, ForeignKey("organizations.id"))
    uploaded_by_user_id = Column(Integer, ForeignKey("users.id"))
    uploaded_at = Column(String)