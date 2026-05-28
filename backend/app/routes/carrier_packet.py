from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import SessionLocal
from app.models.claim import Claim
from app.auth_utils import get_current_user
from app.routes.summary import build_underwriting_intelligence

router = APIRouter(prefix="/carrier-packet", tags=["Carrier Packet"])


class CarrierPacketRequest(BaseModel):
    policy_number: str


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/generate")
def generate_carrier_packet(
    request: CarrierPacketRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    claims = (
        db.query(Claim)
        .filter(Claim.organization_id == current_user["organization_id"])
        .filter(Claim.policy_number == request.policy_number)
        .all()
    )

    if not claims:
        raise HTTPException(
            status_code=404,
            detail="No claims found for this policy number.",
        )

    intelligence = build_underwriting_intelligence(claims)

    total_claims = len(claims)
    open_claims = len([c for c in claims if c.status == "Open"])
    closed_claims = len([c for c in claims if c.status == "Closed"])
    litigation_claims = len([c for c in claims if c.litigation])

    total_paid = sum(float(c.paid_amount or 0) for c in claims)
    total_reserve = sum(float(c.reserve_amount or 0) for c in claims)
    total_incurred = sum(float(c.total_incurred or 0) for c in claims)

    top_claims = sorted(
        claims,
        key=lambda c: float(c.total_incurred or 0),
        reverse=True,
    )[:5]

    severity_drivers = [
        {
            "claim_number": c.claim_number,
            "line_of_business": c.line_of_business,
            "status": c.status,
            "paid_amount": float(c.paid_amount or 0),
            "reserve_amount": float(c.reserve_amount or 0),
            "total_incurred": float(c.total_incurred or 0),
            "litigation": bool(c.litigation),
            "flag": c.flag,
            "description": c.description,
        }
        for c in top_claims
    ]

    reserve_ratio = total_reserve / total_incurred if total_incurred > 0 else 0

    if reserve_ratio < 0.15 and open_claims > 0:
        reserve_analysis = "Reserve levels may be low relative to open incurred exposure. Carrier should review open claim development closely."
    elif reserve_ratio > 0.5:
        reserve_analysis = "Reserve position appears conservative relative to total incurred exposure."
    else:
        reserve_analysis = "Reserve position appears generally reasonable based on current loss data."

    if litigation_claims > 0:
        litigation_exposure = (
            f"{litigation_claims} litigation-related claim(s) identified. "
            "Broker should provide defense status, counsel notes, current reserve rationale, and expected resolution timing."
        )
    else:
        litigation_exposure = "No litigation-related claims identified in the current loss data."

    if intelligence["renewal_risk"] == "RED":
        broker_strategy = (
            "Position the account with a proactive corrective-action narrative, detailed claim explanations, "
            "updated reserves, and evidence of risk controls before carrier submission."
        )
    elif intelligence["renewal_risk"] == "YELLOW":
        broker_strategy = (
            "Position the account as manageable with supporting context around claim frequency, open claims, "
            "and loss control improvements."
        )
    else:
        broker_strategy = (
            "Position the account as favorable with clean loss experience and strong submission documentation."
        )

    return {
        "policy_number": request.policy_number,
        "account_summary": intelligence["summary"],
        "renewal_risk": intelligence["renewal_risk"],
        "risk_level": intelligence["risk_level"],
        "risk_score": intelligence["risk_score"],
        "submission_strength": intelligence["submission_strength"],
        "claim_metrics": {
            "total_claims": total_claims,
            "open_claims": open_claims,
            "closed_claims": closed_claims,
            "litigation_claims": litigation_claims,
            "total_paid": total_paid,
            "total_reserve": total_reserve,
            "total_incurred": total_incurred,
            "reserve_ratio": reserve_ratio,
        },
        "severity_drivers": severity_drivers,
        "litigation_exposure": litigation_exposure,
        "reserve_analysis": reserve_analysis,
        "broker_strategy": broker_strategy,
        "carrier_narrative": intelligence["carrier_narrative"],
        "recommendations": [
            intelligence["recommendation"],
            "Attach current loss runs, claim notes, and reserve explanations.",
            "Address open claims and litigation clearly before submission.",
            "Highlight corrective actions and risk controls where applicable.",
        ],
    }