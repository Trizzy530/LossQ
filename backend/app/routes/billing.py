import os
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import stripe
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.organization import Organization
from app.models.user import User

load_dotenv()

from app.services.audit import record_audit_event

router = APIRouter(prefix="/billing", tags=["Billing"])
security = HTTPBearer()

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable is required")
ALGORITHM = "HS256"
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://lossq.com").rstrip("/")

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

stripe.api_key = STRIPE_SECRET_KEY

PRICE_TO_PLAN = {
    os.getenv("STRIPE_STARTER_PRICE_ID", ""): {
        "plan": "starter",
        "label": "Starter",
        "user_limit": 1,
        "upload_limit": 50,
    },
    os.getenv("STRIPE_PRO_PRICE_ID", ""): {
        "plan": "professional",
        "label": "Professional",
        "user_limit": 5,
        "upload_limit": -1,
    },
    os.getenv("STRIPE_AGENCY_PRICE_ID", ""): {
        "plan": "agency",
        "label": "Agency",
        "user_limit": 25,
        "upload_limit": -1,
    },
    os.getenv("STRIPE_FOUNDING_PRICE_ID", ""): {
        "plan": "founding_agency",
        "label": "Founding Agency",
        "user_limit": 5,
        "upload_limit": -1,
    },
}

PLAN_TO_PRICE = {
    plan_data["plan"]: price_id
    for price_id, plan_data in PRICE_TO_PLAN.items()
    if price_id
}

FOUNDING_AGENCY_LIMIT = min(int(os.getenv("FOUNDING_AGENCY_LIMIT", "5")), 5)


class CheckoutRequest(BaseModel):
    plan: str


