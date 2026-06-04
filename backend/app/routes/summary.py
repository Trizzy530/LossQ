from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
import json

from app.database import SessionLocal
from app.models.claim import Claim
from app.models.account_profile import AccountProfile
from app.auth_utils import get_current_user

router = APIRouter(prefix="/summary", tags=["Summary"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def money(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


def normalize_policy(value):
    return clean_text(value).upper()


def claim_status(value):
    return clean_text(value).lower()


def is_open_claim(claim):
    return claim_status(getattr(claim, "status", "")) in ["open", "reopened", "re-opened"]


def has_litigation(claim):
    raw = getattr(claim, "litigation", False)
    if isinstance(raw, bool):
        return raw
    return clean_text(raw).lower() in ["true", "yes", "y", "1", "litigation", "litigated"]


def is_flagged_claim(claim):
    flagged = getattr(claim, "flagged", None)

    if flagged is None:
        flagged = getattr(claim, "flag", None)

    if isinstance(flagged, bool):
        return flagged

    flagged_text = clean_text(flagged).lower()
    return flagged_text in ["true", "yes", "y", "1", "flagged"] or bool(flagged_text)


def safe_profile_dict(profile):
    if not profile:
        return {}

    data = {}

    for key in [
        "id",
        "business_name",
        "carrier_name",
        "writing_carrier",
        "agency_name",
        "account_number",
        "customer_number",
        "producer_number",
        "policy_number",
        "effective_date",
        "expiration_date",
        "evaluation_date",
        "policies",
        "validation",
    ]:
        if hasattr(profile, key):
            data[key] = getattr(profile, key)

    return data


def parse_policies(raw_policies):
    if not raw_policies:
        return []

    if isinstance(raw_policies, list):
        return raw_policies

    if isinstance(raw_policies, str):
        try:
            parsed = json.loads(raw_policies)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []

    return []


def get_profile_for_policy(db: Session, current_user: dict, policy_number: str | None):
    org_id = current_user["organization_id"]

    if policy_number:
        profile = (
            db.query(AccountProfile)
            .filter(AccountProfile.organization_id == org_id)
            .filter(AccountProfile.policy_number == policy_number)
            .first()
        )

        if profile:
            return profile

    return (
        db.query(AccountProfile)
        .filter(AccountProfile.organization_id == org_id)
        .order_by(AccountProfile.id.desc())
        .first()
    )


def get_account_policy_numbers(db: Session, current_user: dict, policy_number: str | None):
    profile = get_profile_for_policy(db, current_user, policy_number)
    profile_data = safe_profile_dict(profile)

    policies = parse_policies(profile_data.get("policies"))

    policy_numbers = []

    for item in policies:
        if isinstance(item, dict):
            number = normalize_policy(item.get("policy_number"))
            if number:
                policy_numbers.append(number)

    if not policy_numbers and policy_number:
        policy_numbers.append(normalize_policy(policy_number))

    if not policy_numbers and profile_data.get("policy_number"):
        policy_numbers.append(normalize_policy(profile_data.get("policy_number")))

    policy_numbers = list(dict.fromkeys([item for item in policy_numbers if item]))

    return policy_numbers, profile_data


def get_claims_for_account(db: Session, current_user: dict, policy_number: str | None = None):
    org_id = current_user["organization_id"]
    policy_numbers, profile_data = get_account_policy_numbers(db, current_user, policy_number)

    query = db.query(Claim).filter(Claim.organization_id == org_id)

    if policy_numbers:
        query = query.filter(func.upper(Claim.policy_number).in_(policy_numbers))
    elif policy_number:
        query = query.filter(func.upper(Claim.policy_number) == normalize_policy(policy_number))
    else:
        query = query.filter(False)

    claims = query.all()

    return claims, policy_numbers, profile_data


def build_renewal_risk_engine(claims):
    total_claims = len(claims)
    open_claims = len([c for c in claims if is_open_claim(c)])
    closed_claims = len([c for c in claims if claim_status(getattr(c, "status", "")) == "closed"])
    litigation_claims = len([c for c in claims if has_litigation(c)])
    flagged_claims = len([c for c in claims if is_flagged_claim(c)])

    total_paid = sum(money(getattr(c, "paid_amount", 0)) for c in claims)
    total_reserve = sum(money(getattr(c, "reserve_amount", 0)) for c in claims)
    total_incurred = sum(money(getattr(c, "total_incurred", 0)) for c in claims)

    average_severity = total_incurred / total_claims if total_claims else 0
    open_reserve_pressure = total_reserve / total_incurred if total_incurred > 0 else 0

    large_claims = len([c for c in claims if money(getattr(c, "total_incurred", 0)) >= 100000])
    severe_claims = len([c for c in claims if money(getattr(c, "total_incurred", 0)) >= 250000])
    high_reserve_claims = len(
        [
            c
            for c in claims
            if money(getattr(c, "reserve_amount", 0)) > money(getattr(c, "paid_amount", 0))
            and money(getattr(c, "reserve_amount", 0)) > 0
        ]
    )

    renewal_score = 100

    renewal_score -= min(total_claims * 3, 18)
    renewal_score -= min(open_claims * 8, 24)
    renewal_score -= min(litigation_claims * 12, 24)
    renewal_score -= min(flagged_claims * 8, 20)
    renewal_score -= min(large_claims * 10, 20)
    renewal_score -= min(severe_claims * 15, 30)
    renewal_score -= min(high_reserve_claims * 5, 15)

    if total_incurred >= 1000000:
        renewal_score -= 25
    elif total_incurred >= 500000:
        renewal_score -= 18
    elif total_incurred >= 250000:
        renewal_score -= 10
    elif total_incurred >= 100000:
        renewal_score -= 5

    if total_reserve >= 500000:
        renewal_score -= 20
    elif total_reserve >= 250000:
        renewal_score -= 14
    elif total_reserve >= 100000:
        renewal_score -= 8
    elif total_reserve >= 50000:
        renewal_score -= 4

    if average_severity >= 250000:
        renewal_score -= 20
    elif average_severity >= 100000:
        renewal_score -= 12
    elif average_severity >= 50000:
        renewal_score -= 6

    if open_reserve_pressure >= 0.75:
        renewal_score -= 15
    elif open_reserve_pressure >= 0.50:
        renewal_score -= 10
    elif open_reserve_pressure >= 0.25:
        renewal_score -= 5

    renewal_score = max(0, min(100, round(renewal_score)))

    if renewal_score >= 80:
        renewal_risk_level = "Low"
    elif renewal_score >= 60:
        renewal_risk_level = "Moderate"
    elif renewal_score >= 40:
        renewal_risk_level = "High"
    else:
        renewal_risk_level = "Critical"

    renewal_drivers = []

    if total_claims == 0:
        renewal_drivers.append("No policy-specific claims were found for the selected account or child policies.")
    else:
        renewal_drivers.append(f"{total_claims} account-specific claim(s) identified.")

    if open_claims > 0:
        renewal_drivers.append(f"{open_claims} open claim(s) may create uncertainty at renewal.")

    if total_incurred > 0:
        renewal_drivers.append(f"Total incurred losses are ${total_incurred:,.2f}.")

    if total_reserve > 0:
        renewal_drivers.append(f"Outstanding reserves total ${total_reserve:,.2f}.")

    if litigation_claims > 0:
        renewal_drivers.append(f"{litigation_claims} claim(s) involve litigation.")

    if flagged_claims > 0:
        renewal_drivers.append(f"{flagged_claims} flagged claim(s) require underwriting review.")

    if large_claims > 0:
        renewal_drivers.append(f"{large_claims} large claim(s) exceed $100,000 in incurred losses.")

    if average_severity >= 50000:
        renewal_drivers.append(f"Average claim severity is ${average_severity:,.2f}.")

    if open_reserve_pressure >= 0.25:
        renewal_drivers.append(
            f"Open reserve pressure is elevated at {open_reserve_pressure:.0%} of total incurred."
        )

    carrier_concerns = []

    if open_claims > 0:
        carrier_concerns.append("Open claims may continue to develop before renewal.")

    if total_reserve >= 50000:
        carrier_concerns.append("Outstanding reserves may affect final loss development and pricing.")

    if litigation_claims > 0:
        carrier_concerns.append("Litigation increases uncertainty around claim closure and ultimate severity.")

    if flagged_claims > 0:
        carrier_concerns.append("Flagged claims should be explained before carrier submission.")

    if total_claims >= 5:
        carrier_concerns.append("Claim frequency may raise concerns about controls, safety, or operations.")

    if large_claims > 0:
        carrier_concerns.append("Large losses may require detailed corrective-action documentation.")

    if not carrier_concerns:
        carrier_concerns.append("No major carrier concerns detected from the current account-specific loss data.")

    if renewal_risk_level == "Low":
        broker_recommendation = (
            "Proceed with standard renewal marketing. Confirm loss runs are currently valued and highlight favorable loss performance."
        )
    elif renewal_risk_level == "Moderate":
        broker_recommendation = (
            "Prepare a broker narrative explaining open claims, reserves, and corrective actions before marketing."
        )
    elif renewal_risk_level == "High":
        broker_recommendation = (
            "Build a detailed renewal strategy with claim narratives, reserve updates, litigation status, and loss-control documentation."
        )
    else:
        broker_recommendation = (
            "Treat as a critical renewal. Obtain updated loss runs, claim narratives, litigation updates, reserve explanations, and a corrective-action plan before approaching markets."
        )

    renewal_summary = (
        f"The selected account has a renewal score of {renewal_score}/100, which indicates "
        f"{renewal_risk_level.lower()} renewal risk. The score is based on {total_claims} claim(s), "
        f"{open_claims} open claim(s), ${total_incurred:,.2f} in total incurred losses, "
        f"${total_reserve:,.2f} in reserves, {litigation_claims} litigated claim(s), and "
        f"{flagged_claims} flagged claim(s)."
    )

    return {
        "renewal_score": renewal_score,
        "renewal_risk_level": renewal_risk_level,
        "renewal_drivers": renewal_drivers,
        "carrier_concerns": carrier_concerns,
        "broker_recommendation": broker_recommendation,
        "renewal_summary": renewal_summary,
        "renewal_metrics": {
            "total_claims": total_claims,
            "open_claims": open_claims,
            "closed_claims": closed_claims,
            "litigation_claims": litigation_claims,
            "flagged_claims": flagged_claims,
            "large_claims": large_claims,
            "severe_claims": severe_claims,
            "high_reserve_claims": high_reserve_claims,
            "total_paid": total_paid,
            "total_reserve": total_reserve,
            "total_incurred": total_incurred,
            "average_severity": average_severity,
            "open_reserve_pressure": open_reserve_pressure,
        },
    }


def build_underwriting_intelligence(claims):
    total_claims = len(claims)
    open_claims = len([c for c in claims if is_open_claim(c)])
    closed_claims = len([c for c in claims if claim_status(getattr(c, "status", "")) == "closed"])
    litigation_claims = len([c for c in claims if has_litigation(c)])

    total_paid = sum(money(getattr(c, "paid_amount", 0)) for c in claims)
    total_reserve = sum(money(getattr(c, "reserve_amount", 0)) for c in claims)
    total_incurred = sum(money(getattr(c, "total_incurred", 0)) for c in claims)

    large_claims = len([c for c in claims if money(getattr(c, "total_incurred", 0)) >= 100000])
    high_reserve_claims = len(
        [
            c
            for c in claims
            if money(getattr(c, "reserve_amount", 0)) > money(getattr(c, "paid_amount", 0))
            and money(getattr(c, "reserve_amount", 0)) > 0
        ]
    )
    wc_claims = len([c for c in claims if "workers" in clean_text(getattr(c, "line_of_business", "")).lower()])

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
        f"The current loss history shows {total_claims} claim(s), including "
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

    underwriting_response = {
        "submission_strength": submission_strength,
        "missing_items": missing_items,
        "recommended_actions": recommended_actions,
        "summary": (
            f"{total_claims} account-specific claim(s) identified. {open_claims} open and {closed_claims} closed. "
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

    renewal_response = build_renewal_risk_engine(claims)

    return {
        **underwriting_response,
        **renewal_response,
    }


@router.get("/underwriting")
def underwriting_summary(
    policy_number: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    claims, policy_numbers_used, profile_data = get_claims_for_account(db, current_user, policy_number)

    result = build_underwriting_intelligence(claims)

    return {
        **result,
        "policy_number": policy_number,
        "policy_numbers_used": policy_numbers_used,
        "claims_used": len(claims),
        "account_profile": profile_data,
    }