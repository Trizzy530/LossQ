from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Body, Request
from sqlalchemy.orm import Session
from sqlalchemy import inspect, text
import os
import json
import urllib.request
import urllib.error

from app.database import SessionLocal
from app.auth_utils import get_current_user
from app.services.audit_service import write_audit_event

router = APIRouter(prefix="/platform-admin", tags=["Platform Admin"])


def get_db():
  db = SessionLocal()
  try:
    yield db
  finally:
    db.close()


# LOSSQ_INTERNAL_PLATFORM_ACCESS_GUARD_V2
def _lossq_internal_access_emails():
  platform_emails = [
    item.strip().lower()
    for item in os.getenv("PLATFORM_ADMIN_EMAILS", "").split(",")
    if item.strip()
  ]

  support_emails = [
    item.strip().lower()
    for item in os.getenv("TECH_SUPPORT_EMAILS", "").split(",")
    if item.strip()
  ]

  return set(platform_emails + support_emails)


def _lossq_current_user_value(current_user, key):
  try:
    if isinstance(current_user, dict):
      return str(current_user.get(key) or "").strip()
    return str(getattr(current_user, key, "") or "").strip()
  except Exception:
    return ""


def require_platform_admin(current_user: dict):
  """
  Platform Admin is LossQ-internal only.

  Allowed:
  - Emails explicitly listed in PLATFORM_ADMIN_EMAILS or TECH_SUPPORT_EMAILS
  - Internal platform/support roles

  Not allowed:
  - Regular customer owners
  - Regular customer admins
  - Regular customer users
  - Founding Agency customers unless explicitly allowlisted
  """
  user_email = (
    _lossq_current_user_value(current_user, "email")
    or _lossq_current_user_value(current_user, "user_email")
    or _lossq_current_user_value(current_user, "sub")
  ).lower()

  user_role = _lossq_current_user_value(current_user, "role").lower()

  allowed_roles = {
    "founder",
    "platform_owner",
    "platform_admin",
    "super_admin",
    "support",
    "support_admin",
    "tech_support",
  }

  if user_email and user_email in _lossq_internal_access_emails():
    return current_user

  if user_role and user_role in allowed_roles:
    return current_user

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


# LOSSQ_FOUNDER_TECH_SUPPORT_LOOKUP_GATE_V2
def require_founder_or_tech_support(current_user=Depends(get_current_user)):
  """
  Support Lookup is a LossQ internal tool.
  Uses the same internal-access rule as Platform Admin.
  """
  return require_platform_admin(current_user)


# LOSSQ_PLATFORM_ADMIN_AUDIT_EVENTS_V1
def lossq_platform_record_audit(
  db: Session,
  current_user,
  request: Request,
  action: str,
  resource_type: str = "platform_admin",
  resource_id: str = "",
  details: dict | None = None,
):
  """
  Best-effort audit logging for internal LossQ admin actions.
  Never block the admin route if audit logging fails.
  """
  try:
    write_audit_event(
      db=db,
      current_user=current_user,
      action=action,
      resource_type=resource_type,
      resource_id=str(resource_id or ""),
      details=details or {},
      request=request,
    )
  except Exception as exc:
    print("LOSSQ_PLATFORM_ADMIN_AUDIT_ERROR:", str(exc)[:300])


@router.get("/stats")
def platform_stats(
  request: Request,
  db: Session = Depends(get_db),
  current_user: dict = Depends(get_current_user),
):
  require_platform_admin(current_user)
  lossq_platform_record_audit(
    db=db,
    current_user=current_user,
    request=request,
    action="platform_admin_stats_viewed",
    details={"section": "stats"},
  )

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
  request: Request,
  db: Session = Depends(get_db),
  current_user: dict = Depends(get_current_user),
):
  require_platform_admin(current_user)
  lossq_platform_record_audit(
    db=db,
    current_user=current_user,
    request=request,
    action="platform_admin_users_viewed",
    details={"section": "users"},
  )

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
  request: Request,
  db: Session = Depends(get_db),
  current_user: dict = Depends(get_current_user),
):
  require_platform_admin(current_user)
  lossq_platform_record_audit(
    db=db,
    current_user=current_user,
    request=request,
    action="platform_admin_organizations_viewed",
    details={"section": "organizations"},
  )

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
  request: Request,
  q: str = "",
  db: Session = Depends(get_db),
  current_user=Depends(require_founder_or_tech_support),
):
  # LOSSQ_SUPPORT_LOOKUP_V1
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

  lossq_platform_record_audit(
    db=db,
    current_user=current_user,
    request=request,
    action="support_lookup_searched",
    resource_type="support_lookup",
    details={
      "query_length": len(query_value),
      "contains_email_symbol": "@" in query_value,
      "digits_count": len(phone_digits),
      "user_count": len(users),
      "organization_count": len(organizations),
    },
  )

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