class PortalRequest(BaseModel):
    return_url: Optional[str] = None


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_billing_columns(db: Session):
    """Keep deployed DB compatible without a full migration tool."""
    dialect = db.bind.dialect.name

    columns = {
        "plan": "VARCHAR(50) DEFAULT 'free'",
        "subscription_status": "VARCHAR(50) DEFAULT 'inactive'",
        "stripe_customer_id": "VARCHAR(255)",
        "stripe_subscription_id": "VARCHAR(255)",
        "stripe_price_id": "VARCHAR(255)",
        "current_period_end": "TIMESTAMP",
        "upload_limit": "INTEGER DEFAULT 0",
    }

    if dialect == "postgresql":
        existing = {
            row[0]
            for row in db.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'organizations'
                    """
                )
            ).fetchall()
        }

        for column, definition in columns.items():
            if column not in existing:
                db.execute(text(f"ALTER TABLE organizations ADD COLUMN {column} {definition}"))
        db.commit()
        return

    # SQLite fallback for local dev
    existing = {row[1] for row in db.execute(text("PRAGMA table_info(organizations)"))}
    for column, definition in columns.items():
        if column not in existing:
            db.execute(text(f"ALTER TABLE organizations ADD COLUMN {column} {definition}"))
    db.commit()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        email = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    query = db.query(User)
    user = query.filter(User.id == user_id).first() if user_id else None
    if not user and email:
        user = query.filter(User.email == email).first()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


def require_owner_or_admin(user: User):
    if (user.role or "user").lower() not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Owner or admin access required")


def get_org(db: Session, user: User) -> Organization:
    ensure_billing_columns(db)
    org = db.query(Organization).filter(Organization.id == user.organization_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


def plan_from_price(price_id: str) -> Dict[str, Any]:
    plan_data = PRICE_TO_PLAN.get(price_id)
    if not plan_data:
        raise HTTPException(status_code=400, detail="Unknown Stripe price ID")
    return plan_data


def to_datetime_from_unix(value: Any):
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except Exception:
        return None




# LOSSQ_PLAN_FUNCTION_LIMITS_V1
PLAN_FUNCTION_LIMITS = {
    # LOSSQ_BETA_ACCESS_PLAN_V1
    "beta": {
        "label": "Beta Access",
        "user_limit": 1,
        "upload_limit": 10,
        "features": [
            "overview",
            "account_profiles",
            "loss_run_upload",
            "claims_analysis",
            "renewal_score",
            "renewal_memo",
            "reports",
            "copilot",
            "carrier_packet",
            "submission_builder",
            "carrier_email_draft",
            "charts",
        ],
    },
    "free": {
        "label": "Free / Trial",
        "user_limit": 1,
        "upload_limit": 5,
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
        "user_limit": 1,
        "upload_limit": 50,
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
        "user_limit": 5,
        "upload_limit": -1,
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
        ],
    },
    "agency": {
        "label": "Agency",
        "user_limit": 25,
        "upload_limit": -1,
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
        "user_limit": 5,
        "upload_limit": -1,
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
    if clean in {"beta", "beta_access", "early_access"}:
        return "beta"
    return clean if clean in PLAN_FUNCTION_LIMITS else "free"


def get_plan_limits(plan):
    normalized = normalize_plan_name(plan)
    return PLAN_FUNCTION_LIMITS.get(normalized, PLAN_FUNCTION_LIMITS["free"])




# LOSSQ_STRIPE_BILLING_AUTOMATION_HELPERS_V1
def normalize_billing_plan(plan: Any) -> str:
    clean = str(plan or "").strip().lower().replace("-", "_").replace(" ", "_")

    if clean in {"pro"}:
        return "professional"
    if clean in {"enterprise"}:
        return "agency"
    if clean in {"founder", "founding", "founding_agency"}:
        return "founding_agency"

    if clean in {"starter", "professional", "agency", "founding_agency"}:
        return clean

    return "professional"


def stripe_price_env_keys_for_plan(plan: str):
    normalized = normalize_billing_plan(plan)

    if normalized == "starter":
        return [
            "STRIPE_STARTER_PRICE_ID",
            "STRIPE_PRICE_STARTER",
            "STRIPE_STARTER_PRICE",
            "STARTER_PRICE_ID",
            "LOSSQ_STRIPE_STARTER_PRICE_ID",
        ]

    if normalized == "professional":
        return [
            "STRIPE_PRO_PRICE_ID",
            "STRIPE_PROFESSIONAL_PRICE_ID",
            "STRIPE_PRICE_PROFESSIONAL",
            "STRIPE_PROFESSIONAL_PRICE",
            "PROFESSIONAL_PRICE_ID",
            "LOSSQ_STRIPE_PROFESSIONAL_PRICE_ID",
        ]

    if normalized == "agency":
        return [
            "STRIPE_AGENCY_PRICE_ID",
            "STRIPE_PRICE_AGENCY",
            "STRIPE_AGENCY_PRICE",
            "AGENCY_PRICE_ID",
            "LOSSQ_STRIPE_AGENCY_PRICE_ID",
        ]

    if normalized == "founding_agency":
        return [
            "STRIPE_FOUNDING_PRICE_ID",
            "STRIPE_FOUNDING_AGENCY_PRICE_ID",
            "STRIPE_PRICE_FOUNDING_AGENCY",
            "STRIPE_FOUNDING_PRICE",
            "FOUNDING_AGENCY_PRICE_ID",
            "LOSSQ_STRIPE_FOUNDING_AGENCY_PRICE_ID",
        ]

    return []


def get_stripe_price_id_for_plan(plan: str) -> str:
    normalized = normalize_billing_plan(plan)

    existing = PLAN_TO_PRICE.get(normalized)
    if existing:
        return existing

    for key in stripe_price_env_keys_for_plan(normalized):
        value = os.getenv(key, "").strip()
        if value:
            return value

    return ""


def plan_data_from_plan(plan: str) -> Dict[str, Any]:
    normalized = normalize_billing_plan(plan)
    limits = PLAN_FUNCTION_LIMITS.get(normalized, PLAN_FUNCTION_LIMITS["professional"])

    return {
        "plan": normalized,
        "label": limits.get("label", normalized.title()),
        "user_limit": limits.get("user_limit", 5),
        "upload_limit": limits.get("upload_limit", -1),
    }


def plan_data_from_price_or_plan(price_id: str = "", plan: str = "") -> Dict[str, Any]:
    if price_id and price_id in PRICE_TO_PLAN:
        return PRICE_TO_PLAN[price_id]

    normalized = normalize_billing_plan(plan)
    expected_price = get_stripe_price_id_for_plan(normalized)

    if price_id and expected_price and price_id == expected_price:
        return plan_data_from_plan(normalized)

    if normalized:
        return plan_data_from_plan(normalized)

    raise HTTPException(status_code=400, detail="Unable to determine billing plan from Stripe event.")


def extract_price_id_from_subscription_object(obj: Dict[str, Any]) -> str:
    try:
        return (
            obj.get("items", {})
            .get("data", [{}])[0]
            .get("price", {})
            .get("id", "")
        ) or ""
    except Exception:
        return ""


def find_org_for_stripe_payload(db: Session, obj: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None):
    metadata = metadata or {}
    org = None

    org_id = metadata.get("organization_id") or obj.get("metadata", {}).get("organization_id")

    if org_id:
        try:
            org = db.query(Organization).filter(Organization.id == int(org_id)).first()
        except Exception:
            org = None

    subscription_id = obj.get("subscription") or obj.get("id")
    customer_id = obj.get("customer")

    if not org and subscription_id:
        try:
            org = db.query(Organization).filter(Organization.stripe_subscription_id == subscription_id).first()
        except Exception:
            org = None

    if not org and customer_id:
        try:
            org = db.query(Organization).filter(Organization.stripe_customer_id == customer_id).first()
        except Exception:
            org = None

    return org


def apply_stripe_plan_to_org(
    db: Session,
    org: Organization,
    price_id: str = "",
    plan: str = "",
    status: str = "active",
    subscription_id: str = "",
    customer_id: str = "",
    current_period_end: Any = None,
):
    plan_data = plan_data_from_price_or_plan(price_id=price_id, plan=plan)

    org.plan = plan_data["plan"]
    org.subscription_status = status or "active"

    if price_id:
        org.stripe_price_id = price_id
    if subscription_id:
        org.stripe_subscription_id = subscription_id
    if customer_id:
        org.stripe_customer_id = customer_id

    org.user_limit = plan_data.get("user_limit", 5)
    org.upload_limit = plan_data.get("upload_limit", -1)

    converted_period_end = to_datetime_from_unix(current_period_end)
    if converted_period_end:
        org.current_period_end = converted_period_end

    db.commit()
    db.refresh(org)
    return org


def downgrade_org_for_subscription_end(db: Session, org: Organization, status: str = "cancelled"):
    org.plan = "free"
    org.subscription_status = status or "cancelled"
    org.user_limit = 1
    org.upload_limit = 0
    db.commit()
    db.refresh(org)
    return org


def serialize_org_billing(org: Organization):
    return {
        "organization_id": org.id,
        "organization_name": org.name,
        "plan": getattr(org, "plan", "free") or "free",
        "subscription_status": getattr(org, "subscription_status", "inactive") or "inactive",
        "stripe_customer_id": getattr(org, "stripe_customer_id", None),
        "stripe_subscription_id": getattr(org, "stripe_subscription_id", None),
        "stripe_price_id": getattr(org, "stripe_price_id", None),
        "current_period_end": getattr(org, "current_period_end", None).isoformat()
        if getattr(org, "current_period_end", None)
        else None,
        "user_limit": getattr(org, "user_limit", 5) or 5,
        "upload_limit": getattr(org, "upload_limit", 0),
        "plan_limits": get_plan_limits(getattr(org, "plan", "free")),
        "features": get_plan_limits(getattr(org, "plan", "free")).get("features", []),
    }


def apply_plan_to_org(db: Session, org: Organization, price_id: str, status: str, subscription_id: str = "", customer_id: str = "", current_period_end: Any = None):
    plan_data = plan_from_price(price_id)

    org.plan = plan_data["plan"]
    org.subscription_status = status or "inactive"
    org.stripe_price_id = price_id
    org.user_limit = plan_data["user_limit"]
    org.upload_limit = plan_data["upload_limit"]

    if subscription_id:
        org.stripe_subscription_id = subscription_id
    if customer_id:
        org.stripe_customer_id = customer_id

    converted_period_end = to_datetime_from_unix(current_period_end)
    if converted_period_end:
        org.current_period_end = converted_period_end

    db.commit()
    db.refresh(org)
    return org


def founding_slots_remaining(db: Session):
    ensure_billing_columns(db)
    count = (
        db.query(Organization)
        .filter(Organization.plan == "founding_agency")
        .filter(Organization.subscription_status.in_(["active", "trialing"] ))
        .count()
    )
    return max(FOUNDING_AGENCY_LIMIT - count, 0)




# LOSSQ_FOUNDING_AGENCY_AUTO_HIDE_V1
def founding_agency_used_count(db):
    try:
        if "ensure_billing_columns" in globals():
            ensure_billing_columns(db)
    except Exception:
        pass

    active_statuses = ["active", "trialing", "paid"]

    query = db.query(Organization).filter(Organization.plan == "founding_agency")

    try:
        status_col = getattr(Organization, "subscription_status", None)
        if status_col is not None:
            query = query.filter(status_col.in_(active_statuses))
    except Exception:
        pass

    return query.count()


def founding_agency_status_payload(db):
    used = founding_agency_used_count(db)
    limit = FOUNDING_AGENCY_LIMIT
    remaining = max(limit - used, 0)

    return {
        "plan": "founding_agency",
        "label": "Founding Agency",
        "limit": limit,
        "used": used,
        "remaining": remaining,
        "available": remaining > 0,
        "sold_out": remaining <= 0,
    }


@router.get("/public/founding-agency-status")
def public_founding_agency_status(db = Depends(get_db)):
    return founding_agency_status_payload(db)


@router.get("/status")
def billing_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    org = get_org(db, current_user)

    # LOSSQ_BETA_ACCESS_EXPIRATION_V1
    if str(getattr(org, "plan", "") or "").lower() == "beta":
        beta_end = getattr(org, "current_period_end", None)
        if beta_end:
            now = datetime.now(timezone.utc)
            if getattr(beta_end, "tzinfo", None) is None:
                beta_end = beta_end.replace(tzinfo=timezone.utc)
            if beta_end < now:
                org.plan = "free"
                org.subscription_status = "beta_expired"
                org.upload_limit = 0
                if hasattr(org, "user_limit"):
                    org.user_limit = 1
                db.commit()
                db.refresh(org)

    return {
        **serialize_org_billing(org),
        "founding_slots_remaining": founding_slots_remaining(db),
        "is_billing_admin": (current_user.role or "user").lower() in {"owner", "admin"},
    }


@router.post("/create-checkout-session")
def create_checkout_session(
    data: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_owner_or_admin(current_user)

    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe is not configured")

    plan = data.plan.strip().lower()
    price_id = PLAN_TO_PRICE.get(plan)

    if not price_id:
        raise HTTPException(status_code=400, detail="Unknown billing plan")

    if plan == "founding_agency" and founding_slots_remaining(db) <= 0:
        raise HTTPException(status_code=400, detail="Founding Agency plan is no longer available")

    org = get_org(db, current_user)

    customer_id = getattr(org, "stripe_customer_id", None)
    if not customer_id:
        customer = stripe.Customer.create(
            email=current_user.email,
            name=org.name,
            metadata={
                "organization_id": str(org.id),
                "organization_name": org.name,
                "created_by_user_id": str(current_user.id),
            },
        )
        customer_id = customer.id
        org.stripe_customer_id = customer_id
        db.commit()

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{FRONTEND_URL}/settings?billing=success&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{FRONTEND_URL}/pricing?billing=cancelled",
        allow_promotion_codes=True,
        subscription_data={
            "metadata": {
                "organization_id": str(org.id),
                "plan": plan,
                "price_id": price_id,
            }
        },
        metadata={
            "organization_id": str(org.id),
            "plan": plan,
            "price_id": price_id,
        },
    )

    record_audit_event(
        db,
        current_user=current_user,
        action="billing_checkout_started",
        resource_type="billing",
        resource_id=str(session.id),
        details={
            "event": "billing_checkout_started",
            "session_id": session.id,
            "checkout_url_created": bool(session.url),
            "price_id": price_id if "price_id" in locals() else "",
            "plan": getattr(data, "plan", "") or getattr(data, "plan_key", "") or getattr(data, "price_id", ""),
        },
    )

    return {"checkout_url": session.url, "session_id": session.id}


@router.post("/create-portal-session")
def create_portal_session(
    data: PortalRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_owner_or_admin(current_user)

    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe is not configured")

    org = get_org(db, current_user)
    customer_id = getattr(org, "stripe_customer_id", None)

    if not customer_id:
        raise HTTPException(status_code=400, detail="No Stripe customer found for this organization")

    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=data.return_url or f"{FRONTEND_URL}/settings",
    )

    return {"portal_url": session.url}


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    # LOSSQ_STRIPE_WEBHOOK_AUTOMATION_V2
    ensure_billing_columns(db)

    payload = await request.body()
    signature = request.headers.get("stripe-signature")

    if STRIPE_WEBHOOK_SECRET:
        try:
            stripe.Webhook.construct_event(payload, signature, STRIPE_WEBHOOK_SECRET)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Webhook signature verification failed: {exc}")

    try:
        event = json.loads(payload.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid webhook payload: {exc}")

    event_type = event.get("type", "")
    obj = event.get("data", {}).get("object", {}) or {}

    org = None
    subscription_id = ""
    customer_id = ""
    price_id = ""
    plan = ""
    status = ""

    try:
        if event_type == "checkout.session.completed":
            metadata = obj.get("metadata", {}) or {}

            org = find_org_for_stripe_payload(db, obj, metadata)
            subscription_id = obj.get("subscription") or ""
            customer_id = obj.get("customer") or ""
            price_id = metadata.get("price_id") or ""
            plan = metadata.get("plan") or ""
            status = "active"

            # If checkout metadata is missing price_id, retrieve subscription from Stripe.
            if subscription_id and not price_id and STRIPE_SECRET_KEY:
                try:
                    subscription = stripe.Subscription.retrieve(subscription_id)
                    subscription_dict = dict(subscription)
                    price_id = extract_price_id_from_subscription_object(subscription_dict)
                    plan = plan or subscription_dict.get("metadata", {}).get("plan", "")
                except Exception:
                    pass

            if org:
                org = apply_stripe_plan_to_org(
                    db,
                    org,
                    price_id=price_id,
                    plan=plan,
                    status=status,
                    subscription_id=subscription_id,
                    customer_id=customer_id,
                    current_period_end=None,
                )

        elif event_type in {"customer.subscription.created", "customer.subscription.updated"}:
            metadata = obj.get("metadata", {}) or {}

            org = find_org_for_stripe_payload(db, obj, metadata)
            subscription_id = obj.get("id") or ""
            customer_id = obj.get("customer") or ""
            price_id = extract_price_id_from_subscription_object(obj)
            plan = metadata.get("plan") or ""
            status = obj.get("status") or "inactive"

            if org and price_id:
                org = apply_stripe_plan_to_org(
                    db,
                    org,
                    price_id=price_id,
                    plan=plan,
                    status=status,
                    subscription_id=subscription_id,
                    customer_id=customer_id,
                    current_period_end=obj.get("current_period_end"),
                )

        elif event_type in {"customer.subscription.deleted", "customer.subscription.paused"}:
            metadata = obj.get("metadata", {}) or {}

            org = find_org_for_stripe_payload(db, obj, metadata)
            subscription_id = obj.get("id") or ""
            customer_id = obj.get("customer") or ""
            status = obj.get("status") or "cancelled"

            if org:
                org = downgrade_org_for_subscription_end(db, org, status=status)

        elif event_type == "invoice.payment_succeeded":
            subscription_id = obj.get("subscription") or ""
            customer_id = obj.get("customer") or ""

            org = find_org_for_stripe_payload(
                db,
                {
                    "subscription": subscription_id,
                    "customer": customer_id,
                },
                {},
            )

            if org:
                org.subscription_status = "active"
                db.commit()
                db.refresh(org)

        elif event_type == "invoice.payment_failed":
            subscription_id = obj.get("subscription") or ""
            customer_id = obj.get("customer") or ""

            org = find_org_for_stripe_payload(
                db,
                {
                    "subscription": subscription_id,
                    "customer": customer_id,
                },
                {},
            )

            if org:
                org.subscription_status = "past_due"
                db.commit()
                db.refresh(org)

        record_audit_event(
            db,
            current_user={"organization_id": getattr(org, "id", None)} if org else {},
            action="billing_webhook_received",
            resource_type="billing",
            resource_id=str(event_type or ""),
            details={
                "event": "billing_webhook_received",
                "stripe_event_type": event_type,
                "stripe_event_id": event.get("id") if isinstance(event, dict) else "",
                "subscription_id": subscription_id,
                "customer_id": customer_id,
                "price_id": price_id,
                "plan": plan,
                "status": status,
                "organization_id": getattr(org, "id", None) if org else None,
            },
            request=request,
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Billing webhook processing failed: {exc}")

    return {"received": True}


# LOSSQ_BILLING_CANCEL_SUBSCRIPTION_ENDPOINT_V1
@router.post("/cancel-subscription")
def cancel_subscription(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """
    End/cancel the current organization's subscription.

    Safety rule:
    - This does not delete users, organizations, account profiles, claims, uploads, or reports.
    - If Stripe is configured and a subscription id exists, request cancellation at period end.
    - If no Stripe subscription id exists, downgrade local access to free/cancelled.
    """
    org = get_org(db, current_user)

    subscription_id = getattr(org, "stripe_subscription_id", None)
    stripe_cancel_requested = False

    if subscription_id and STRIPE_SECRET_KEY:
        try:
            stripe.Subscription.modify(subscription_id, cancel_at_period_end=True)
            stripe_cancel_requested = True
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Stripe cancellation request failed: {str(exc)}",
            )

    if stripe_cancel_requested:
        org.subscription_status = "canceling"
    else:
        org.plan = "free"
        org.subscription_status = "cancelled"

    db.commit()
    db.refresh(org)

    return {
        "ok": True,
        "message": (
            "Subscription cancellation requested. Access will remain until Stripe ends the current billing period."
            if stripe_cancel_requested
            else "Subscription ended locally. Account data was not deleted."
        ),
        "plan": getattr(org, "plan", "free"),
        "subscription_status": getattr(org, "subscription_status", "cancelled"),
        "cancel_at_period_end": stripe_cancel_requested,
    }

# LOSSQ_BILLING_CHECKOUT_COMPAT_ENDPOINT_V1
@router.post("/checkout")
def create_checkout_compat(payload: dict, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    # LOSSQ_BILLING_CHECKOUT_COMPAT_ENDPOINT_V2
    require_owner_or_admin(current_user)

    if not STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=400,
            detail="Stripe billing is not configured yet. Add STRIPE_SECRET_KEY in Railway.",
        )

    org = get_org(db, current_user)

    requested_plan = normalize_billing_plan(
        payload.get("plan")
        or payload.get("package")
        or payload.get("subscription_plan")
        or "professional"
    )

    if requested_plan == "founding_agency" and founding_slots_remaining(db) <= 0:
        raise HTTPException(status_code=400, detail="Founding Agency plan is no longer available")

    price_id = get_stripe_price_id_for_plan(requested_plan)

    if not price_id:
        raise HTTPException(
            status_code=400,
            detail=f"Stripe price ID is not configured for the {requested_plan} plan.",
        )

    success_url = (
        payload.get("success_url")
        or os.getenv("LOSSQ_BILLING_SUCCESS_URL")
        or f"{FRONTEND_URL}/dashboard?billing=success"
    )

    cancel_url = (
        payload.get("cancel_url")
        or os.getenv("LOSSQ_BILLING_CANCEL_URL")
        or f"{FRONTEND_URL}/settings/billing?billing=cancelled"
    )

    try:
        customer_id = getattr(org, "stripe_customer_id", None)

        if not customer_id:
            customer = stripe.Customer.create(
                email=current_user.email,
                name=org.name,
                metadata={
                    "organization_id": str(org.id),
                    "organization_name": org.name or "",
                    "created_by_user_id": str(current_user.id),
                },
            )
            customer_id = customer.id
            org.stripe_customer_id = customer_id
            db.commit()

        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            allow_promotion_codes=True,
            metadata={
                "organization_id": str(org.id),
                "plan": requested_plan,
                "price_id": price_id,
            },
            subscription_data={
                "metadata": {
                    "organization_id": str(org.id),
                    "plan": requested_plan,
                    "price_id": price_id,
                }
            },
        )

        record_audit_event(
            db,
            current_user=current_user,
            action="billing_checkout_started",
            resource_type="billing",
            resource_id=str(session.id),
            details={
                "event": "billing_checkout_started",
                "session_id": session.id,
                "checkout_url_created": bool(session.url),
                "price_id": price_id,
                "plan": requested_plan,
            },
        )

        return {
            "ok": True,
            "plan": requested_plan,
            "url": session.url,
            "checkout_url": session.url,
            "session_id": session.id,
        }

    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Stripe checkout failed: {str(exc)}")
