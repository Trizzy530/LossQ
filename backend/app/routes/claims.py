from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text, inspect
from datetime import datetime

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


def ensure_claim_timeline_columns(db: Session):
    required_columns = {
        "date_reported": "VARCHAR",
        "date_closed": "VARCHAR",
        "open_days": "INTEGER",
        "claim_age": "INTEGER",
    }

def ensure_claim_delete_columns(db: Session):
    required_columns = {
        "is_deleted": "BOOLEAN DEFAULT FALSE",
        "deleted_at": "TIMESTAMP",
    }

    try:
        inspector = inspect(db.bind)
        existing_columns = [
            column["name"] for column in inspector.get_columns("claims")
        ]

        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                db.execute(
                    text(f"ALTER TABLE claims ADD COLUMN {column_name} {column_type}")
                )

        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Claim delete column check failed: {e}")
    try:
        inspector = inspect(db.bind)
        existing_columns = [
            column["name"] for column in inspector.get_columns("claims")
        ]

        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                db.execute(
                    text(f"ALTER TABLE claims ADD COLUMN {column_name} {column_type}")
                )

        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Claim timeline column check failed: {e}")
    try:
        result = db.execute(text("PRAGMA table_info(claims)"))
        existing_columns = [row[1] for row in result.fetchall()]

        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                db.execute(
                    text(f"ALTER TABLE claims ADD COLUMN {column_name} {column_type}")
                )

        db.commit()
    except Exception:
        db.rollback()

def score_claim(claim):
    score = 0
    total = float(claim.total_incurred or 0)
    reserve = float(claim.reserve_amount or 0)
    paid = float(claim.paid_amount or 0)

    if total >= 250000:
        score += 50
    elif total >= 100000:
        score += 35
    elif total >= 50000:
        score += 20
    elif total >= 10000:
        score += 10

    if claim.litigation:
        score += 30

    if claim.attorney_assigned:
        score += 15

    if claim.status == "Open":
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

    total = float(claim.total_incurred or 0)
    reserve = float(claim.reserve_amount or 0)
    paid = float(claim.paid_amount or 0)

    risk_factors = []

    if claim.status == "Open":
        risk_factors.append("Open claim")

    if reserve > 0:
        risk_factors.append("Outstanding reserve")

    if reserve > paid:
        risk_factors.append("Reserve exceeds paid amount")

    if claim.litigation:
        risk_factors.append("Litigation exposure")

    if claim.attorney_assigned:
        risk_factors.append("Attorney involvement")

    if total >= 100000:
        risk_factors.append("High incurred severity")

    reserve_concern = "Low"
    if reserve >= 100000:
        reserve_concern = "High"
    elif reserve >= 25000:
        reserve_concern = "Moderate"

    litigation_exposure = (
        "Elevated litigation exposure detected" if claim.litigation else "None detected"
    )

    renewal_impact = "Low renewal impact"
    if severity in ["Severe", "Catastrophic"]:
        renewal_impact = "High renewal impact"
    elif severity == "Moderate":
        renewal_impact = "Moderate renewal impact"

    broker_actions = []

    if claim.status == "Open":
        broker_actions.append("Obtain updated claim status before renewal submission")

    if reserve > paid:
        broker_actions.append("Explain reserve strategy and expected resolution timeline")

    if claim.litigation:
        broker_actions.append("Provide defense counsel update and litigation narrative")

    if total >= 100000:
        broker_actions.append("Prepare severe-loss explanation and corrective action summary")

    if not broker_actions:
        broker_actions.append("No major broker action required beyond standard documentation")

    ai_summary = (
        f"Claim {claim.claim_number} is classified as {severity} severity with a score of {score}. "
        f"The claim has paid losses of ${paid:,.2f}, reserves of ${reserve:,.2f}, "
        f"and total incurred exposure of ${total:,.2f}. "
        f"Primary underwriting concerns include: "
        f"{', '.join(risk_factors) if risk_factors else 'no major concerns detected'}."
    )

    return {
        "severity_score": score,
        "severity": severity,
        "reserve_concern": reserve_concern,
        "litigation_exposure": litigation_exposure,
        "renewal_impact": renewal_impact,
        "risk_factors": risk_factors,
        "broker_actions": broker_actions,
        "ai_summary": ai_summary,
    }


@router.get("/")
def get_claims(
    policy_number: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    ensure_claim_timeline_columns(db)
    ensure_claim_delete_columns(db)

    query = db.query(Claim).filter(
    Claim.organization_id == current_user["organization_id"],
    Claim.is_deleted == False,
)

    if policy_number:
        query = query.filter(Claim.policy_number == policy_number)

    return query.order_by(Claim.id.desc()).all()


@router.get("/{claim_id}")
def get_claim_detail(
    claim_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    ensure_claim_timeline_columns(db)
    ensure_claim_delete_columns(db)

    claim = (
    db.query(Claim)
    .filter(
        Claim.id == claim_id,
        Claim.organization_id == current_user["organization_id"],
        Claim.is_deleted == False,
    )
    .first()
)

    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    analysis = build_claim_ai_analysis(claim)

    return {
        "claim": claim,
        **analysis,
    }

@router.delete("/{claim_id}")
def delete_claim(
    claim_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    ensure_claim_delete_columns(db)

    claim = (
        db.query(Claim)
        .filter(
            Claim.id == claim_id,
            Claim.organization_id == current_user["organization_id"],
            Claim.is_deleted == False,
        )
        .first()
    )

    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    claim.is_deleted = True
    claim.deleted_at = datetime.utcnow()

    db.commit()

    return {
        "message": "Claim deleted successfully",
        "claim_id": claim_id,
    }


@router.post("/{claim_id}/restore")
def restore_claim(
    claim_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    ensure_claim_delete_columns(db)

    claim = (
        db.query(Claim)
        .filter(
            Claim.id == claim_id,
            Claim.organization_id == current_user["organization_id"],
        )
        .first()
    )

    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    claim.is_deleted = False
    claim.deleted_at = None

    db.commit()

    return {
        "message": "Claim restored successfully",
        "claim_id": claim_id,
    }