Before testing, please review the LossQ Beta Guide:

https://www.lossq.com/beta-guide

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

Please review the LossQ Beta Guide before testing:

https://www.lossq.com/beta-guide

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


# LOSSQ_PLATFORM_ADMIN_BETA_FEEDBACK_V1
def ensure_platform_beta_feedback_table(db: Session):
  db.execute(
    text(
      """
      CREATE TABLE IF NOT EXISTS beta_feedback (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NULL,
        organization_id INTEGER NULL,
        email VARCHAR(320),
        feature VARCHAR(160),
        severity VARCHAR(50),
        message TEXT NOT NULL,
        page_url TEXT,
        status VARCHAR(50) DEFAULT 'new',
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
      """
    )
  )

  for column_sql in [
    "ALTER TABLE beta_feedback ADD COLUMN IF NOT EXISTS user_id INTEGER NULL",
    "ALTER TABLE beta_feedback ADD COLUMN IF NOT EXISTS organization_id INTEGER NULL",
    "ALTER TABLE beta_feedback ADD COLUMN IF NOT EXISTS email VARCHAR(320)",
    "ALTER TABLE beta_feedback ADD COLUMN IF NOT EXISTS feature VARCHAR(160)",
    "ALTER TABLE beta_feedback ADD COLUMN IF NOT EXISTS severity VARCHAR(50)",
    "ALTER TABLE beta_feedback ADD COLUMN IF NOT EXISTS message TEXT",
    "ALTER TABLE beta_feedback ADD COLUMN IF NOT EXISTS page_url TEXT",
    "ALTER TABLE beta_feedback ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'new'",
    "ALTER TABLE beta_feedback ADD COLUMN IF NOT EXISTS notes TEXT",
    "ALTER TABLE beta_feedback ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    "ALTER TABLE beta_feedback ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
  ]:
    try:
      db.execute(text(column_sql))
    except Exception:
      pass

  db.commit()


@router.get("/beta-feedback")
def list_beta_feedback(
  db: Session = Depends(get_db),
  current_user: dict = Depends(get_current_user),
):
  require_platform_admin(current_user)
  ensure_platform_beta_feedback_table(db)

  rows = db.execute(
    text(
      """
      SELECT id, user_id, organization_id, email, feature, severity, message,
          page_url, status, notes, created_at, updated_at
      FROM beta_feedback
      ORDER BY created_at DESC, id DESC
      LIMIT 500
      """
    )
  ).fetchall()

  feedback = [row_to_dict(row) for row in rows]

  return {
    "feedback": feedback,
    "count": len(feedback),
  }


@router.post("/beta-feedback/{feedback_id}/status")
def update_beta_feedback_status(
  feedback_id: int,
  payload: dict = Body(default={}),
  db: Session = Depends(get_db),
  current_user: dict = Depends(get_current_user),
):
  require_platform_admin(current_user)
  ensure_platform_beta_feedback_table(db)

  status = str(payload.get("status") or "").strip().lower()
  notes = str(payload.get("notes") or "").strip()

  allowed = {"new", "reviewing", "fixed", "closed"}
  if status not in allowed:
    raise HTTPException(status_code=400, detail="Status must be one of: new, reviewing, fixed, closed.")

  result = db.execute(
    text(
      """
      UPDATE beta_feedback
      SET status = :status,
        notes = :notes,
        updated_at = CURRENT_TIMESTAMP
      WHERE id = :feedback_id
      """
    ),
    {
      "feedback_id": feedback_id,
      "status": status,
      "notes": notes,
    },
  )

  db.commit()

  if getattr(result, "rowcount", 0) == 0:
    raise HTTPException(status_code=404, detail="Beta feedback not found.")

  return {
    "ok": True,
    "message": "Beta feedback updated.",
    "feedback_id": feedback_id,
    "status": status,
  }


