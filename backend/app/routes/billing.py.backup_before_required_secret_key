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

router = APIRouter(prefix="/billing", tags=["Billing"])
security = HTTPBearer()

SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key-later")
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

FOUNDING_AGENCY_LIMIT = int(os.getenv("FOUNDING_AGENCY_LIMIT", "20"))


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


@router.get("/status")
def billing_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    org = get_org(db, current_user)
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
    ensure_billing_columns(db)

    payload = await request.body()
    signature = request.headers.get("stripe-signature")

    # Verify Stripe signature first, then parse the raw JSON payload into
    # a normal Python dict. This avoids StripeObject/Event parsing crashes
    # such as AttributeError: get or KeyError: 0.
    if STRIPE_WEBHOOK_SECRET:
        try:
            stripe.Webhook.construct_event(payload, signature, STRIPE_WEBHOOK_SECRET)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Webhook signature verification failed: {exc}")

    try:
        event = json.loads(payload.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid webhook payload: {exc}")

    event_type = event.get("type")
    obj = event.get("data", {}).get("object", {}) or {}

    if event_type == "checkout.session.completed":
        metadata = obj.get("metadata", {}) or {}
        org_id = metadata.get("organization_id")
        price_id = metadata.get("price_id")
        subscription_id = obj.get("subscription")
        customer_id = obj.get("customer")

        # Do not call subscription.get() here. Stripe SDK returns StripeObject,
        # which can crash with AttributeError: get on some versions.
        # The checkout session already carries the price_id in metadata because
        # create_checkout_session stores it there. Subscription updated events
        # can later fill current_period_end.
        if org_id and price_id:
            org = db.query(Organization).filter(Organization.id == int(org_id)).first()
            if org:
                apply_plan_to_org(
                    db,
                    org,
                    price_id=price_id,
                    status="active",
                    subscription_id=subscription_id or "",
                    customer_id=customer_id or "",
                    current_period_end=None,
                )

    if event_type in {"customer.subscription.created", "customer.subscription.updated"}:
        subscription_id = obj.get("id")
        customer_id = obj.get("customer")
        status = obj.get("status", "inactive")
        price_id = obj.get("items", {}).get("data", [{}])[0].get("price", {}).get("id")
        org_id = obj.get("metadata", {}).get("organization_id")

        org = None
        if org_id:
            org = db.query(Organization).filter(Organization.id == int(org_id)).first()
        if not org and customer_id:
            org = db.query(Organization).filter(Organization.stripe_customer_id == customer_id).first()

        if org and price_id:
            apply_plan_to_org(
                db,
                org,
                price_id=price_id,
                status=status,
                subscription_id=subscription_id,
                customer_id=customer_id,
                current_period_end=obj.get("current_period_end"),
            )

    if event_type in {"customer.subscription.deleted", "customer.subscription.paused"}:
        subscription_id = obj.get("id")
        customer_id = obj.get("customer")
        org = None

        if subscription_id:
            org = db.query(Organization).filter(Organization.stripe_subscription_id == subscription_id).first()
        if not org and customer_id:
            org = db.query(Organization).filter(Organization.stripe_customer_id == customer_id).first()

        if org:
            org.subscription_status = obj.get("status", "inactive")
            org.plan = "free"
            org.user_limit = 1
            org.upload_limit = 0
            db.commit()

    return {"received": True}
