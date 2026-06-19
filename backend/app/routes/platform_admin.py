from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy import inspect, text
import os
import json
import urllib.request
import urllib.error

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

    if user_email in allowed_emails or user_role in {"platform_admin", "super_admin"}:
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




# LOSSQ_FOUNDER_TECH_SUPPORT_LOOKUP_GATE_V1
def require_founder_or_tech_support(current_user=Depends(get_current_user)):
    """
    Support Lookup is a LossQ internal tool.

    Allowed:
    - Founder / platform admin emails
    - Tech support emails

    Not allowed:
    - Regular agency users
    - Regular agency admins
    - Regular agency owners
    - Founding Agency customers unless specifically allowlisted
    """
    if isinstance(current_user, dict):
        user_email = str(current_user.get("email", "") or "").strip().lower()
    else:
        user_email = str(getattr(current_user, "email", "") or "").strip().lower()

    founder_emails = [
        item.strip().lower()
        for item in os.getenv("PLATFORM_ADMIN_EMAILS", "").split(",")
        if item.strip()
    ]

    tech_support_emails = [
        item.strip().lower()
        for item in os.getenv("TECH_SUPPORT_EMAILS", "").split(",")
        if item.strip()
    ]

    allowed_emails = set(founder_emails + tech_support_emails)

    if user_email and user_email in allowed_emails:
        return current_user

    raise HTTPException(
        status_code=403,
        detail="Support Lookup is restricted to LossQ Founder and Tech Support only.",
    )


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
    current_user=Depends(require_founder_or_tech_support),
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

# LOSSQ_PLATFORM_ADMIN_BETA_ACCESS_ENDPOINTS_V1
def _lossq_platform_find_beta_org_id(db: Session, payload: dict):
    org_id = payload.get("organization_id") or payload.get("org_id")
    email = str(payload.get("email") or payload.get("user_email") or "").strip().lower()

    if org_id:
        try:
            return int(org_id)
        except Exception:
            raise HTTPException(status_code=400, detail="organization_id must be a number.")

    if not email:
        raise HTTPException(status_code=400, detail="Provide organization_id or user email.")

    if not table_exists(db, "users"):
        raise HTTPException(status_code=404, detail="Users table not found.")

    rows = db.execute(
        text("SELECT organization_id FROM users WHERE lower(email) = :email LIMIT 1"),
        {"email": email},
    ).fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail="No user found with that email.")

    row = row_to_dict(rows[0])
    found_org_id = row.get("organization_id")

    if not found_org_id:
        raise HTTPException(status_code=404, detail="User does not have an organization_id.")

    return int(found_org_id)


def _lossq_platform_org_update_columns(db: Session):
    if not table_exists(db, "organizations"):
        raise HTTPException(status_code=404, detail="Organizations table not found.")
    return get_columns(db, "organizations")


@router.post("/beta-access/grant")
def grant_beta_access(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)

    org_id = _lossq_platform_find_beta_org_id(db, payload)
    columns = _lossq_platform_org_update_columns(db)

    days = int(payload.get("days") or 30)
    upload_limit = int(payload.get("upload_limit") or 10)
    user_limit = int(payload.get("user_limit") or 1)

    if days < 1 or days > 120:
        raise HTTPException(status_code=400, detail="Beta days must be between 1 and 120.")

    beta_end = datetime.now(timezone.utc) + timedelta(days=days)

    updates = {
        "plan": "beta",
        "subscription_status": "active",
        "upload_limit": upload_limit,
        "current_period_end": beta_end,
    }

    if "user_limit" in columns:
        updates["user_limit"] = user_limit

    set_parts = []
    params = {"org_id": org_id}

    for key, value in updates.items():
        if key in columns:
            set_parts.append(f"{key} = :{key}")
            params[key] = value

    if "updated_at" in columns:
        set_parts.append("updated_at = CURRENT_TIMESTAMP")

    if not set_parts:
        raise HTTPException(status_code=500, detail="No beta access columns are available to update.")

    db.execute(
        text(f"UPDATE organizations SET {', '.join(set_parts)} WHERE id = :org_id"),
        params,
    )
    db.commit()

    rows = db.execute(
        text("SELECT id, name, plan, subscription_status, upload_limit, current_period_end FROM organizations WHERE id = :org_id"),
        {"org_id": org_id},
    ).fetchall()

    org = row_to_dict(rows[0]) if rows else {"id": org_id}

    return {
        "ok": True,
        "message": "Beta access granted.",
        "organization": org,
        "days": days,
        "upload_limit": upload_limit,
        "user_limit": user_limit,
    }


