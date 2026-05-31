from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.claim import Claim
from app.auth_utils import get_current_user
from app.routes.summary import build_underwriting_intelligence

router = APIRouter(prefix="/renewal", tags=["Renewal"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def money(value):
    return float(value or 0)


def is_open(claim):
    return str(claim.status or "").strip().lower() == "open"


def is_flagged(claim):
    return bool(getattr(claim, "flag", None) or getattr(claim, "flagged", None))


def build_underwriter_decision_engine(claims, policy_number=None):
    intelligence = build_underwriting_intelligence(claims)

    total_claims = len(claims)
    open_claims = len([c for c in claims if is_open(c)])
    litigation_claims = len([c for c in claims if getattr(c, "litigation", False)])
    flagged_claims = len([c for c in claims if is_flagged(c)])

    total_incurred = sum(money(c.total_incurred) for c in claims)
    total_reserve = sum(money(c.reserve_amount) for c in claims)
    average_severity = total_incurred / total_claims if total_claims else 0

    large_claims = len([c for c in claims if money(c.total_incurred) >= 100000])
    severe_claims = len([c for c in claims if money(c.total_incurred) >= 250000])

    renewal_score = int(intelligence.get("renewal_score", 75))

    renewal_probability = renewal_score

    if open_claims >= 3:
        renewal_probability -= 8

    if litigation_claims > 0:
        renewal_probability -= 10

    if severe_claims > 0:
        renewal_probability -= 10

    if total_claims >= 10:
        renewal_probability -= 8
    elif total_claims >= 5:
        renewal_probability -= 4

    renewal_probability = max(0, min(100, renewal_probability))

    marketability_score = renewal_probability

    if flagged_claims > 0:
        marketability_score -= min(flagged_claims * 5, 15)

    if total_reserve > 100000:
        marketability_score -= 8

    marketability_score = max(0, min(100, marketability_score))

    if renewal_probability >= 85:
        expected_premium_impact = "Flat to +5%"
        carrier_appetite = "Strong"
        submission_readiness = "Ready for standard renewal marketing"
    elif renewal_probability >= 70:
        expected_premium_impact = "+5% to +15%"
        carrier_appetite = "Moderate"
        submission_readiness = "Marketable with broker narrative"
    elif renewal_probability >= 50:
        expected_premium_impact = "+15% to +35%"
        carrier_appetite = "Limited"
        submission_readiness = "Needs claim narratives and reserve explanations before marketing"
    else:
        expected_premium_impact = "+35% or higher / possible non-renewal concern"
        carrier_appetite = "Restricted"
        submission_readiness = "Not ready without corrective-action documentation"

    underwriting_concerns = []

    if open_claims > 0:
        underwriting_concerns.append(f"{open_claims} open claim(s) may continue developing.")

    if litigation_claims > 0:
        underwriting_concerns.append(f"{litigation_claims} litigated claim(s) create uncertainty.")

    if total_reserve > 0:
        underwriting_concerns.append(f"${total_reserve:,.2f} in open reserves may pressure renewal terms.")

    if large_claims > 0:
        underwriting_concerns.append(f"{large_claims} large claim(s) exceed $100,000.")

    if severe_claims > 0:
        underwriting_concerns.append(f"{severe_claims} severe claim(s) exceed $250,000.")

    if total_claims >= 5:
        underwriting_concerns.append("Claim frequency may raise carrier concerns.")

    if flagged_claims > 0:
        underwriting_concerns.append(f"{flagged_claims} flagged claim(s) require explanation.")

    if not underwriting_concerns:
        underwriting_concerns.append("No major underwriting concerns detected from current loss data.")

    best_market_types = []

    if renewal_probability >= 80:
        best_market_types = [
            "Standard admitted carriers",
            "Regional commercial insurance markets",
            "Preferred renewal markets",
        ]
    elif renewal_probability >= 60:
        best_market_types = [
            "Regional commercial insurance markets",
            "Middle-market carriers",
            "Carriers comfortable with moderate loss activity",
        ]
    elif renewal_probability >= 40:
        best_market_types = [
            "Loss-sensitive markets",
            "Specialty commercial markets",
            "Carriers willing to review corrective-action plans",
        ]
    else:
        best_market_types = [
            "Excess and surplus markets",
            "High-risk commercial markets",
            "Specialty underwriting programs",
        ]

    underwriter_decision_summary = (
        f"LossQ estimates a {renewal_probability}% renewal probability for "
        f"{policy_number or 'the selected account'}. Expected premium impact is "
        f"{expected_premium_impact}, with {carrier_appetite.lower()} carrier appetite. "
        f"The marketability score is {marketability_score}/100. This decision is based on "
        f"{total_claims} claim(s), {open_claims} open claim(s), ${total_incurred:,.2f} "
        f"in total incurred losses, ${total_reserve:,.2f} in reserves, and "
        f"{litigation_claims} litigated claim(s)."
    )

    return {
        "policy_number": policy_number,
        "renewal_probability": renewal_probability,
        "expected_premium_impact": expected_premium_impact,
        "carrier_appetite": carrier_appetite,
        "marketability_score": marketability_score,
        "submission_readiness": submission_readiness,
        "underwriting_concerns": underwriting_concerns,
        "best_market_types": best_market_types,
        "underwriter_decision_summary": underwriter_decision_summary,
        "decision_metrics": {
            "total_claims": total_claims,
            "open_claims": open_claims,
            "litigation_claims": litigation_claims,
            "flagged_claims": flagged_claims,
            "large_claims": large_claims,
            "severe_claims": severe_claims,
            "total_incurred": total_incurred,
            "total_reserve": total_reserve,
            "average_severity": average_severity,
            "renewal_score": renewal_score,
        },
    }


@router.get("/decision")
def renewal_decision(
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

    return build_underwriter_decision_engine(claims, policy_number)


@router.get("/memo")
def renewal_memo(
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

    intelligence = build_underwriting_intelligence(claims)
    decision = build_underwriter_decision_engine(claims, policy_number)

    total_claims = len(claims)
    open_claims = len([c for c in claims if is_open(c)])
    litigation_claims = len([c for c in claims if getattr(c, "litigation", False)])

    top_claims = sorted(
        claims,
        key=lambda c: money(c.total_incurred),
        reverse=True,
    )[:5]

    top_claim_text = "\n".join(
        [
            f"- {c.claim_number} | {c.line_of_business} | ${money(c.total_incurred):,.0f}"
            for c in top_claims
        ]
    )

    memo = f"""
LOSSQ AI RENEWAL MEMO
Selected Policy: {policy_number or "All Policies"}

----------------------------------------

ACCOUNT OVERVIEW

Risk Level: {intelligence["risk_level"]}
Renewal Risk: {intelligence["renewal_risk"]}
Risk Score: {intelligence["risk_score"]}
Submission Strength: {intelligence["submission_strength"]}

Renewal Score: {intelligence.get("renewal_score", "N/A")}/100
Renewal Risk Level: {intelligence.get("renewal_risk_level", "N/A")}

----------------------------------------

UNDERWRITER DECISION ENGINE

Renewal Probability: {decision["renewal_probability"]}%
Expected Premium Impact: {decision["expected_premium_impact"]}
Carrier Appetite: {decision["carrier_appetite"]}
Marketability Score: {decision["marketability_score"]}/100
Submission Readiness: {decision["submission_readiness"]}

----------------------------------------

CLAIM SUMMARY

Total Claims: {total_claims}
Open Claims: {open_claims}
Litigation Claims: {litigation_claims}

Total Incurred:
${intelligence["metrics"]["total_incurred"]:,.2f}

----------------------------------------

TOP SEVERITY CLAIMS

{top_claim_text or "No claims available."}

----------------------------------------

UNDERWRITING SUMMARY

{intelligence["summary"]}

----------------------------------------

BROKER RECOMMENDATION

{intelligence["recommendation"]}

----------------------------------------

CARRIER NARRATIVE

{intelligence["carrier_narrative"]}

----------------------------------------

UNDERWRITER DECISION SUMMARY

{decision["underwriter_decision_summary"]}

----------------------------------------

Generated by LossQ AI
"""

    return {
        "memo": memo,
        "policy_number": policy_number,
        "claims_used": total_claims,
        "decision": decision,
    }