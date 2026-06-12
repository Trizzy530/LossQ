from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.auth_utils import get_current_user
from app.plan_limits import require_package_access
from app.routes.summary import build_underwriting_intelligence, get_claims_for_account, data_quality
from app.routes.renewal import build_underwriter_decision_engine, build_carrier_appetite_engine, build_carrier_match_engine, build_premium_forecast_engine, money, is_open, is_litigated

router = APIRouter(prefix="/submission-builder", tags=["Submission Builder"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/")
def submission_builder(policy_number: str | None = Query(default=None), db: Session = Depends(get_db), current_user: dict = Depends(require_package_access)):
    claims, policy_numbers_used, profile_data = get_claims_for_account(db, current_user, policy_number)
    quality = data_quality(claims, policy_numbers_used, profile_data)
    if not quality["is_credible"]:
        return {
            "policy_number": policy_number,
            "claims_used": len(claims),
            "policy_numbers_used": policy_numbers_used,
            "account_profile": profile_data,
            "is_credible": False,
            "data_quality": quality,
            "underwriter_narrative": "INSUFFICIENT DATA: Do not send to underwriters until claims and policy schedule are validated.",
            "carrier_submission_email": "Submission blocked by LossQ data-quality guardrail. Validate loss run extraction first.",
            "executive_summary": "Insufficient validated loss data. Submission package not generated.",
            "loss_explanations": [],
            "broker_marketing_memo": "Not ready for market.",
            "renewal_strategy": "Correct parser/upload data first, then regenerate the submission package.",
            "supporting_intelligence": {},
        }

    intelligence = build_underwriting_intelligence(claims)
    decision = build_underwriter_decision_engine(claims, policy_number)
    appetite = build_carrier_appetite_engine(claims, policy_number)
    carrier_match = build_carrier_match_engine(claims, policy_number)
    forecast = build_premium_forecast_engine(claims, policy_number)
    total_claims = len(claims)
    open_claims = len([c for c in claims if is_open(c)])
    litigation_claims = len([c for c in claims if is_litigated(c)])
    total_incurred = sum(money(getattr(c, "total_incurred", 0)) for c in claims)
    total_reserve = sum(money(getattr(c, "reserve_amount", 0)) for c in claims)
    insured = profile_data.get("business_name") or "Selected Account"
    policy_text = ", ".join(policy_numbers_used)
    return {
        "policy_number": policy_number,
        "policy_numbers_used": policy_numbers_used,
        "claims_used": total_claims,
        "account_profile": profile_data,
        "is_credible": True,
        "data_quality": quality,
        "underwriter_narrative": f"{insured} has {total_claims} account-specific claims across {policy_text}. Open claims: {open_claims}. Litigation claims: {litigation_claims}. Total incurred: ${total_incurred:,.0f}. Reserves: ${total_reserve:,.0f}.",
        "carrier_submission_email": f"Subject: Renewal Submission - {insured}\n\nValidated LossQ review attached. Policies used: {policy_text}. Claims used: {total_claims}. Renewal risk: {intelligence.get('renewal_risk_level')}.",
        "executive_summary": f"LossQ reviewed {total_claims} validated account-specific claims and projects a {forecast.get('expected_increase_percent')}% modeled renewal premium change.",
        "loss_explanations": [],
        "broker_marketing_memo": appetite.get("market_strategy"),
        "renewal_strategy": decision.get("submission_readiness"),
        "supporting_intelligence": {"summary": intelligence, "decision": decision, "carrier_appetite": appetite, "carrier_match": carrier_match, "premium_forecast": forecast},
    }