@router.post("/beta-access/revoke")
def revoke_beta_access(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)

    org_id = _lossq_platform_find_beta_org_id(db, payload)
    columns = _lossq_platform_org_update_columns(db)

    updates = {
        "plan": "free",
        "subscription_status": "beta_revoked",
        "upload_limit": 0,
        "current_period_end": None,
    }

    if "user_limit" in columns:
        updates["user_limit"] = 1

    set_parts = []
    params = {"org_id": org_id}

    for key, value in updates.items():
        if key in columns:
            set_parts.append(f"{key} = :{key}")
            params[key] = value

    if "updated_at" in columns:
        set_parts.append("updated_at = CURRENT_TIMESTAMP")

    db.execute(
        text(f"UPDATE organizations SET {', '.join(set_parts)} WHERE id = :org_id"),
        params,
    )
    db.commit()

    return {
        "ok": True,
        "message": "Beta access revoked.",
        "organization_id": org_id,
    }




# LOSSQ_BETA_STATUS_EMAILS_V1
def send_beta_status_email(email: str, status: str):
    clean_email = str(email or "").strip().lower()
    clean_status = str(status or "").strip().lower()

    if not clean_email or "@" not in clean_email:
        return False

    resend_api_key = os.getenv("RESEND_API_KEY", "").strip()
    from_email = os.getenv("SMTP_FROM_EMAIL", "hello@lossq.com").strip()

    if not resend_api_key or not from_email:
        print(
            "LOSSQ_BETA_STATUS_EMAIL_NOT_CONFIGURED:",
            {"email": clean_email, "status": clean_status, "from_email": from_email, "has_resend_key": bool(resend_api_key)},
        )
        return False

    if clean_status == "approved":
        subject = "Your LossQ beta request was approved"
        body = """Hi,

Your LossQ beta request has been approved.

Once your registered LossQ account is matched to this email address, our team can activate beta dashboard access.

Best,
LossQ Team
hello@lossq.com
"""
    elif clean_status == "activated":
        subject = "Your LossQ beta access is active"
        body = """Hi,

Your LossQ beta dashboard access is now active.

You can log in here:

https://www.lossq.com/login

Best,
LossQ Team
hello@lossq.com
"""
    elif clean_status == "rejected":
        subject = "LossQ beta request update"
        body = """Hi,

Thank you for your interest in LossQ.

We are not opening beta access to this account yet. We may expand beta availability as additional testing slots become available.

Best,
LossQ Team
hello@lossq.com
"""
    else:
        return False

    request_payload = {
        "from": from_email,
        "to": [clean_email],
        "subject": subject,
        "text": body,
    }

    request = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(request_payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {resend_api_key}",
            "Content-Type": "application/json",
            "User-Agent": "LossQ/1.0 (https://www.lossq.com; hello@lossq.com)",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            print(
                "LOSSQ_BETA_STATUS_EMAIL_SENT:",
                {"email": clean_email, "status": clean_status, "http_status": response.status, "response": response_body[:500]},
            )
            return 200 <= response.status < 300
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        print(
            "LOSSQ_BETA_STATUS_EMAIL_HTTP_ERROR:",
            {"email": clean_email, "status": clean_status, "http_status": exc.code, "body": error_body[:1000]},
        )
        return False
    except Exception as exc:
        print("LOSSQ_BETA_STATUS_EMAIL_ERROR:", {"email": clean_email, "status": clean_status, "error": str(exc)[:500]})
        return False

# LOSSQ_PLATFORM_ADMIN_BETA_REQUESTS_V1
def ensure_platform_beta_requests_table(db: Session):
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS beta_requests (
                id SERIAL PRIMARY KEY,
                email VARCHAR(320) UNIQUE NOT NULL,
                source VARCHAR(120),
                page_url TEXT,
                user_agent TEXT,
                status VARCHAR(50) DEFAULT 'new',
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                approved_at TIMESTAMP NULL,
                rejected_at TIMESTAMP NULL,
                activated_at TIMESTAMP NULL
            )
            """
        )
    )

    for column_sql in [
        "ALTER TABLE beta_requests ADD COLUMN IF NOT EXISTS source VARCHAR(120)",
        "ALTER TABLE beta_requests ADD COLUMN IF NOT EXISTS page_url TEXT",
        "ALTER TABLE beta_requests ADD COLUMN IF NOT EXISTS user_agent TEXT",
        "ALTER TABLE beta_requests ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'new'",
        "ALTER TABLE beta_requests ADD COLUMN IF NOT EXISTS notes TEXT",
        "ALTER TABLE beta_requests ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE beta_requests ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE beta_requests ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP NULL",
        "ALTER TABLE beta_requests ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMP NULL",
        "ALTER TABLE beta_requests ADD COLUMN IF NOT EXISTS activated_at TIMESTAMP NULL",
    ]:
        try:
            db.execute(text(column_sql))
        except Exception:
            pass

    db.commit()


def _lossq_apply_beta_access_to_org(db: Session, org_id: int, days: int = 30, upload_limit: int = 10, user_limit: int = 1):
    columns = _lossq_platform_org_update_columns(db)

    beta_end = datetime.now(timezone.utc) + timedelta(days=days)

    updates = {
        "plan": "beta",
        "subscription_status": "active",
        "upload_limit": upload_limit,
        "current_period_end": beta_end,
    }

    if "user_limit" in columns:
        updates["user_limit"] = user_limit

    set_parts = []
    params = {"org_id": org_id}

    for key, value in updates.items():
        if key in columns:
            set_parts.append(f"{key} = :{key}")
            params[key] = value

    if not set_parts:
        raise HTTPException(status_code=500, detail="No beta access columns are available to update.")

    db.execute(
        text(f"UPDATE organizations SET {', '.join(set_parts)} WHERE id = :org_id"),
        params,
    )

    rows = db.execute(
        text("SELECT id, name, plan, subscription_status, upload_limit, current_period_end FROM organizations WHERE id = :org_id"),
        {"org_id": org_id},
    ).fetchall()

    return row_to_dict(rows[0]) if rows else {"id": org_id}


@router.get("/beta-requests")
def list_beta_requests(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)
    ensure_platform_beta_requests_table(db)

    rows = db.execute(
        text(
            """
            SELECT id, email, source, page_url, user_agent, status, notes,
                   created_at, updated_at, approved_at, rejected_at, activated_at
            FROM beta_requests
            ORDER BY created_at DESC, id DESC
            LIMIT 250
            """
        )
    ).fetchall()

    requests = [row_to_dict(row) for row in rows]

    for item in requests:
        email = str(item.get("email") or "").strip().lower()
        item["registered"] = False
        item["user"] = None
        item["organization"] = None

        if not email or not table_exists(db, "users"):
            continue

        user_rows = db.execute(
            text("SELECT id, email, role, organization_id, created_at FROM users WHERE lower(email) = :email LIMIT 1"),
            {"email": email},
        ).fetchall()

        if user_rows:
            user = row_to_dict(user_rows[0])
            item["registered"] = True
            item["user"] = user

            org_id = user.get("organization_id")
            if org_id and table_exists(db, "organizations"):
                org_rows = db.execute(
                    text("SELECT id, name, plan, subscription_status, upload_limit, current_period_end FROM organizations WHERE id = :org_id LIMIT 1"),
                    {"org_id": org_id},
                ).fetchall()
                item["organization"] = row_to_dict(org_rows[0]) if org_rows else None

    return {"beta_requests": requests, "count": len(requests)}


@router.post("/beta-requests/{request_id}/approve")
def approve_beta_request(
    request_id: int,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)
    ensure_platform_beta_requests_table(db)

    rows = db.execute(
        text("SELECT id, email FROM beta_requests WHERE id = :request_id LIMIT 1"),
        {"request_id": request_id},
    ).fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail="Beta request not found.")

    request_row = row_to_dict(rows[0])
    email = str(request_row.get("email") or "").strip().lower()

    days = int(payload.get("days") or 30)
    upload_limit = int(payload.get("upload_limit") or 10)
    user_limit = int(payload.get("user_limit") or 1)

    if days < 1 or days > 120:
        raise HTTPException(status_code=400, detail="Beta days must be between 1 and 120.")

    try:
        org_id = _lossq_platform_find_beta_org_id(db, {"email": email})
    except HTTPException:
        db.execute(
            text(
                """
                UPDATE beta_requests
                SET status = 'approved',
                    approved_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP,
                    notes = 'Approved pending user registration.'
                WHERE id = :request_id
                """
            ),
            {"request_id": request_id},
        )
        db.commit()

        # LOSSQ_BETA_APPROVED_EMAIL_SEND_V1
        beta_status_email_sent = send_beta_status_email(email, "approved")

        return {
            "ok": True,
            "status": "approved",
            "message": "Beta request approved. Access can be activated after the registered account is matched to this email.",
            "email": email,
            "beta_status_email_sent": beta_status_email_sent,
        }

    organization = _lossq_apply_beta_access_to_org(
        db,
        org_id=org_id,
        days=days,
        upload_limit=upload_limit,
        user_limit=user_limit,
    )

    db.execute(
        text(
            """
            UPDATE beta_requests
            SET status = 'activated',
                approved_at = COALESCE(approved_at, CURRENT_TIMESTAMP),
                activated_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP,
                notes = 'Beta access activated.'
            WHERE id = :request_id
            """
        ),
        {"request_id": request_id},
    )

    db.commit()

    # LOSSQ_BETA_ACTIVATED_EMAIL_SEND_V1
    beta_status_email_sent = send_beta_status_email(email, "activated")

    return {
        "ok": True,
        "status": "activated",
        "message": "Beta access activated.",
        "email": email,
        "organization": organization,
        "days": days,
        "upload_limit": upload_limit,
        "user_limit": user_limit,
        "beta_status_email_sent": beta_status_email_sent,
    }


@router.post("/beta-requests/{request_id}/reject")
def reject_beta_request(
    request_id: int,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)
    ensure_platform_beta_requests_table(db)

    note = str(payload.get("note") or "Rejected by platform admin.").strip()

    request_rows = db.execute(
        text("SELECT email FROM beta_requests WHERE id = :request_id LIMIT 1"),
        {"request_id": request_id},
    ).fetchall()
    request_email = str(row_to_dict(request_rows[0]).get("email") or "").strip().lower() if request_rows else ""

    result = db.execute(
        text(
            """
            UPDATE beta_requests
            SET status = 'rejected',
                rejected_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP,
                notes = :note
            WHERE id = :request_id
            """
        ),
        {"request_id": request_id, "note": note},
    )

    db.commit()

    if getattr(result, "rowcount", 0) == 0:
        raise HTTPException(status_code=404, detail="Beta request not found.")

    # LOSSQ_BETA_REJECTED_EMAIL_SEND_V1
    beta_status_email_sent = send_beta_status_email(request_email, "rejected") if request_email else False

    return {
        "ok": True,
        "status": "rejected",
        "message": "Beta request rejected.",
        "request_id": request_id,
        "beta_status_email_sent": beta_status_email_sent,
    }
