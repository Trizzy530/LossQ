from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text, inspect, func
from typing import Any

from app.database import SessionLocal
from app.models.claim import Claim
from app.auth_utils import get_current_user

router = APIRouter(prefix="/claims", tags=["Claims"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def clean_value(value: Any) -> str:
    return str(value or "").strip()


def normalize_policy_number(value: Any) -> str:
    return clean_value(value).upper()


def money_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        cleaned = str(value).replace("$", "").replace(",", "").strip()
        if cleaned in {"", "-", "None", "none", "null"}:
            return 0.0
        return float(cleaned)
    except Exception:
        return 0.0


def ensure_claim_timeline_columns(db: Session):
    required_columns = {
        "date_of_loss": "VARCHAR",
        "date_reported": "VARCHAR",
        "date_closed": "VARCHAR",
        "open_days": "INTEGER",
        "claim_age": "INTEGER",
    }

    try:
        inspector = inspect(db.bind)
        existing_columns = [column["name"] for column in inspector.get_columns("claims")]
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                db.execute(text(f"ALTER TABLE claims ADD COLUMN {column_name} {column_type}"))
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Claim timeline column check failed: {e}")


def claim_to_dict(claim: Claim):
    return {
        "id": getattr(claim, "id", None),
        "claim_number": clean_value(getattr(claim, "claim_number", "")),
        "policy_id": getattr(claim, "policy_id", None),
        "policy_number": clean_value(getattr(claim, "policy_number", "")),
        "line_of_business": clean_value(getattr(claim, "line_of_business", "")),
        "claim_type": clean_value(getattr(claim, "claim_type", "")),
        "cause_of_loss": clean_value(getattr(claim, "cause_of_loss", "")),
        "claimant_type": clean_value(getattr(claim, "claimant_type", "")),
        "date_of_loss": clean_value(getattr(claim, "date_of_loss", "")),
        "date_reported": clean_value(getattr(claim, "date_reported", "")),
        "date_closed": clean_value(getattr(claim, "date_closed", "")),
        "open_days": getattr(claim, "open_days", None),
        "claim_age": getattr(claim, "claim_age", None),
        "status": clean_value(getattr(claim, "status", "")),
        "description": clean_value(getattr(claim, "description", "")),
        "paid_amount": money_float(getattr(claim, "paid_amount", 0)),
        "reserve_amount": money_float(getattr(claim, "reserve_amount", 0)),
        "total_incurred": money_float(getattr(claim, "total_incurred", 0)),
        "litigation": bool(getattr(claim, "litigation", False)),
        "litigation_status": clean_value(getattr(claim, "litigation_status", "")),
        "attorney_assigned": bool(getattr(claim, "attorney_assigned", False)),
        "suit_filed": bool(getattr(claim, "suit_filed", False)),
        "venue_state": clean_value(getattr(claim, "venue_state", "")),
        "injury_type": clean_value(getattr(claim, "injury_type", "")),
        "flag": clean_value(getattr(claim, "flag", "")),
        "organization_id": getattr(claim, "organization_id", None),
        "uploaded_by_user_id": getattr(claim, "uploaded_by_user_id", None),
        "uploaded_at": clean_value(getattr(claim, "uploaded_at", "")),
    }


def score_claim(claim):
    score = 0
    total = money_float(getattr(claim, "total_incurred", 0))
    reserve = money_float(getattr(claim, "reserve_amount", 0))
    paid = money_float(getattr(claim, "paid_amount", 0))
    status = clean_value(getattr(claim, "status", "")).lower()

    if total >= 250000:
        score += 50
    elif total >= 100000:
        score += 35
    elif total >= 50000:
        score += 20
    elif total >= 10000:
        score += 10

    if bool(getattr(claim, "litigation", False)):
        score += 30
    if bool(getattr(claim, "attorney_assigned", False)):
        score += 15
    if status == "open":
        score += 10
    if reserve > paid:
        score += 10

    if score >= 75:
        severity = "Catastrophic"
    elif score >= 50:
        severity = "Severe"
    elif score >= 25:
        severity = "Moderate"
    else:
        severity = "Low"

    return score, severity


def build_claim_ai_analysis(claim):
    score, severity = score_claim(claim)
    total = money_float(getattr(claim, "total_incurred", 0))
    reserve = money_float(getattr(claim, "reserve_amount", 0))
    paid = money_float(getattr(claim, "paid_amount", 0))
    status = clean_value(getattr(claim, "status", ""))
    claim_number = clean_value(getattr(claim, "claim_number", ""))

    risk_factors = []
    if status.lower() == "open":
        risk_factors.append("Open claim")
    if reserve > 0:
        risk_factors.append("Outstanding reserve")
    if reserve > paid:
        risk_factors.append("Reserve exceeds paid amount")
    if bool(getattr(claim, "litigation", False)):
        risk_factors.append("Litigation exposure")
    if bool(getattr(claim, "attorney_assigned", False)):
        risk_factors.append("Attorney involvement")
    if total >= 100000:
        risk_factors.append("High incurred severity")

    reserve_concern = "Low"
    if reserve >= 100000:
        reserve_concern = "High"
    elif reserve >= 25000:
        reserve_concern = "Moderate"

    broker_actions = []
    if status.lower() == "open":
        broker_actions.append("Obtain updated claim status before renewal submission")
    if reserve > paid:
        broker_actions.append("Explain reserve strategy and expected resolution timeline")
    if bool(getattr(claim, "litigation", False)):
        broker_actions.append("Provide defense counsel update and litigation narrative")
    if total >= 100000:
        broker_actions.append("Prepare severe-loss explanation and corrective action summary")
    if not broker_actions:
        broker_actions.append("No major broker action required beyond standard documentation")

    underwriter_narrative = (
        f"Claim {claim_number or 'N/A'} involves "
        f"{clean_value(getattr(claim, 'line_of_business', '')) or 'an unspecified line of business'} exposure. "
        f"The claim shows paid losses of ${paid:,.2f}, reserves of ${reserve:,.2f}, "
        f"and total incurred losses of ${total:,.2f}. This claim is classified as {severity}."
    )

    return {
        "severity_score": score,
        "severity": severity,
        "reserve_concern": reserve_concern,
        "litigation_exposure": "Elevated litigation exposure detected" if bool(getattr(claim, "litigation", False)) else "None detected",
        "renewal_impact": "High renewal impact" if severity in ["Severe", "Catastrophic"] else ("Moderate renewal impact" if severity == "Moderate" else "Low renewal impact"),
        "risk_factors": risk_factors,
        "broker_actions": broker_actions,
        "ai_summary": (
            f"Claim {claim_number} is classified as {severity} severity with a score of {score}. "
            f"Paid: ${paid:,.2f}; reserve: ${reserve:,.2f}; total incurred: ${total:,.2f}."
        ),
        "underwriter_narrative": underwriter_narrative,
        "risk_summary": f"This claim presents {severity.lower()} underwriting risk.",
        "litigation_analysis": "No litigation or attorney involvement is currently identified." if not bool(getattr(claim, "litigation", False)) else "Litigation exposure is present and should be addressed.",
        "broker_talking_points": broker_actions,
    }


@router.get("/")
def get_claims(
    policy_number: str | None = Query(default=None),
    policy_numbers: str | None = Query(default=None),
    claim_number: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    ensure_claim_timeline_columns(db)
    query = db.query(Claim).filter(Claim.organization_id == current_user["organization_id"])

    if policy_numbers:
        pn_list = [p.strip().upper() for p in policy_numbers.split(",") if p.strip()]
        if pn_list:
            query = query.filter(func.upper(func.trim(Claim.policy_number)).in_(pn_list))
    elif policy_number:
        normalized_policy = normalize_policy_number(policy_number)
        query = query.filter(func.upper(func.trim(Claim.policy_number)) == normalized_policy)

    if claim_number:
        normalized_claim = clean_value(claim_number).upper()
        query = query.filter(func.upper(func.trim(Claim.claim_number)) == normalized_claim)

    claims = query.order_by(Claim.id.desc()).all()
    return [claim_to_dict(claim) for claim in claims]


@router.get("/lookup")
def lookup_claim(
    claim_number: str = Query(...),
    policy_number: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    ensure_claim_timeline_columns(db)
    query = db.query(Claim).filter(
        Claim.organization_id == current_user["organization_id"],
        func.upper(func.trim(Claim.claim_number)) == clean_value(claim_number).upper(),
    )
    if policy_number:
        query = query.filter(func.upper(func.trim(Claim.policy_number)) == normalize_policy_number(policy_number))
    claim = query.order_by(Claim.id.desc()).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    return {"claim": claim_to_dict(claim), **build_claim_ai_analysis(claim)}


@router.get("/{claim_id}")
def get_claim_detail(
    claim_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    ensure_claim_timeline_columns(db)
    claim = db.query(Claim).filter(
        Claim.id == claim_id,
        Claim.organization_id == current_user["organization_id"],
    ).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    return {"claim": claim_to_dict(claim), **build_claim_ai_analysis(claim)}

@router.delete("/bulk")
def bulk_delete_claims(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Deletes ALL claims for the current organization.
    Used to wipe bad/orphaned claims before a clean re-upload.
    """
    deleted = (
        db.query(Claim)
        .filter(Claim.organization_id == current_user["organization_id"])
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"deleted": True, "claims_deleted": deleted}



