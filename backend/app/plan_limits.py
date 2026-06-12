from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth_utils import get_current_user
from app.database import get_db
from app.models import Organization


# LOSSQ_BACKEND_API_PACKAGE_GATES_V1

PLAN_FUNCTION_LIMITS = {
    "free": {
        "label": "Free / Trial",
        "user_limit": 1,
        "upload_limit": 5,
        "features": {
            "overview",
            "account_profiles",
            "loss_run_upload",
            "claims_dashboard",
            "exposure_inputs",
        },
    },
    "starter": {
        "label": "Starter",
        "user_limit": 1,
        "upload_limit": 50,
        "features": {
            "overview",
            "account_profiles",
            "loss_run_upload",
            "claims_dashboard",
            "exposure_inputs",
            "ai_summary",
            "renewal_memo",
            "pdf_exports",
        },
    },
    "professional": {
        "label": "Professional",
        "user_limit": 5,
        "upload_limit": -1,
        "features": {
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
        },
    },
    "agency": {
        "label": "Agency",
        "user_limit": 25,
        "upload_limit": -1,
        "features": {
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
        },
    },
    "founding_agency": {
        "label": "Founding Agency",
        "user_limit": 5,
        "upload_limit": -1,
        "features": {
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
        },
    },
}

PATH_FEATURE_MAP = [
    ("/upload", "loss_run_upload"),
    ("/upload-v2", "loss_run_upload"),
    ("/summary/underwriting", "ai_summary"),
    ("/renewal/memo", "renewal_memo"),
    ("/renewal/summary", "renewal_risk"),
    ("/renewal/risk", "renewal_risk"),
    ("/renewal/decision", "underwriter_decision"),
    ("/renewal/carrier-appetite", "carrier_appetite"),
    ("/renewal/carrier-match", "carrier_match"),
    ("/renewal/submission-readiness", "submission_readiness"),
    ("/renewal/premium-forecast", "premium_forecast"),
    ("/premium-forecast", "premium_forecast"),
    ("/submission-builder", "submission_builder"),
    ("/reports/executive-report-pdf", "pdf_exports"),
    ("/reports/carrier-packet-pdf", "carrier_packet"),
    ("/carrier-packet", "carrier_packet"),
    ("/audit-logs", "audit_logs"),
    ("/admin/users", "team_management"),
]


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
    normalized = normalize_plan_name(plan)
    return PLAN_FUNCTION_LIMITS.get(normalized, PLAN_FUNCTION_LIMITS["free"])


def get_current_user_org_id(current_user):
    if isinstance(current_user, dict):
        return current_user.get("organization_id") or current_user.get("org_id")
    return getattr(current_user, "organization_id", None)


def get_current_user_role(current_user):
    if isinstance(current_user, dict):
        return str(current_user.get("role") or "user").lower()
    return str(getattr(current_user, "role", "user") or "user").lower()


def get_org_for_current_user(db: Session, current_user):
    org_id = get_current_user_org_id(current_user)

    if not org_id:
        raise HTTPException(status_code=403, detail="Organization is required for this feature.")

    org = db.query(Organization).filter(Organization.id == org_id).first()

    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")

    return org


def feature_for_path(path: str):
    clean_path = str(path or "")

    for prefix, feature in PATH_FEATURE_MAP:
        if clean_path.startswith(prefix):
            return feature

    return None


def enforce_feature(db: Session, current_user, feature: str):
    if not feature:
        return current_user

    org = get_org_for_current_user(db, current_user)
    plan = normalize_plan_name(getattr(org, "plan", "free"))
    limits = get_plan_limits(plan)
    features = limits.get("features", set())

    if feature not in features:
        label = limits.get("label", plan)
        raise HTTPException(
            status_code=403,
            detail=f"This function is not included in the current {label} package. Upgrade the account package to unlock it.",
        )

    return current_user


def require_feature(feature: str):
    def dependency(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        return enforce_feature(db, current_user, feature)

    return dependency


def require_package_access(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    feature = feature_for_path(request.url.path)
    return enforce_feature(db, current_user, feature)
