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
    }


def build_carrier_appetite_engine(claims, policy_number=None):
    intelligence = build_underwriting_intelligence(claims)
    decision = build_underwriter_decision_engine(claims, policy_number)

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
    marketability_score = int(decision.get("marketability_score", renewal_score))

    carrier_appetite_score = marketability_score

    if litigation_claims > 0:
        carrier_appetite_score -= 8
    if severe_claims > 0:
        carrier_appetite_score -= 10
    if open_claims >= 3:
        carrier_appetite_score -= 6
    if total_reserve >= 250000:
        carrier_appetite_score -= 10
    elif total_reserve >= 100000:
        carrier_appetite_score -= 5
    if total_claims >= 10:
        carrier_appetite_score -= 8
    elif total_claims >= 5:
        carrier_appetite_score -= 4

    carrier_appetite_score = max(0, min(100, carrier_appetite_score))

    if carrier_appetite_score >= 85:
        carrier_appetite_level = "Preferred"
    elif carrier_appetite_score >= 70:
        carrier_appetite_level = "Strong"
    elif carrier_appetite_score >= 55:
        carrier_appetite_level = "Moderate"
    elif carrier_appetite_score >= 40:
        carrier_appetite_level = "Limited"
    else:
        carrier_appetite_level = "Distressed"

    carrier_matches = [
        {
            "carrier_type": "Preferred Standard Carrier",
            "match_score": max(0, min(100, carrier_appetite_score + 5)),
            "fit": "Best Fit" if carrier_appetite_score >= 80 else "Selective Fit",
            "reason": "Best suited for accounts with clean loss history, low severity, and minimal open claim pressure.",
        },
        {
            "carrier_type": "Regional Commercial Carrier",
            "match_score": max(0, min(100, carrier_appetite_score + 12)),
            "fit": "Best Fit" if carrier_appetite_score >= 60 else "Possible Fit",
            "reason": "Often more flexible for accounts with moderate losses and strong broker explanations.",
        },
        {
            "carrier_type": "Middle Market Carrier",
            "match_score": max(0, min(100, carrier_appetite_score + 2)),
            "fit": "Best Fit" if 55 <= carrier_appetite_score < 85 else "Selective Fit",
            "reason": "Appropriate when the account needs underwriting review but remains marketable.",
        },
        {
            "carrier_type": "Loss-Sensitive Program",
            "match_score": max(0, min(100, 100 - abs(carrier_appetite_score - 55))),
            "fit": "Best Fit" if 40 <= carrier_appetite_score < 70 else "Possible Fit",
            "reason": "Useful when carriers want insured participation because losses or reserves are elevated.",
        },
        {
            "carrier_type": "E&S / Specialty Market",
            "match_score": max(0, min(100, 100 - carrier_appetite_score + 30)),
            "fit": "Best Fit" if carrier_appetite_score < 50 else "Backup Fit",
            "reason": "Best used when standard markets are restricted due to frequency, severity, litigation, or reserve pressure.",
        },
    ]

    carrier_matches = sorted(carrier_matches, key=lambda item: item["match_score"], reverse=True)

    return {
        "policy_number": policy_number,
        "carrier_appetite_score": carrier_appetite_score,
        "carrier_appetite_level": carrier_appetite_level,
        "best_fit_carriers": carrier_matches[:3],
        "poor_fit_carriers": carrier_matches[-2:],
        "carrier_match_reasons": [
            "Carrier appetite is based on frequency, severity, reserve pressure, litigation, and open claim development.",
            f"Total claims reviewed: {total_claims}.",
            f"Open claims reviewed: {open_claims}.",
            f"Litigation claims reviewed: {litigation_claims}.",
            f"Flagged claims reviewed: {flagged_claims}.",
        ],
        "market_strategy": (
            "Target regional and middle-market carriers first. Use a clean broker narrative with claim explanations, reserve updates, and loss-control improvements."
        ),
        "placement_summary": (
            f"LossQ estimates carrier appetite at {carrier_appetite_score}/100, rated {carrier_appetite_level}. "
            f"This is based on {total_claims} claim(s), {open_claims} open claim(s), "
            f"${total_incurred:,.2f} in total incurred losses, ${total_reserve:,.2f} in reserves, "
            f"{litigation_claims} litigated claim(s), {large_claims} large claim(s), "
            f"{severe_claims} severe claim(s), and average severity of ${average_severity:,.2f}."
        ),
    }


