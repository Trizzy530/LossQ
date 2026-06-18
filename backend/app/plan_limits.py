from fastapi import Depends

from app.auth_utils import get_current_user


# LOSSQ_PROFESSIONAL_ADVANCED_ANALYTICS_INCLUDED_V1
# LOSSQ_PACKAGE_GATE_SAFE_BOOT_RESTORE_V1
# Temporary safe boot version so the backend can start and login can work.
# We will re-enable hard API blocks after confirming the correct database dependency.

PLAN_FUNCTION_LIMITS = {
    "free": {
        "label": "Free / Trial",
        "features": [
            "overview",
            "account_profiles",
            "loss_run_upload",
            "claims_dashboard",
            "exposure_inputs",
        ],
    },
    "starter": {
        "label": "Starter",
        "features": [
            "overview",
            "account_profiles",
            "loss_run_upload",
            "claims_dashboard",
            "exposure_inputs",
            "ai_summary",
            "renewal_memo",
            "pdf_exports",
        ],
    },
    "professional": {
        "label": "Professional",
        "features": [
            "overview",
            "account_profiles",
            "loss_run_upload",
            "claims_dashboard",
            "exposure_inputs",
            "ai_summary",
            "renewal_memo",
            "pdf_exports",
            "renewal_risk",
            "underwriter_decision",
            "carrier_appetite",
            "carrier_match",
            "submission_readiness",
            "premium_forecast",
            "submission_builder",
            "carrier_packet",
            "carrier_email_draft",
            "advanced_analytics",
        ],
    },
    "agency": {
        "label": "Agency",
        "features": [
            "overview",
            "account_profiles",
            "loss_run_upload",
            "claims_dashboard",
            "exposure_inputs",
            "ai_summary",
            "renewal_memo",
            "pdf_exports",
            "renewal_risk",
            "underwriter_decision",
            "carrier_appetite",
            "carrier_match",
            "submission_readiness",
            "premium_forecast",
            "submission_builder",
            "carrier_packet",
            "carrier_email_draft",
            "advanced_analytics",
            "audit_logs",
            "team_management",
            "user_permissions",
        ],
    },
    "founding_agency": {
        "label": "Founding Agency",
        "features": [
            "overview",
            "account_profiles",
            "loss_run_upload",
            "claims_dashboard",
            "exposure_inputs",
            "ai_summary",
            "renewal_memo",
            "pdf_exports",
            "renewal_risk",
            "underwriter_decision",
            "carrier_appetite",
            "carrier_match",
            "submission_readiness",
            "premium_forecast",
            "submission_builder",
            "carrier_packet",
            "carrier_email_draft",
            "advanced_analytics",
            "audit_logs",
            "team_management",
            "user_permissions",
        ],
    },
}


def normalize_plan_name(plan):
    clean = str(plan or "free").strip().lower()

    if clean in {"founder", "founding", "founding agency"}:
        return "founding_agency"
    if clean in {"pro", "professional"}:
        return "professional"
    if clean in {"agency", "enterprise"}:
        return "agency"
    if clean in {"starter", "start"}:
        return "starter"

    return clean if clean in PLAN_FUNCTION_LIMITS else "free"


def get_plan_limits(plan):
    return PLAN_FUNCTION_LIMITS.get(normalize_plan_name(plan), PLAN_FUNCTION_LIMITS["free"])


def enforce_feature(db, current_user, feature):
    return current_user


def require_package_access(current_user=Depends(get_current_user)):
    return current_user