# LOSSQ_PLATFORM_ADMIN_BETA_ACTIVITY_V1
@router.get("/beta-activity")
def platform_beta_activity(
  db: Session = Depends(get_db),
  current_user: dict = Depends(get_current_user),
):
  require_platform_admin(current_user)

  if not table_exists(db, "users"):
    return {"beta_users": [], "count": 0, "message": "No users table found."}

  user_columns = get_columns(db, "users")
  org_columns = get_columns(db, "organizations") if table_exists(db, "organizations") else []

  selected_user_columns = safe_select_columns(
    user_columns,
    [
      "id",
      "email",
      "full_name",
      "first_name",
      "last_name",
      "role",
      "organization_id",
      "created_at",
      "last_login_at",
      "is_active",
    ],
  )

  if not selected_user_columns:
    return {"beta_users": [], "count": 0, "message": "No usable user columns found."}

  users = [
    row_to_dict(row)
    for row in db.execute(
      text(f"SELECT {', '.join(selected_user_columns)} FROM users ORDER BY id DESC")
    ).fetchall()
  ]

  orgs = {}
  if org_columns:
    selected_org_columns = safe_select_columns(
      org_columns,
      [
        "id",
        "name",
        "company_name",
        "organization_name",
        "plan",
        "subscription_status",
        "upload_limit",
        "user_limit",
        "current_period_end",
        "created_at",
      ],
    )

    if selected_org_columns:
      org_rows = db.execute(
        text(f"SELECT {', '.join(selected_org_columns)} FROM organizations")
      ).fetchall()
      orgs = {row_to_dict(row).get("id"): row_to_dict(row) for row in org_rows}

  feedback_counts = {}
  if table_exists(db, "beta_feedback"):
    try:
      rows = db.execute(
        text(
          """
          SELECT lower(email) AS email, COUNT(*) AS feedback_count
          FROM beta_feedback
          GROUP BY lower(email)
          """
        )
      ).fetchall()

      feedback_counts = {
        str(row_to_dict(row).get("email") or "").lower(): int(row_to_dict(row).get("feedback_count") or 0)
        for row in rows
      }
    except Exception:
      feedback_counts = {}

  upload_counts_by_org = {}
  upload_counts_by_user = {}

  upload_table_candidates = [
    "upload_history",
    "uploads",
    "loss_run_uploads",
    "documents",
  ]

  for table_name in upload_table_candidates:
    if not table_exists(db, table_name):
      continue

    columns = get_columns(db, table_name)

    try:
      if "organization_id" in columns:
        rows = db.execute(
          text(f"SELECT organization_id, COUNT(*) AS upload_count FROM {table_name} GROUP BY organization_id")
        ).fetchall()

        for row in rows:
          data = row_to_dict(row)
          org_id = data.get("organization_id")
          upload_counts_by_org[org_id] = upload_counts_by_org.get(org_id, 0) + int(data.get("upload_count") or 0)

      if "user_id" in columns:
        rows = db.execute(
          text(f"SELECT user_id, COUNT(*) AS upload_count FROM {table_name} GROUP BY user_id")
        ).fetchall()

        for row in rows:
          data = row_to_dict(row)
          user_id = data.get("user_id")
          upload_counts_by_user[user_id] = upload_counts_by_user.get(user_id, 0) + int(data.get("upload_count") or 0)
    except Exception:
      pass

  beta_users = []

  for user in users:
    org = orgs.get(user.get("organization_id")) or {}

    plan = str(org.get("plan") or "").strip().lower()
    subscription_status = str(org.get("subscription_status") or "").strip().lower()

    is_beta = plan in {"beta", "beta_access", "early_access"} or subscription_status.startswith("beta")

    if not is_beta:
      continue

    email = str(user.get("email") or "").strip().lower()
    org_id = user.get("organization_id")

    full_name = (
      user.get("full_name")
      or " ".join(
        part
        for part in [
          str(user.get("first_name") or "").strip(),
          str(user.get("last_name") or "").strip(),
        ]
        if part
      )
      or ""
    )

    uploads_used = int(upload_counts_by_user.get(user.get("id"), 0) or 0)
    if uploads_used == 0 and org_id in upload_counts_by_org:
      uploads_used = int(upload_counts_by_org.get(org_id, 0) or 0)

    beta_users.append(
      {
        "user_id": user.get("id"),
        "email": email,
        "full_name": full_name,
        "role": user.get("role"),
        "is_active": user.get("is_active"),
        "organization_id": org_id,
        "organization_name": org.get("name") or org.get("company_name") or org.get("organization_name") or "",
        "plan": org.get("plan"),
        "subscription_status": org.get("subscription_status"),
        "upload_limit": org.get("upload_limit"),
        "user_limit": org.get("user_limit"),
        "uploads_used": uploads_used,
        "feedback_count": int(feedback_counts.get(email, 0) or 0),
        "last_login_at": user.get("last_login_at"),
        "registered_at": user.get("created_at"),
        "beta_expires_at": org.get("current_period_end"),
      }
    )

  beta_users.sort(
    key=lambda item: (
      str(item.get("last_login_at") or ""),
      str(item.get("registered_at") or ""),
    ),
    reverse=True,
  )

  return {
    "beta_users": beta_users,
    "count": len(beta_users),
  }