def build_submission_readiness_engine(claims, policy_number=None):
    intelligence = build_underwriting_intelligence(claims)
    decision = build_underwriter_decision_engine(claims, policy_number)
    appetite = build_carrier_appetite_engine(claims, policy_number)

    total_claims = len(claims)
    open_claims = len([c for c in claims if is_open(c)])
    litigation_claims = len([c for c in claims if getattr(c, "litigation", False)])
    flagged_claims = len([c for c in claims if is_flagged(c)])
    total_incurred = sum(money(c.total_incurred) for c in claims)
    total_reserve = sum(money(c.reserve_amount) for c in claims)

    readiness_score = 100

    missing_items = []
    required_documents = []
    recommended_actions = []

    required_documents.append("Currently valued loss runs")
    required_documents.append("Carrier account profile")
    required_documents.append("Policy details and effective dates")

    if total_claims > 0:
        required_documents.append("Claims summary by policy period")

    if open_claims > 0:
        readiness_score -= min(open_claims * 7, 25)
        missing_items.append("Updated status for all open claims")
        required_documents.append("Open claim status report")
        recommended_actions.append("Request current adjuster notes and reserve status before marketing.")

    if litigation_claims > 0:
        readiness_score -= min(litigation_claims * 10, 25)
        missing_items.append("Litigation status updates")
        required_documents.append("Defense counsel or litigation update")
        recommended_actions.append("Prepare a litigation narrative explaining current posture, expected resolution, and defense strategy.")

    if flagged_claims > 0:
        readiness_score -= min(flagged_claims * 6, 18)
        missing_items.append("Explanation for flagged claims")
        recommended_actions.append("Address flagged claims before carrier submission.")

    if total_reserve >= 100000:
        readiness_score -= 12
        missing_items.append("Reserve explanation for high open reserves")
        required_documents.append("Reserve development explanation")
        recommended_actions.append("Explain whether reserves are precautionary, expected to reduce, or likely to develop.")

    if total_incurred >= 250000:
        readiness_score -= 10
        missing_items.append("Large loss narrative")
        required_documents.append("Large loss narrative")
        recommended_actions.append("Summarize what happened, what changed, and why the exposure is controlled going forward.")

    if total_claims >= 5:
        readiness_score -= 8
        missing_items.append("Frequency trend explanation")
        required_documents.append("Loss-control or corrective-action plan")
        recommended_actions.append("Document safety, operational, driver, or procedural changes made after the losses.")

    if appetite.get("carrier_appetite_score", 0) < 55:
        readiness_score -= 8
        missing_items.append("Expanded market strategy")
        recommended_actions.append("Prepare for regional, specialty, loss-sensitive, or E&S market review.")

    readiness_score = max(0, min(100, readiness_score))

    if readiness_score >= 85:
        readiness_level = "Excellent"
        carrier_confidence = "High"
        submission_quality = "Strong"
    elif readiness_score >= 70:
        readiness_level = "Good"
        carrier_confidence = "Moderate to High"
        submission_quality = "Marketable"
    elif readiness_score >= 50:
        readiness_level = "Needs Work"
        carrier_confidence = "Moderate"
        submission_quality = "Incomplete"
    else:
        readiness_level = "Not Ready"
        carrier_confidence = "Low"
        submission_quality = "Weak"

    if not missing_items:
        missing_items.append("No major missing submission items detected.")

    if not recommended_actions:
        recommended_actions.append("Proceed with standard renewal submission package.")

    readiness_summary = (
        f"LossQ rates this submission {readiness_score}/100, or {readiness_level}. "
        f"Carrier confidence is {carrier_confidence}, and submission quality is {submission_quality}. "
        f"The review considered {total_claims} claim(s), {open_claims} open claim(s), "
        f"{litigation_claims} litigated claim(s), {flagged_claims} flagged claim(s), "
        f"${total_incurred:,.2f} in total incurred losses, and ${total_reserve:,.2f} in reserves."
    )

    return {
        "policy_number": policy_number,
        "submission_readiness_score": readiness_score,
        "submission_readiness_level": readiness_level,
        "missing_items": missing_items,
        "required_documents": required_documents,
        "recommended_actions": recommended_actions,
        "carrier_confidence": carrier_confidence,
        "submission_quality": submission_quality,
        "readiness_summary": readiness_summary,
        "readiness_metrics": {
            "total_claims": total_claims,
            "open_claims": open_claims,
            "litigation_claims": litigation_claims,
            "flagged_claims": flagged_claims,
            "total_incurred": total_incurred,
            "total_reserve": total_reserve,
            "renewal_score": intelligence.get("renewal_score"),
            "marketability_score": decision.get("marketability_score"),
            "carrier_appetite_score": appetite.get("carrier_appetite_score"),
        },
    }
