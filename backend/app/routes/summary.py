from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.claim import Claim
from app.auth_utils import get_current_user

router = APIRouter(prefix="/summary", tags=["Summary"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def build_underwriting_intelligence(claims):
    total_claims = len(claims)
    open_claims = len([c for c in claims if c.status == "Open"])
    closed_claims = len([c for c in claims if c.status == "Closed"])
    litigation_claims = len([c for c in claims if c.litigation])

    total_paid = sum(float(c.paid_amount or 0) for c in claims)
    total_reserve = sum(float(c.reserve_amount or 0) for c in claims)
    total_incurred = sum(float(c.total_incurred or 0) for c in claims)

    large_claims = len([c for c in claims if float(c.total_incurred or 0) >= 100000])
    high_reserve_claims = len([c for c in claims if float(c.reserve_amount or 0) > float(c.paid_amount or 0)])
    wc_claims = len([c for c in claims if "workers" in str(c.line_of_business).lower()])

    score = 0
    score += open_claims * 10
    score += litigation_claims * 25
    score += large_claims * 20

    if total_claims >= 10:
        score += 20
    elif total_claims >= 5:
        score += 10

    score += high_reserve_claims * 5
    score += wc_claims * 5

    risk_level = "Low"
    if score >= 70:
        risk_level = "High"
    elif score >= 35:
        risk_level = "Moderate"

    renewal_risk = "GREEN"
    if score >= 80:
        renewal_risk = "RED"
    elif score >= 40:
        renewal_risk = "YELLOW"

    carrier_narrative = (
        f"The account presents a {risk_level.lower()} underwriting profile with "
        f"{total_claims} claim(s), {open_claims} open claim(s), and "
        f"{litigation_claims} litigation-related claim(s). Total incurred losses are "
        f"${total_incurred:,.2f}, with ${total_reserve:,.2f} in outstanding reserves."
    )

    client_narrative = (
        f"Your current loss history shows {total_claims} claim(s), including "
        f"{open_claims} open claim(s). Open reserves, severe losses, and litigated claims "
        f"may affect renewal pricing."
    )

    recommendation = "Proceed with standard review."

    if renewal_risk == "RED":
        recommendation = (
            "High renewal concern. Prepare a detailed broker narrative, address open reserves, "
            "explain litigation status, gather updated loss runs, and provide loss-control documentation."
        )
    elif renewal_risk == "YELLOW":
        recommendation = (
            "Moderate renewal concern. Review open claims, reserve adequacy, claim narratives, "
            "and loss-control improvements before submission."
        )

    missing_items = []

    if open_claims > 0:
        missing_items.append("Updated currently valued loss runs")

    if litigation_claims > 0:
        missing_items.append("Detailed claim narratives for litigated claims")

    if large_claims > 0:
        missing_items.append("Loss-control explanation for severe claims")

    if wc_claims > 0:
        missing_items.append("Updated OSHA / safety program documentation")

    if total_claims >= 5:
        missing_items.append("Driver schedules and unit list")

    recommended_actions = []

    if high_reserve_claims > 0:
        recommended_actions.append("Explain reserve development and claim strategy")

    if litigation_claims > 0:
        recommended_actions.append("Provide defense counsel updates and litigation status")

    if open_claims >= 3:
        recommended_actions.append("Review aging open claims before marketing account")

    if large_claims > 0:
        recommended_actions.append("Prepare broker narrative addressing severe losses")

    if total_claims >= 5:
        recommended_actions.append("Summarize frequency trends and corrective actions")

    submission_strength = "Strong"

    if renewal_risk == "RED":
        submission_strength = "Weak"
    elif renewal_risk == "YELLOW":
        submission_strength = "Moderate"

    return {
        "submission_strength": submission_strength,
        "missing_items": missing_items,
        "recommended_actions": recommended_actions,
        "summary": (
            f"{total_claims} claim(s) identified. {open_claims} open and {closed_claims} closed. "
            f"Total paid is ${total_paid:,.2f}, reserves are ${total_reserve:,.2f}, "
            f"and total incurred is ${total_incurred:,.2f}. "
            f"{litigation_claims} litigation-related claim(s) detected."
        ),
        "risk_level": risk_level,
        "risk_score": score,
        "renewal_risk": renewal_risk,
        "recommendation": recommendation,
        "carrier_narrative": carrier_narrative,
        "client_narrative": client_narrative,
        "metrics": {
            "total_claims": total_claims,
            "open_claims": open_claims,
            "closed_claims": closed_claims,
            "litigation_claims": litigation_claims,
            "large_claims": large_claims,
            "high_reserve_claims": high_reserve_claims,
            "wc_claims": wc_claims,
            "total_paid": total_paid,
            "total_reserve": total_reserve,
            "total_incurred": total_incurred,
        },
    }


@router.get("/underwriting")
def underwriting_summary(
    policy_number: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    query = db.query(Claim).filter(
        Claim.organization_id == current_user["organization_id"]
    )

    if policy_number:
        query = query.filter(Claim.policy_number == policy_number)

    claims = query.all()

    return build_underwriting_intelligence(claims)