from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from collections import defaultdict

from app.database import SessionLocal
from app.models.claim import Claim
from app.auth_utils import get_current_user

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/dashboard")
def analytics_dashboard(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    claims = db.query(Claim).filter(
        Claim.organization_id == current_user["organization_id"]
    ).all()

    by_line = defaultdict(float)
    by_status = defaultdict(int)
    by_year = defaultdict(float)

    litigation_count = 0
    open_reserve_total = 0

    for claim in claims:
        line = claim.line_of_business or "Unknown"
        status = claim.status or "Unknown"
        incurred = float(claim.total_incurred or 0)
        reserve = float(claim.reserve_amount or 0)

        by_line[line] += incurred
        by_status[status] += 1

        if claim.date_of_loss and len(str(claim.date_of_loss)) >= 4:
            year = str(claim.date_of_loss)[:4]
            by_year[year] += incurred

        if claim.litigation:
            litigation_count += 1

        if status == "Open":
            open_reserve_total += reserve

    total_incurred = sum(float(c.total_incurred or 0) for c in claims)
    total_claims = len(claims)

    avg_claim = total_incurred / total_claims if total_claims else 0

    reserve_pressure = "Low"
    if open_reserve_total >= 250000:
        reserve_pressure = "High"
    elif open_reserve_total >= 75000:
        reserve_pressure = "Moderate"

    trend_note = "Not enough year-based claim data to determine trend."
    if len(by_year.keys()) >= 2:
        years = sorted(by_year.keys())
        first = by_year[years[0]]
        last = by_year[years[-1]]

        if last > first:
            trend_note = "Total incurred trend appears to be increasing."
        elif last < first:
            trend_note = "Total incurred trend appears to be improving."
        else:
            trend_note = "Total incurred trend appears stable."

    return {
        "total_claims": total_claims,
        "total_incurred": total_incurred,
        "average_claim": avg_claim,
        "litigation_count": litigation_count,
        "open_reserve_total": open_reserve_total,
        "reserve_pressure": reserve_pressure,
        "trend_note": trend_note,
        "incurred_by_line": dict(by_line),
        "claims_by_status": dict(by_status),
        "incurred_by_year": dict(by_year),
    }