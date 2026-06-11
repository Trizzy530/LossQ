
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import inspect, text
import os

from app.database import SessionLocal
from app.auth_utils import get_current_user

router = APIRouter(prefix="/platform-admin", tags=["Platform Admin"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_platform_admin(current_user: dict):
    allowed_emails = [
        item.strip().lower()
        for item in os.getenv("PLATFORM_ADMIN_EMAILS", "").split(",")
        if item.strip()
    ]

    user_email = str(
        current_user.get("email")
        or current_user.get("user_email")
        or current_user.get("sub")
        or ""
    ).strip().lower()

    user_role = str(current_user.get("role") or "").strip().lower()

    if user_email in allowed_emails or user_role in {"platform_admin", "super_admin", "owner"}:
        return True

    raise HTTPException(status_code=403, detail="Platform admin access required.")


def table_exists(db: Session, table_name: str):
    try:
        inspector = inspect(db.bind)
        return table_name in inspector.get_table_names()
    except Exception:
        return False


def get_columns(db: Session, table_name: str):
    try:
        inspector = inspect(db.bind)
        return [column["name"] for column in inspector.get_columns(table_name)]
    except Exception:
        return []


def safe_select_columns(existing_columns, desired_columns):
    return [column for column in desired_columns if column in existing_columns]


def row_to_dict(row):
    try:
        return dict(row._mapping)
    except Exception:
        return dict(row)


@router.get("/stats")
def platform_stats(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)

    stats = {
        "total_users": 0,
        "total_organizations": 0,
        "total_claims": 0,
        "total_profiles": 0,
        "total_uploads": 0,
    }

    table_map = {
        "users": "total_users",
        "organizations": "total_organizations",
        "claims": "total_claims",
        "account_profiles": "total_profiles",
        "upload_history": "total_uploads",
    }

    for table_name, stat_key in table_map.items():
        if table_exists(db, table_name):
            try:
                result = db.execute(text(f"SELECT COUNT(*) AS count FROM {table_name}")).first()
                stats[stat_key] = int(result._mapping["count"] or 0)
            except Exception:
                stats[stat_key] = 0

    return stats


@router.get("/users")
def platform_users(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)

    if not table_exists(db, "users"):
        return {"users": [], "message": "No users table found."}

    user_columns = get_columns(db, "users")

    desired_user_columns = [
        "id",
        "email",
        "full_name",
        "name",
        "first_name",
        "last_name",
        "role",
        "organization_id",
        "company_name",
        "phone",
        "phone_number",
        "mobile_phone",
        "office_phone",
        "support_phone",
        "billing_phone",
        "is_active",
        "status",
        "account_status",
        "subscription_status",
        "plan",
        "stripe_customer_id",
        "stripe_subscription_id",
        "created_at",
        "updated_at",
        "last_login",
        "last_login_at",
    ]

    selected_user_columns = safe_select_columns(user_columns, desired_user_columns)

    if not selected_user_columns:
        selected_user_columns = user_columns[:20]

    query = f"""
        SELECT {", ".join(selected_user_columns)}
        FROM users
        ORDER BY
            CASE WHEN created_at IS NOT NULL THEN created_at END DESC
    """

    try:
        rows = db.execute(text(query)).fetchall()
    except Exception:
        query = f"SELECT {', '.join(selected_user_columns)} FROM users"
        rows = db.execute(text(query)).fetchall()

    users = [row_to_dict(row) for row in rows]

    # Attach organization info if table exists.
    if table_exists(db, "organizations"):
        org_columns = get_columns(db, "organizations")
        org_select = safe_select_columns(
            org_columns,
            ["id", "name", "company_name", "organization_name", "plan", "subscription_status", "created_at"],
        )

        if org_select and "id" in org_columns:
            try:
                org_rows = db.execute(
                    text(f"SELECT {', '.join(org_select)} FROM organizations")
                ).fetchall()
                orgs = {row_to_dict(row).get("id"): row_to_dict(row) for row in org_rows}

                for user in users:
                    org_id = user.get("organization_id")
                    user["organization"] = orgs.get(org_id)
            except Exception:
                pass

    return {"users": users, "count": len(users)}


@router.get("/organizations")
def platform_organizations(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)

    if not table_exists(db, "organizations"):
        return {"organizations": [], "message": "No organizations table found."}

    org_columns = get_columns(db, "organizations")

    desired_columns = [
        "id",
        "name",
        "company_name",
        "organization_name",
        "phone",
        "phone_number",
        "office_phone",
        "support_phone",
        "billing_phone",
        "owner_user_id",
        "plan",
        "subscription_status",
        "stripe_customer_id",
        "stripe_subscription_id",
        "created_at",
        "updated_at",
    ]

    selected_columns = safe_select_columns(org_columns, desired_columns)

    if not selected_columns:
        selected_columns = org_columns[:20]

    try:
        rows = db.execute(
            text(f"SELECT {', '.join(selected_columns)} FROM organizations ORDER BY id DESC")
        ).fetchall()
    except Exception:
        rows = db.execute(
            text(f"SELECT {', '.join(selected_columns)} FROM organizations")
        ).fetchall()

    organizations = [row_to_dict(row) for row in rows]

    return {"organizations": organizations, "count": len(organizations)}

@router.get("/support-lookup")
def platform_support_lookup(
    q: str = "",
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # LOSSQ_SUPPORT_LOOKUP_V1
    require_platform_admin(current_user)

    import re

    query_value = str(q or "").strip().lower()
    phone_digits = re.sub(r"\D", "", query_value)

    if not query_value:
        return {
            "query": q,
            "users": [],
            "organizations": [],
            "message": "Enter a phone number, email, company name, contact name, or organization ID.",
        }

    def normalize_phone(value):
        return re.sub(r"\D", "", str(value or ""))

    def matches(record):
        record_text = " ".join(str(value or "") for value in record.values()).lower()
        record_digits = normalize_phone(record_text)

        if query_value in record_text:
            return True

        if phone_digits and len(phone_digits) >= 4 and phone_digits in record_digits:
            return True

        return False

    users = []
    organizations = []

    if table_exists(db, "users"):
        user_columns = get_columns(db, "users")
        selected_user_columns = safe_select_columns(
            user_columns,
            [
                "id",
                "email",
                "full_name",
                "name",
                "first_name",
                "last_name",
                "role",
                "organization_id",
                "company_name",
                "phone",
                "phone_number",
                "mobile_phone",
                "office_phone",
                "support_phone",
                "billing_phone",
                "is_active",
                "status",
                "account_status",
                "subscription_status",
                "plan",
                "created_at",
                "last_login",
                "last_login_at",
            ],
        )

        if selected_user_columns:
            rows = db.execute(text(f"SELECT {', '.join(selected_user_columns)} FROM users")).fetchall()
            users = [row_to_dict(row) for row in rows]
            users = [user for user in users if matches(user)]

    if table_exists(db, "organizations"):
        org_columns = get_columns(db, "organizations")
        selected_org_columns = safe_select_columns(
            org_columns,
            [
                "id",
                "name",
                "company_name",
                "organization_name",
                "phone",
                "phone_number",
                "office_phone",
                "support_phone",
                "billing_phone",
                "owner_user_id",
                "plan",
                "subscription_status",
                "stripe_customer_id",
                "stripe_subscription_id",
                "created_at",
                "updated_at",
            ],
        )

        if selected_org_columns:
            rows = db.execute(text(f"SELECT {', '.join(selected_org_columns)} FROM organizations")).fetchall()
            organizations = [row_to_dict(row) for row in rows]
            organizations = [org for org in organizations if matches(org)]

    return {
        "query": q,
        "users": users,
        "organizations": organizations,
        "user_count": len(users),
        "organization_count": len(organizations),
    }

