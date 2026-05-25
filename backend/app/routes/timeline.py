from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from collections import defaultdict
from datetime import datetime

from app.database import SessionLocal
from app.models.claim import Claim
from app.auth_utils import get_current_user

router = APIRouter(prefix="/timeline", tags=["Timeline Analytics"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_year(date_value):
    if not date_value:
        return "Unknown"

    text = str(date_value)

    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            return str(datetime.strptime(text, fmt).year)
        except Exception:
            pass

    return text[:4] if len(text) >= 4 else "Unknown"


@router.get("/analytics")
def timeline_analytics(
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

    incurred_by_year = defaultdict(float)
    open_aging = {
        "0-3 Months": 0,
        "3-6 Months": 0,
        "6-12 Months": 0,
        "12+ Months": 0,
        "Unknown": 0,
    }

    severity_heatmap = {
        "Low": 0,
        "Moderate": 0,
        "Severe": 0,
        "Catastrophic": 0,
    }

    by_line = defaultdict(float)

    today = datetime.now()

    for claim in claims:
        total = float(claim.total_incurred or 0)
        reserve = float(claim.reserve_amount or 0)

        year = get_year(claim.date_of_loss)
        incurred_by_year[year] += total

        line = claim.line_of_business or "Unknown"
        by_line[line] += total

        if total >= 250000:
            severity_heatmap["Catastrophic"] += 1
        elif total >= 100000:
            severity_heatmap["Severe"] += 1
        elif total >= 25000:
            severity_heatmap["Moderate"] += 1
        else:
            severity_heatmap["Low"] += 1

        if str(claim.status).lower() == "open":
            try:
                loss_date = None
                text = str(claim.date_of_loss)

                for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
                    try:
                        loss_date = datetime.strptime(text, fmt)
                        break
                    except Exception:
                        pass

                if not loss_date:
                    open_aging["Unknown"] += 1
                    continue

                days_open = (today - loss_date).days

                if days_open <= 90:
                    open_aging["0-3 Months"] += 1
                elif days_open <= 180:
                    open_aging["3-6 Months"] += 1
                elif days_open <= 365:
                    open_aging["6-12 Months"] += 1
                else:
                    open_aging["12+ Months"] += 1

            except Exception:
                open_aging["Unknown"] += 1

    total_incurred = sum(float(c.total_incurred or 0) for c in claims)
    total_reserve = sum(float(c.reserve_amount or 0) for c in claims)
    open_claims = len([c for c in claims if str(c.status).lower() == "open"])

    trend_note = "Not enough yearly claim data to determine trend."

    years = sorted([y for y in incurred_by_year.keys() if y != "Unknown"])

    if len(years) >= 2:
        first = incurred_by_year[years[0]]
        last = incurred_by_year[years[-1]]

        if last > first:
          trend_note = "Loss severity trend appears to be increasing."
        elif last < first:
          trend_note = "Loss severity trend appears to be improving."
        else:
          trend_note = "Loss severity trend appears stable."

    reserve_pressure = "Low"

    if total_reserve >= 250000:
        reserve_pressure = "High"
    elif total_reserve >= 75000:
        reserve_pressure = "Moderate"

    return {
        "total_claims": len(claims),
        "open_claims": open_claims,
        "total_incurred": total_incurred,
        "total_reserve": total_reserve,
        "reserve_pressure": reserve_pressure,
        "trend_note": trend_note,
        "incurred_by_year": dict(incurred_by_year),
        "open_claim_aging": open_aging,
        "severity_heatmap": severity_heatmap,
        "incurred_by_line": dict(by_line),
    }