from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.auth_utils import get_current_user
from app.routes.summary import build_underwriting_intelligence, get_claims_for_account
from app.routes.renewal import (
    build_underwriter_decision_engine,
    build_carrier_appetite_engine,
    build_submission_readiness_engine,
    build_carrier_match_engine,
    build_premium_forecast_engine,
    money,
    is_open,
    is_litigated,
)

router = APIRouter(prefix="/submission-builder", tags=["Submission Builder"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def build_submission_package(claims, policy_number=None, policy_numbers_used=None, profile_data=None):
    policy_numbers_used = policy_numbers_used or []
    profile_data = profile_data or {}

    intelligence = build_underwriting_intelligence(claims)
    decision = build_underwriter_decision_engine(claims, policy_number)
    appetite = build_carrier_appetite_engine(claims, policy_number)
    readiness = build_submission_readiness_engine(claims, policy_number)
    carrier_match = build_carrier_match_engine(claims, policy_number)
    forecast = build_premium_forecast_engine(claims, policy_number)

    total_claims = len(claims)
    open_claims = len([c for c in claims if is_open(c)])
    litigation_claims = len([c for c in claims if is_litigated(c)])
    total_incurred = sum(money(getattr(c, "total_incurred", 0)) for c in claims)
    total_reserve = sum(money(getattr(c, "reserve_amount", 0)) for c in claims)

    top_claims = sorted(
        claims,
        key=lambda c: money(getattr(c, "total_incurred", 0)),
        reverse=True,
    )[:5]

    loss_explanations = []

    for claim in top_claims:
        loss_explanations.append(
            {
                "claim_number": getattr(claim, "claim_number", None) or "Unknown",
                "policy_number": getattr(claim, "policy_number", None) or "Unknown",
                "line_of_business": getattr(claim, "line_of_business", None) or "Unknown",
                "status": getattr(claim, "status", None) or "Unknown",
                "total_incurred": money(getattr(claim, "total_incurred", 0)),
                "reserve_amount": money(getattr(claim, "reserve_amount", 0)),
                "explanation": (
                    f"Claim {getattr(claim, 'claim_number', None) or 'Unknown'} involved "
                    f"{getattr(claim, 'line_of_business', None) or 'the applicable line of business'} "
                    f"under policy {getattr(claim, 'policy_number', None) or 'Unknown'} "
                    f"with total incurred of ${money(getattr(claim, 'total_incurred', 0)):,.0f}. "
                    f"The claim is currently marked as {getattr(claim, 'status', None) or 'unknown'}."
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
                "policy_number": "N/A",
                "line_of_business": "N/A",
                "status": "N/A",
                "total_incurred": 0,
                "reserve_amount": 0,
                "explanation": "No claim activity was found for the selected account or child policies.",
                "broker_position": "Position the account as having minimal loss activity if loss runs validate as clean.",
            }
        )

    insured_name = (
        profile_data.get("business_name")
        or profile_data.get("insured_name")
        or "Selected Account"
    )

    carrier_name = (
        profile_data.get("carrier_name")
        or profile_data.get("writing_carrier")
        or "Selected Carrier"
    )

    policy_text = ", ".join(policy_numbers_used) if policy_numbers_used else policy_number or "Selected Account"

    underwriter_narrative = (
        f"{insured_name} has {total_claims} account-specific claim(s), {open_claims} open claim(s), "
        f"and {litigation_claims} litigated claim(s) across the selected policy schedule. "
        f"Total incurred losses are ${total_incurred:,.0f}, with ${total_reserve:,.0f} in open reserves. "
        f"LossQ rates the renewal risk as {intelligence.get('renewal_risk_level', 'Not Rated')} "
        f"with a renewal score of {intelligence.get('renewal_score', 'N/A')}/100. "
        f"The account has an estimated renewal probability of "
        f"{decision.get('renewal_probability', 'N/A')}% and carrier appetite is rated "
        f"{appetite.get('carrier_appetite_level', 'N/A')}."
    )

    carrier_submission_email = (
        f"Subject: Renewal Submission - {insured_name}\n\n"
        f"Dear Underwriter,\n\n"
        f"Please find the renewal submission for {insured_name}. "
        f"The account includes the following policy numbers: {policy_text}.\n\n"
        f"The account has been reviewed through LossQ's underwriting intelligence engine. "
        f"The renewal score is {intelligence.get('renewal_score', 'N/A')}/100, "
        f"carrier appetite is rated {appetite.get('carrier_appetite_level', 'N/A')}, "
        f"and submission readiness is rated {readiness.get('submission_readiness_level', 'N/A')}.\n\n"
        f"Loss activity includes {total_claims} account-specific claim(s), {open_claims} open claim(s), "
        f"${total_incurred:,.0f} in total incurred losses, and ${total_reserve:,.0f} "
        f"in reserves.\n\n"
        f"We believe this account should receive underwriting consideration based on the attached "
        f"loss analysis, carrier strategy, and renewal positioning.\n\n"
        f"Thank you,\n"
        f"Broker Team"
    )

    executive_summary = (
        f"{insured_name} has been reviewed for renewal strategy, carrier appetite, submission readiness, "
        f"and premium forecast. LossQ used {total_claims} account-specific claim(s) across "
        f"{len(policy_numbers_used)} policy number(s). LossQ projects an expected renewal premium of "
        f"${forecast.get('expected_renewal_premium', 0):,.0f}, representing an estimated "
        f"{forecast.get('expected_increase_percent', 0)}% change. "
        f"The recommended carrier is {carrier_match.get('recommended_carrier', 'N/A')} with a "
        f"{carrier_match.get('recommended_score', 'N/A')}/100 match score."
    )

    broker_marketing_memo = (
        f"Insured:\n"
        f"{insured_name}\n\n"
        f"Current / Writing Carrier:\n"
        f"{carrier_name}\n\n"
        f"Policy Numbers Used:\n"
        f"{policy_text}\n\n"
        f"Marketing Strategy:\n"
        f"{appetite.get('market_strategy', 'No market strategy available.')}\n\n"
        f"Recommended Carrier:\n"
        f"{carrier_match.get('recommended_carrier', 'N/A')} "
        f"({carrier_match.get('recommended_score', 'N/A')}/100 match score)\n\n"
        f"Submission Readiness:\n"
        f"{readiness.get('submission_readiness_level', 'N/A')} "
        f"({readiness.get('submission_readiness_score', 'N/A')}/100)\n\n"
        f"Premium Forecast:\n"
        f"Expected change: {forecast.get('expected_increase_percent', 'N/A')}%"
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
        "policy_numbers_used": policy_numbers_used,
        "claims_used": total_claims,
        "account_profile": profile_data,
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
    claims, policy_numbers_used, profile_data = get_claims_for_account(db, current_user, policy_number)

    return build_submission_package(
        claims=claims,
        policy_number=policy_number,
        policy_numbers_used=policy_numbers_used,
        profile_data=profile_data,
    )