# LOSSQ_PLATFORM_ADMIN_BETA_EXIT_SURVEYS_V1
def ensure_platform_beta_exit_surveys_table(db: Session):
  db.execute(
    text(
      """
      CREATE TABLE IF NOT EXISTS beta_exit_surveys (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NULL,
        organization_id INTEGER NULL,
        email VARCHAR(320),
        overall_score INTEGER,
        would_pay VARCHAR(80),
        likely_plan VARCHAR(120),
        most_valuable_feature TEXT,
        most_confusing_part TEXT,
        missing_feature TEXT,
        would_recommend VARCHAR(80),
        launch_blocker TEXT,
        additional_feedback TEXT,
        page_url TEXT,
        status VARCHAR(50) DEFAULT 'new',
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
      """
    )
  )

  for column_sql in [
    "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS user_id INTEGER NULL",
    "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS organization_id INTEGER NULL",
    "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS email VARCHAR(320)",
    "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS overall_score INTEGER",
    "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS would_pay VARCHAR(80)",
    "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS likely_plan VARCHAR(120)",
    "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS most_valuable_feature TEXT",
    "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS most_confusing_part TEXT",
    "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS missing_feature TEXT",
    "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS would_recommend VARCHAR(80)",
    "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS launch_blocker TEXT",
    "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS additional_feedback TEXT",
    "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS page_url TEXT",
    "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'new'",
    "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS notes TEXT",
    "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
  ]:
    try:
      db.execute(text(column_sql))
    except Exception:
      pass

  db.commit()


@router.get("/beta-exit-surveys")
def list_beta_exit_surveys(
  db: Session = Depends(get_db),
  current_user: dict = Depends(get_current_user),
):
  require_platform_admin(current_user)
  ensure_platform_beta_exit_surveys_table(db)

  rows = db.execute(
    text(
      """
      SELECT id, user_id, organization_id, email, overall_score, would_pay,
          likely_plan, most_valuable_feature, most_confusing_part,
          missing_feature, would_recommend, launch_blocker,
          additional_feedback, page_url, status, notes, created_at, updated_at
      FROM beta_exit_surveys
      ORDER BY created_at DESC, id DESC
      LIMIT 500
      """
    )
  ).fetchall()

  surveys = [row_to_dict(row) for row in rows]

  average_score = None
  scores = [
    int(item.get("overall_score") or 0)
    for item in surveys
    if int(item.get("overall_score") or 0) > 0
  ]

  if scores:
    average_score = round(sum(scores) / len(scores), 1)

  return {
    "surveys": surveys,
    "count": len(surveys),
    "average_score": average_score,
  }


@router.post("/beta-exit-surveys/{survey_id}/status")
def update_beta_exit_survey_status(
  survey_id: int,
  payload: dict = Body(default={}),
  db: Session = Depends(get_db),
  current_user: dict = Depends(get_current_user),
):
  require_platform_admin(current_user)
  ensure_platform_beta_exit_surveys_table(db)

  status = str(payload.get("status") or "").strip().lower()
  notes = str(payload.get("notes") or "").strip()

  allowed = {"new", "reviewed", "follow_up", "closed"}
  if status not in allowed:
    raise HTTPException(status_code=400, detail="Status must be one of: new, reviewed, follow_up, closed.")

  result = db.execute(
    text(
      """
      UPDATE beta_exit_surveys
      SET status = :status,
        notes = :notes,
        updated_at = CURRENT_TIMESTAMP
      WHERE id = :survey_id
      """
    ),
    {
      "survey_id": survey_id,
      "status": status,
      "notes": notes,
    },
  )

  db.commit()

  if getattr(result, "rowcount", 0) == 0:
    raise HTTPException(status_code=404, detail="Beta exit survey not found.")

  return {
    "ok": True,
    "message": "Beta exit survey updated.",
    "survey_id": survey_id,
    "status": status,
  }
