from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.claim import Claim
from app.auth_utils import get_current_user
from app.routes.summary import build_underwriting_intelligence
from app.routes.renewal import (
    build_underwriter_decision_engine,
    build_carrier_appetite_engine,
    build_submission_readiness_engine,
    build_carrier_match_engine,
    build_premium_forecast_engine,
    money,
    is_open,
)

router = APIRouter(prefix="/submission-builder", tags=["Submission Builder"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def build_submission_package(claims, policy_number=None):
    intelligence = build_underwriting_intelligence(claims)
    decision = build_underwriter_decision_engine(claims, policy_number)
    appetite = build_carrier_appetite_engine(claims, policy_number)
    readiness = build_submission_readiness_engine(claims, policy_number)
    carrier_match = build_carrier_match_engine(claims, policy_number)
    forecast = build_premium_forecast_engine(claims, policy_number)

    total_claims = len(claims)
    open_claims = len([c for c in claims if is_open(c)])
    litigation_claims = len([c for c in claims if getattr(c, "litigation", False)])
    total_incurred = sum(money(c.total_incurred) for c in claims)
    total_reserve = sum(money(c.reserve_amount) for c in claims)

    top_claims = sorted(
        claims,
        key=lambda c: money(c.total_incurred),
        reverse=True,
    )[:5]

    loss_explanations = []

    for claim in top_claims:
        loss_explanations.append(
            {
                "claim_number": claim.claim_number or "Unknown",
                "line_of_business": claim.line_of_business or "Unknown",
                "status": claim.status or "Unknown",
                "total_incurred": money(claim.total_incurred),
                "reserve_amount": money(claim.reserve_amount),
                "explanation": (
                    f"Claim {claim.claim_number or 'Unknown'} involved "
                    f"{claim.line_of_business or 'the applicable line of business'} "
                    f"with total incurred of ${money(claim.total_incurred):,.0f}. "
                    f"The claim is currently marked as {claim.status or 'unknown'}."
                ),
                "broker_position": (
                    "Provide current claim status, reserve development, corrective action, "
                    "and any available closure timeline before carrier review."
                ),
            }
        )

    if not loss_explanations:
        loss_explanations.append(
            {
                "claim_number": "N/A",
                "line_of_business": "N/A",
                "status": "N/A",
                "total_incurred": 0,
                "reserve_amount": 0,
                "explanation": "No claim activity was found for this policy.",
                "broker_position": "Position the account as having minimal loss activity.",
            }
        )

    underwriter_narrative = (
        f"The selected account has {total_claims} claim(s), {open_claims} open claim(s), "
        f"and {litigation_claims} litigated claim(s). Total incurred losses are "
        f"${total_incurred:,.0f}, with ${total_reserve:,.0f} in open reserves. "
        f"LossQ rates the renewal risk as {intelligence.get('renewal_risk_level', 'Not Rated')} "
        f"with a renewal score of {intelligence.get('renewal_score', 'N/A')}/100. "
        f"The account has an estimated renewal probability of "
        f"{decision.get('renewal_probability', 'N/A')}% and carrier appetite is rated "
        f"{appetite.get('carrier_appetite_level', 'N/A')}."
    )

    carrier_submission_email = (
        f"Subject: Renewal Submission - Policy {policy_number or 'Selected Account'}\n\n"
        f"Dear Underwriter,\n\n"
        f"Please find the renewal submission for policy {policy_number or 'the selected account'}.\n\n"
        f"The account has been reviewed through LossQ's underwriting intelligence engine. "
        f"The renewal score is {intelligence.get('renewal_score', 'N/A')}/100, "
        f"carrier appetite is rated {appetite.get('carrier_appetite_level', 'N/A')}, "
        f"and submission readiness is rated {readiness.get('submission_readiness_level', 'N/A')}.\n\n"
        f"Loss activity includes {total_claims} claim(s), {open_claims} open claim(s), "
        f"${total_incurred:,.0f} in total incurred losses, and ${total_reserve:,.0f} "
        f"in reserves.\n\n"
        f"We believe this account should receive underwriting consideration based on the attached "
        f"loss analysis, carrier strategy, and renewal positioning.\n\n"
        f"Thank you,\n"
        f"Broker Team"
    )

    executive_summary = (
        f"Policy {policy_number or 'Selected Account'} has been reviewed for renewal strategy, "
        f"carrier appetite, submission readiness, and premium forecast. LossQ projects an expected "
        f"renewal premium of ${forecast.get('expected_renewal_premium', 0):,.0f}, representing an "
        f"estimated {forecast.get('expected_increase_percent', 0)}% increase. "
        f"The recommended carrier is {carrier_match.get('recommended_carrier', 'N/A')} with a "
        f"{carrier_match.get('recommended_score', 'N/A')}/100 match score."
    )

    broker_marketing_memo = (
        f"Marketing Strategy:\n"
        f"{appetite.get('market_strategy', 'No market strategy available.')}\n\n"
        f"Recommended Carrier:\n"
        f"{carrier_match.get('recommended_carrier', 'N/A')} "
        f"({carrier_match.get('recommended_score', 'N/A')}/100 match score)\n\n"
        f"Submission Readiness:\n"
        f"{readiness.get('submission_readiness_level', 'N/A')} "
        f"({readiness.get('submission_readiness_score', 'N/A')}/100)\n\n"
        f"Premium Forecast:\n"
        f"Expected increase: {forecast.get('expected_increase_percent', 'N/A')}%"
    )

    renewal_strategy = (
        f"Primary strategy is to lead with the strongest carrier match, "
        f"{carrier_match.get('recommended_carrier', 'N/A')}, while also preparing alternative "
        f"regional, middle-market, or specialty markets depending on carrier response. "
        f"The broker should address open claims, reserve pressure, litigation status, and any "
        f"large-loss explanations before submission."
    )

    return {
        "policy_number": policy_number,
        "underwriter_narrative": underwriter_narrative,
        "carrier_submission_email": carrier_submission_email,
        "executive_summary": executive_summary,
        "loss_explanations": loss_explanations,
        "broker_marketing_memo": broker_marketing_memo,
        "renewal_strategy": renewal_strategy,
        "supporting_intelligence": {
            "summary": intelligence,
            "decision": decision,
            "carrier_appetite": appetite,
            "submission_readiness": readiness,
            "carrier_match": carrier_match,
            "premium_forecast": forecast,
        },
    }


@router.get("/")
def submission_builder(
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

    return build_submission_package(claims, policy_number)