def build_carrier_match_engine(claims, policy_number=None):
    appetite = build_carrier_appetite_engine(claims, policy_number)
    decision = build_underwriter_decision_engine(claims, policy_number)

    appetite_score = appetite.get("carrier_appetite_score", 50)
    renewal_probability = decision.get("renewal_probability", 50)

    carriers = [
        {
            "carrier": "Travelers",
            "base": 88,
            "strength": "Strong middle-market appetite",
        },
        {
            "carrier": "Liberty Mutual",
            "base": 85,
            "strength": "Broad commercial appetite",
        },
        {
            "carrier": "Nationwide",
            "base": 83,
            "strength": "Good frequency tolerance",
        },
        {
            "carrier": "Hanover",
            "base": 80,
            "strength": "Regional underwriting flexibility",
        },
        {
            "carrier": "CNA",
            "base": 78,
            "strength": "Strong risk-control focus",
        },
        {
            "carrier": "Auto-Owners",
            "base": 76,
            "strength": "Preferred commercial risks",
        },
        {
            "carrier": "Progressive Commercial",
            "base": 74,
            "strength": "Commercial auto focus",
        },
        {
            "carrier": "Berkley",
            "base": 72,
            "strength": "Specialty commercial underwriting",
        },
    ]

    matches = []

    for carrier in carriers:
        score = carrier["base"]

        score += (appetite_score - 70) * 0.25
        score += (renewal_probability - 70) * 0.15

        score = int(max(0, min(100, score)))

        if score >= 85:
            fit = "Excellent"
        elif score >= 75:
            fit = "Strong"
        elif score >= 65:
            fit = "Moderate"
        else:
            fit = "Limited"

        matches.append(
            {
                "carrier": carrier["carrier"],
                "match_score": score,
                "fit": fit,
                "reason": carrier["strength"],
            }
        )

    matches = sorted(
        matches,
        key=lambda x: x["match_score"],
        reverse=True,
    )

    return {
        "policy_number": policy_number,
        "top_carriers": matches[:5],
        "recommended_carrier": matches[0]["carrier"],
        "recommended_score": matches[0]["match_score"],
        "carrier_match_summary": (
            f"LossQ recommends {matches[0]['carrier']} "
            f"as the strongest carrier fit with a "
            f"{matches[0]['match_score']}/100 match score."
        ),
    }

@router.get("/decision")
def renewal_decision(
    policy_number: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    query = db.query(Claim).filter(Claim.organization_id == current_user["organization_id"])

    if policy_number:
        query = query.filter(Claim.policy_number == policy_number)

    claims = query.all()
    return build_underwriter_decision_engine(claims, policy_number)


@router.get("/carrier-appetite")
def carrier_appetite(
    policy_number: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    query = db.query(Claim).filter(Claim.organization_id == current_user["organization_id"])

    if policy_number:
        query = query.filter(Claim.policy_number == policy_number)

    claims = query.all()
    return build_carrier_appetite_engine(claims, policy_number)


@router.get("/submission-readiness")
def submission_readiness(
    policy_number: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    query = db.query(Claim).filter(Claim.organization_id == current_user["organization_id"])

    if policy_number:
        query = query.filter(Claim.policy_number == policy_number)

    claims = query.all()
    return build_submission_readiness_engine(claims, policy_number)


@router.get("/memo")
def renewal_memo(
    policy_number: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    query = db.query(Claim).filter(Claim.organization_id == current_user["organization_id"])

    if policy_number:
        query = query.filter(Claim.policy_number == policy_number)

    claims = query.all()

    intelligence = build_underwriting_intelligence(claims)
    decision = build_underwriter_decision_engine(claims, policy_number)
    appetite = build_carrier_appetite_engine(claims, policy_number)
    readiness = build_submission_readiness_engine(claims, policy_number)

    total_claims = len(claims)
    open_claims = len([c for c in claims if is_open(c)])
    litigation_claims = len([c for c in claims if getattr(c, "litigation", False)])

    top_claims = sorted(claims, key=lambda c: money(c.total_incurred), reverse=True)[:5]

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

CARRIER APPETITE ENGINE

Carrier Appetite Score: {appetite["carrier_appetite_score"]}/100
Carrier Appetite Level: {appetite["carrier_appetite_level"]}

Market Strategy:
{appetite["market_strategy"]}

Placement Summary:
{appetite["placement_summary"]}

----------------------------------------

SUBMISSION READINESS ENGINE

Submission Readiness Score: {readiness["submission_readiness_score"]}/100
Submission Readiness Level: {readiness["submission_readiness_level"]}
Carrier Confidence: {readiness["carrier_confidence"]}
Submission Quality: {readiness["submission_quality"]}

Readiness Summary:
{readiness["readiness_summary"]}

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

Generated by LossQ AI
"""

    return {
        "memo": memo,
        "policy_number": policy_number,
        "claims_used": total_claims,
        "decision": decision,
        "carrier_appetite": appetite,
        "submission_readiness": readiness,
    }

@router.get("/carrier-match")
def carrier_match(
    policy_number: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    query = db.query(Claim).filter(
        Claim.organization_id == current_user["organization_id"]
    )

    if policy_number:
        query = query.filter(
            Claim.policy_number == policy_number
        )

    claims = query.all()

    return build_carrier_match_engine(
        claims,
        policy_number,
    )