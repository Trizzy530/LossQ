import re
import os
import resend
from datetime import datetime, timedelta
from typing import Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.organization import Organization
from app.models.user import User
from app.services.audit import record_audit_event

load_dotenv()

router = APIRouter(prefix="/auth", tags=["Auth"])

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable is required")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
RESET_TOKEN_EXPIRE_MINUTES = 30
VERIFY_TOKEN_EXPIRE_MINUTES = 1440
INVITE_TOKEN_EXPIRE_MINUTES = 10080

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://lossq.com").rstrip("/")
FROM_EMAIL = os.getenv("FROM_EMAIL", "LossQ <onboarding@resend.dev>")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


# LOSSQ_PASSWORD_POLICY_AUTH_ROUTE_V1
PASSWORD_POLICY_MESSAGE = (
    "Password must be at least 8 characters and include at least "
    "1 uppercase letter and 1 special character."
)


def validate_password_strength(password: str):
    password = str(password or "")

    if len(password) < 8:
        raise HTTPException(status_code=400, detail=PASSWORD_POLICY_MESSAGE)

    if not re.search(r"[A-Z]", password):
        raise HTTPException(status_code=400, detail=PASSWORD_POLICY_MESSAGE)

    if not re.search(r"[^A-Za-z0-9]", password):
        raise HTTPException(status_code=400, detail=PASSWORD_POLICY_MESSAGE)

    return True


def hash_valid_password(password: str):
    validate_password_strength(password)
    return pwd_context.hash(password)

security = HTTPBearer()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    organization_name: str
    first_name: Optional[str] = ""
    last_name: Optional[str] = ""

    # LOSSQ_REGISTER_SAVE_BUSINESS_ROLE_INTAKE_V2
    account_role: Optional[str] = ""
    role: Optional[str] = ""
    company_type: Optional[str] = ""
    monthly_volume: Optional[str] = ""
    primary_lines: Optional[object] = ""
    ams_system: Optional[str] = ""
    market_state: Optional[str] = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class InviteUserRequest(BaseModel):
    email: EmailStr
    role: str = "user"


class AcceptInviteRequest(BaseModel):
    token: str
    password: str
    first_name: Optional[str] = ""
    last_name: Optional[str] = ""


class VerifyPasswordRequest(BaseModel):
    password: str


class UpdateMeRequest(BaseModel):
    first_name: Optional[str] = ""
    last_name: Optional[str] = ""


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


def get_db():
    db = SessionLocal()
    try:
        ensure_security_columns(db)
        yield db
    finally:
        db.close()


def ensure_security_columns(db: Session):
    dialect = db.bind.dialect.name if db.bind is not None else ""

    def column_exists(table_name: str, column_name: str) -> bool:
        if dialect == "postgresql":
            result = db.execute(
                text(
                    """
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = :table_name
                      AND column_name = :column_name
                    LIMIT 1
                    """
                ),
                {"table_name": table_name, "column_name": column_name},
            ).first()
            return result is not None

        result = db.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
        return any(row[1] == column_name for row in result)

    def add_column(table_name: str, column_name: str, column_sql: str):
        if not column_exists(table_name, column_name):
            db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"))
            db.commit()

    add_column("users", "first_name", "VARCHAR")
    add_column("users", "last_name", "VARCHAR")
    add_column("users", "is_email_verified", "BOOLEAN DEFAULT FALSE")
    add_column("users", "is_active", "BOOLEAN DEFAULT TRUE")
    add_column("users", "last_login_at", "TIMESTAMP")
    add_column("users", "created_at", "TIMESTAMP")
    add_column("users", "updated_at", "TIMESTAMP")

    add_column("organizations", "user_limit", "INTEGER DEFAULT 5")
    add_column("organizations", "owner_user_id", "INTEGER")

    # LOSSQ_AGENCY_PROFILE_DB_COLUMNS_V1
    add_column("organizations", "agency_contact_name", "VARCHAR")
    add_column("organizations", "agency_email", "VARCHAR")
    add_column("organizations", "agency_phone", "VARCHAR")
    add_column("organizations", "agency_address", "VARCHAR")
    add_column("organizations", "agency_city", "VARCHAR")
    add_column("organizations", "agency_state", "VARCHAR")
    add_column("organizations", "agency_zip", "VARCHAR")
    add_column("organizations", "agency_website", "VARCHAR")
    add_column("organizations", "agency_license_number", "VARCHAR")
    add_column("organizations", "agency_logo_url", "VARCHAR")
    add_column("organizations", "created_at", "TIMESTAMP")
    add_column("organizations", "updated_at", "TIMESTAMP")

    db.execute(text("UPDATE users SET is_email_verified = FALSE WHERE is_email_verified IS NULL"))
    db.execute(text("UPDATE users SET is_active = TRUE WHERE is_active IS NULL"))
    db.execute(text("UPDATE users SET role = 'user' WHERE role IS NULL OR role = ''"))
    db.execute(text("UPDATE organizations SET user_limit = 5 WHERE user_limit IS NULL OR user_limit <= 0"))
    db.commit()


def create_token(data: dict, minutes: int):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(user: User):
    return create_token(
        {
            "sub": user.email,
            "user_id": user.id,
            "role": user.role or "user",
            "organization_id": user.organization_id,
        },
        ACCESS_TOKEN_EXPIRE_MINUTES,
    )


def decode_token_or_400(token: str, expected_type: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    if payload.get("type") != expected_type:
        raise HTTPException(status_code=400, detail="Invalid token type")

    return payload


def send_email(to: str, subject: str, html: str):
    if not RESEND_API_KEY:
        print(f"EMAIL DEBUG -> TO: {to} | SUBJECT: {subject}")
        print(html)
        return {"sent": False, "reason": "RESEND_API_KEY is not configured"}

    try:
        return resend.Emails.send({
            "from": FROM_EMAIL,
            "to": [to],
            "subject": subject,
            "html": html,
        })
    except Exception as exc:
        print(f"EMAIL SEND FAILED -> TO: {to} | SUBJECT: {subject} | ERROR: {exc}")
        return {"sent": False, "reason": str(exc)}


def email_shell(title: str, preview: str, button_text: str, button_url: str, footer_note: str = ""):
    return f"""
    <div style="margin:0;padding:0;background:#020617;font-family:Arial,Helvetica,sans-serif;color:#e5e7eb;">
      <div style="max-width:640px;margin:0 auto;padding:32px 20px;">
        <div style="background:#0f172a;border:1px solid #1e3a8a;border-radius:20px;overflow:hidden;">
          <div style="padding:28px 32px;border-bottom:1px solid #1e293b;background:linear-gradient(135deg,#020617,#0f172a,#111827);">
            <div style="font-size:34px;font-weight:900;letter-spacing:-1px;color:#ffffff;">Loss<span style="color:#2563eb;">Q</span></div>
            <div style="margin-top:6px;font-size:11px;letter-spacing:4px;text-transform:uppercase;color:#93c5fd;">AI Underwriting Platform</div>
          </div>

          <div style="padding:34px 32px;">
            <h1 style="margin:0 0 12px;font-size:24px;line-height:1.25;color:#ffffff;">{title}</h1>
            <p style="margin:0 0 26px;font-size:15px;line-height:1.7;color:#cbd5e1;">{preview}</p>

            <a href="{button_url}" style="display:inline-block;background:#2563eb;color:#ffffff;text-decoration:none;font-weight:800;padding:14px 22px;border-radius:12px;">
              {button_text}
            </a>

            <p style="margin:28px 0 0;font-size:12px;line-height:1.6;color:#94a3b8;">
              If the button does not work, copy and paste this link into your browser:<br />
              <span style="color:#93c5fd;word-break:break-all;">{button_url}</span>
            </p>

            {f'<p style="margin:18px 0 0;font-size:12px;line-height:1.6;color:#94a3b8;">{footer_note}</p>' if footer_note else ''}
          </div>
        </div>

        <p style="text-align:center;margin:18px 0 0;font-size:11px;color:#64748b;">
          © 2026 LossQ. This is a transactional account security email.
        </p>
      </div>
    </div>
    """


def public_user(user: User):
    return {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "role": user.role or "user",
        "organization_id": user.organization_id,
        "is_email_verified": bool(user.is_email_verified),
        "is_active": bool(user.is_active),
    }


def audit_actor(user):
    if not user:
        return None

    return {
        "id": getattr(user, "id", None),
        "user_id": getattr(user, "id", None),
        "email": getattr(user, "email", ""),
        "user_email": getattr(user, "email", ""),
        "organization_id": getattr(user, "organization_id", None),
        "first_name": getattr(user, "first_name", "") or "",
        "last_name": getattr(user, "last_name", "") or "",
    }


def audit_user_details(user, extra=None):
    details = {
        "user_id": getattr(user, "id", None),
        "user_email": getattr(user, "email", ""),
        "user_full_name": " ".join(
            part
            for part in [
                getattr(user, "first_name", "") or "",
                getattr(user, "last_name", "") or "",
            ]
            if str(part).strip()
        ).strip(),
        "role": getattr(user, "role", "") or "",
        "organization_id": getattr(user, "organization_id", None),
    }

    if extra:
        details.update(extra)

    return details


def user_count_for_org(db: Session, organization_id: int):
    return (
        db.query(User)
        .filter(User.organization_id == organization_id, User.is_active == True)  # noqa: E712
        .count()
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    token = credentials.credentials

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = payload.get("user_id")
    email = payload.get("sub")

    user = None
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
    if not user and email:
        user = db.query(User).filter(User.email == email).first()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    if not bool(user.is_active):
        raise HTTPException(status_code=403, detail="User account is disabled")

    return user


def require_owner(user: User = Depends(get_current_user)):
    if (user.role or "").lower() != "owner":
        raise HTTPException(status_code=403, detail="Owner access required")
    return user


def require_admin_or_owner(user: User = Depends(get_current_user)):
    if (user.role or "").lower() not in ["owner", "admin"]:
        raise HTTPException(status_code=403, detail="Admin or owner access required")
    return user



def public_registration_role(requested_role=None):
    # LOSSQ_BLOCK_PUBLIC_OWNER_ROLE_V1
    # Public registration must never trust a browser-selected owner role.
    # The backend may still assign owner internally for the first user of a new organization.
    clean_role = str(requested_role or "user").strip().lower()

    if clean_role in {"admin", "user"}:
        return clean_role

    return "user"


@router.post("/register")
def register_user(data: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    clean_email = data.email.strip().lower()
    organization_name = data.organization_name.strip()

    if len(data.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    existing_user = db.query(User).filter(User.email == clean_email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    organization = db.query(Organization).filter(Organization.name == organization_name).first()

    if not organization:
        organization = Organization(name=organization_name, user_limit=5)
        db.add(organization)

    # LOSSQ_REGISTER_SAVE_BUSINESS_ROLE_INTAKE_SQL_V2
    try:
        business_role = str(getattr(data, "account_role", "") or getattr(data, "role", "") or "").strip()
        company_type_value = str(getattr(data, "company_type", "") or "").strip()
        monthly_volume_value = str(getattr(data, "monthly_volume", "") or "").strip()
        primary_lines_value = getattr(data, "primary_lines", "") or ""
        if isinstance(primary_lines_value, list):
            primary_lines_value = ", ".join([str(x).strip() for x in primary_lines_value if str(x).strip()])
        else:
            primary_lines_value = str(primary_lines_value or "").strip()
        ams_system_value = str(getattr(data, "ams_system", "") or "").strip()
        market_state_value = str(getattr(data, "market_state", "") or "").strip()

        db.execute(
            text("""
                UPDATE organizations
                SET account_role = :account_role,
                    company_type = :company_type,
                    monthly_volume = :monthly_volume,
                    primary_lines = :primary_lines,
                    ams_system = :ams_system,
                    market_state = :market_state
                WHERE id = :organization_id
            """),
            {
                "account_role": business_role,
                "company_type": company_type_value,
                "monthly_volume": monthly_volume_value,
                "primary_lines": primary_lines_value,
                "ams_system": ams_system_value,
                "market_state": market_state_value,
                "organization_id": organization.id,
            },
        )
    except Exception:
        pass

        db.commit()
        db.refresh(organization)
        new_role = "owner"
    else:
        existing_org_users = db.query(User).filter(User.organization_id == organization.id).count()
        if existing_org_users > 0:
            raise HTTPException(
                status_code=403,
                detail="This organization already exists. Ask the owner or admin to invite you.",
            )
        new_role = "owner"

    new_user = User(
        email=clean_email,
        password_hash=hash_valid_password(data.password),
        role=new_role,
        organization_id=organization.id,
        first_name=(data.first_name or "").strip(),
        last_name=(data.last_name or "").strip(),
        is_email_verified=False,
        is_active=True,
        created_at=datetime.utcnow(),
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    if new_role == "owner":
        organization.owner_user_id = new_user.id
        db.commit()

    record_audit_event(
        db,
        current_user=audit_actor(new_user),
        action="user_registered",
        resource_type="user",
        resource_id=str(new_user.id),
        details=audit_user_details(
            new_user,
            {
                "event": "public_registration",
                "organization_name": organization.name,
                "email_verification_status": "pending",
            },
        ),
        request=request,
    )

    access_token = create_access_token(new_user)

    verify_token = create_token({"sub": new_user.email, "type": "email_verify"}, VERIFY_TOKEN_EXPIRE_MINUTES)
    verify_link = f"{FRONTEND_URL}/verify-email?token={verify_token}"

    send_email(
        new_user.email,
        "Verify your LossQ email",
        email_shell(
            title="Verify your LossQ email",
            preview="Welcome to LossQ. Please verify your email address to help secure your account.",
            button_text="Verify Email",
            button_url=verify_link,
            footer_note="This verification link expires in 24 hours.",
        ),
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "session_timeout_minutes": ACCESS_TOKEN_EXPIRE_MINUTES,
        "email_verification_status": "pending",
        "user": public_user(new_user),
        "organization": {
            "id": organization.id,
            "name": organization.name,
            "user_limit": organization.user_limit,
            "owner_user_id": organization.owner_user_id,
        },
    }


@router.post("/login")
def login_user(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    clean_email = data.email.strip().lower()
    user = db.query(User).filter(User.email == clean_email).first()

    if not user or not pwd_context.verify(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not bool(user.is_active):
        raise HTTPException(status_code=403, detail="User account is disabled")

    user.last_login_at = datetime.utcnow()
    db.commit()

    record_audit_event(
        db,
        current_user=audit_actor(user),
        action="user_login",
        resource_type="user",
        resource_id=str(user.id),
        details=audit_user_details(user, {"event": "login_success"}),
        request=request,
    )

    token = create_access_token(user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "session_timeout_minutes": ACCESS_TOKEN_EXPIRE_MINUTES,
        "user": public_user(user),
    }


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    organization = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    return {
        "user": public_user(current_user),
        "organization": {
            "id": organization.id if organization else None,
            "name": organization.name if organization else "",
            "user_limit": organization.user_limit if organization else 0,
            "owner_user_id": organization.owner_user_id if organization else None,
            # LOSSQ_AUTH_ME_AGENCY_PROFILE_RESPONSE_V1
            "agency_contact_name": getattr(organization, "agency_contact_name", "") if organization else "",
            "agency_email": getattr(organization, "agency_email", "") if organization else "",
            "agency_phone": getattr(organization, "agency_phone", "") if organization else "",
            "agency_address": getattr(organization, "agency_address", "") if organization else "",
            "agency_city": getattr(organization, "agency_city", "") if organization else "",
            "agency_state": getattr(organization, "agency_state", "") if organization else "",
            "agency_zip": getattr(organization, "agency_zip", "") if organization else "",
            "agency_website": getattr(organization, "agency_website", "") if organization else "",
            "agency_license_number": getattr(organization, "agency_license_number", "") if organization else "",
            "agency_logo_url": getattr(organization, "agency_logo_url", "") if organization else "",
        },
        "session_timeout_minutes": ACCESS_TOKEN_EXPIRE_MINUTES,
    }


@router.put("/me")
def update_me(data: UpdateMeRequest, request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current_user.first_name = (data.first_name or "").strip()
    current_user.last_name = (data.last_name or "").strip()
    current_user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(current_user)

    record_audit_event(
        db,
        current_user=audit_actor(current_user),
        action="user_profile_updated",
        resource_type="user",
        resource_id=str(current_user.id),
        details=audit_user_details(current_user, {"event": "profile_updated"}),
        request=request,
    )

    return {"message": "Profile updated.", "user": public_user(current_user)}


@router.post("/change-password")
def change_password(data: ChangePasswordRequest, request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not pwd_context.verify(data.current_password, current_user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")
    current_user.password_hash = hash_valid_password(data.new_password)
    current_user.updated_at = datetime.utcnow()
    db.commit()

    record_audit_event(
        db,
        current_user=audit_actor(current_user),
        action="password_changed",
        resource_type="user",
        resource_id=str(current_user.id),
        details=audit_user_details(current_user, {"event": "password_changed"}),
        request=request,
    )

    return {"message": "Password changed successfully."}


@router.post("/verify-password")
def verify_password(data: VerifyPasswordRequest, current_user: User = Depends(get_current_user)):
    if not pwd_context.verify(data.password, current_user.password_hash):
        raise HTTPException(status_code=401, detail="Password verification failed")
    security_token = create_token({"sub": current_user.email, "user_id": current_user.id, "type": "security_check"}, 10)
    return {"verified": True, "security_token": security_token, "expires_minutes": 10}


@router.post("/invite")
def invite_user(data: InviteUserRequest, request: Request, current_user: User = Depends(require_admin_or_owner), db: Session = Depends(get_db)):
    clean_email = data.email.strip().lower()
    invite_role=public_registration_role(getattr(data, "role", None)).strip().lower()

    if invite_role not in ["admin", "user"]:
        raise HTTPException(status_code=400, detail="Invite role must be admin or user")
    if current_user.role == "admin" and invite_role == "admin":
        raise HTTPException(status_code=403, detail="Admins can only invite normal users")

    organization = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")

    existing_user = db.query(User).filter(User.email == clean_email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already belongs to a LossQ user")

    active_users = user_count_for_org(db, organization.id)
    if active_users >= int(organization.user_limit or 1):
        raise HTTPException(status_code=403, detail="User limit reached for this account")

    invite_token = create_token(
        {"sub": clean_email, "type": "invite", "organization_id": organization.id, "role": invite_role, "invited_by": current_user.id},
        INVITE_TOKEN_EXPIRE_MINUTES,
    )
    invite_link = f"{FRONTEND_URL}/accept-invite?token={invite_token}"
    send_email(
        clean_email,
        "You have been invited to LossQ",
        email_shell(
            title="You have been invited to LossQ",
            preview=f"{current_user.email} invited you to join {organization.name} on LossQ as a {invite_role}.",
            button_text="Accept Invite",
            button_url=invite_link,
            footer_note="This invite expires in 7 days. If you were not expecting this invite, you can ignore this email.",
        ),
    )

    record_audit_event(
        db,
        current_user=audit_actor(current_user),
        action="user_invited",
        resource_type="user",
        resource_id=clean_email,
        details=audit_user_details(
            current_user,
            {
                "event": "user_invited",
                "invited_email": clean_email,
                "invited_role": invite_role,
                "organization_name": organization.name,
            },
        ),
        request=request,
    )

    return {"message": "Invite created.", "invite_email": clean_email, "invite_role": invite_role, "invite_link": invite_link, "expires_minutes": INVITE_TOKEN_EXPIRE_MINUTES}


@router.post("/accept-invite")
def accept_invite(data: AcceptInviteRequest, request: Request, db: Session = Depends(get_db)):
    payload = decode_token_or_400(data.token, "invite")
    clean_email = str(payload.get("sub") or "").strip().lower()
    organization_id = payload.get("organization_id")
    role = str(payload.get("role") or "user").lower()

    if not clean_email or not organization_id:
        raise HTTPException(status_code=400, detail="Invalid invite token")
    if role not in ["admin", "user"]:
        role = "user"
    if len(data.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    organization = db.query(Organization).filter(Organization.id == organization_id).first()
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")

    existing_user = db.query(User).filter(User.email == clean_email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    active_users = user_count_for_org(db, organization.id)
    if active_users >= int(organization.user_limit or 1):
        raise HTTPException(status_code=403, detail="User limit reached for this account")

    new_user = User(
        email=clean_email,
        password_hash=hash_valid_password(data.password),
        role=role,
        organization_id=organization.id,
        first_name=(data.first_name or "").strip(),
        last_name=(data.last_name or "").strip(),
        is_email_verified=True,
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    record_audit_event(
        db,
        current_user=audit_actor(new_user),
        action="invite_accepted",
        resource_type="user",
        resource_id=str(new_user.id),
        details=audit_user_details(
            new_user,
            {
                "event": "invite_accepted",
                "accepted_email": new_user.email,
                "role": role,
            },
        ),
        request=request,
    )

    token = create_access_token(new_user)
    return {"message": "Invite accepted.", "access_token": token, "token_type": "bearer", "session_timeout_minutes": ACCESS_TOKEN_EXPIRE_MINUTES, "user": public_user(new_user)}


@router.get("/users")
def list_org_users(current_user: User = Depends(require_admin_or_owner), db: Session = Depends(get_db)):
    organization = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    # Only return active users in User Management.
    users = (
        db.query(User)
        .filter(User.organization_id == current_user.organization_id, User.is_active != False)
        .order_by(User.role.asc(), User.email.asc())
        .all()
    )
    active_users = users
    limit = int((organization.user_limit if organization else 0) or 0)
    return {
        "organization": {"id": organization.id if organization else None, "name": organization.name if organization else "", "user_limit": limit, "active_user_count": len(active_users), "remaining_users": max(limit - len(active_users), 0)},
        "users": [public_user(user) for user in users],
    }


@router.delete("/users/{user_id}")
def remove_org_user(user_id: int, request: Request, current_user: User = Depends(require_admin_or_owner), db: Session = Depends(get_db)):
    target_user = db.query(User).filter(User.id == user_id, User.organization_id == current_user.organization_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    current_role = (current_user.role or "user").lower()
    target_role = (target_user.role or "user").lower()

    if target_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot remove yourself here")
    if target_role == "owner":
        raise HTTPException(status_code=403, detail="Owner cannot be removed")
    if current_role == "admin" and target_role != "user":
        raise HTTPException(status_code=403, detail="Admins can only remove normal users")

    # LOSSQ_HARD_DELETE_ORG_USER_V1
    # Fully delete the user so they no longer appear in User Management.
    removed_email = target_user.email
    removed_role = target_user.role or "user"
    removed_name = " ".join(
        part
        for part in [target_user.first_name or "", target_user.last_name or ""]
        if str(part).strip()
    ).strip()

    db.delete(target_user)
    db.commit()

    record_audit_event(
        db,
        current_user=audit_actor(current_user),
        action="user_removed",
        resource_type="user",
        resource_id=str(user_id),
        details=audit_user_details(
            current_user,
            {
                "event": "user_removed",
                "removed_user_id": user_id,
                "removed_user_email": removed_email,
                "removed_user_full_name": removed_name,
                "removed_user_role": removed_role,
            },
        ),
        request=request,
    )

    return {"message": f"{removed_email} was deleted from the account.", "deleted_user_id": user_id}


@router.post("/forgot-password")
def forgot_password(data: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    clean_email = data.email.strip().lower()
    user = db.query(User).filter(User.email == clean_email).first()
    if not user:
        return {"message": "If an account exists, a reset email has been sent."}

    reset_token = create_token({"sub": user.email, "type": "password_reset"}, RESET_TOKEN_EXPIRE_MINUTES)
    reset_link = f"{FRONTEND_URL}/reset-password?token={reset_token}"
    send_email(
        user.email,
        "Reset your LossQ password",
        email_shell(
            title="Reset your LossQ password",
            preview="We received a request to reset your LossQ password. This link expires in 30 minutes.",
            button_text="Reset Password",
            button_url=reset_link,
            footer_note="If you did not request a password reset, you can ignore this email.",
        ),
    )
    record_audit_event(
        db,
        current_user=audit_actor(user),
        action="password_reset_requested",
        resource_type="user",
        resource_id=str(user.id),
        details=audit_user_details(user, {"event": "password_reset_requested"}),
        request=request,
    )

    return {"message": "If an account exists, a reset email has been sent."}


@router.post("/reset-password")
def reset_password(data: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    payload = decode_token_or_400(data.token, "password_reset")
    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=400, detail="Invalid reset token")
    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.password_hash = hash_valid_password(data.new_password)
    user.updated_at = datetime.utcnow()
    db.commit()

    record_audit_event(
        db,
        current_user=audit_actor(user),
        action="password_reset_completed",
        resource_type="user",
        resource_id=str(user.id),
        details=audit_user_details(user, {"event": "password_reset_completed"}),
        request=request,
    )

    return {"message": "Password reset successful. You can now log in."}


@router.get("/verify-email")
def verify_email(token: str, request: Request, db: Session = Depends(get_db)):
    payload = decode_token_or_400(token, "email_verify")
    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=400, detail="Invalid verification token")
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_email_verified = True
    user.updated_at = datetime.utcnow()
    db.commit()

    record_audit_event(
        db,
        current_user=audit_actor(user),
        action="email_verified",
        resource_type="user",
        resource_id=str(user.id),
        details=audit_user_details(user, {"event": "email_verified"}),
        request=request,
    )

    return {"message": "Email verified successfully.", "email": email, "status": "verified"}


@router.get("/validate")
def validate_token(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    user = get_current_user(credentials=credentials, db=db)
    return {"valid": True, "user": public_user(user), "session_timeout_minutes": ACCESS_TOKEN_EXPIRE_MINUTES}


@router.post("/bootstrap-owner")
def bootstrap_owner(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    allowed_owner_email = os.getenv("LOSSQ_OWNER_EMAIL", "tmckenzie49@gmail.com").strip().lower()
    current_email = (current_user.email or "").strip().lower()

    if current_email != allowed_owner_email:
        raise HTTPException(status_code=403, detail="This account is not allowed to become owner")

    organization = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")

    current_user.role = "owner"
    current_user.is_active = True
    current_user.updated_at = datetime.utcnow()
    organization.owner_user_id = current_user.id
    organization.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(current_user)
    db.refresh(organization)

    record_audit_event(
        db,
        current_user=audit_actor(current_user),
        action="owner_bootstrapped",
        resource_type="user",
        resource_id=str(current_user.id),
        details=audit_user_details(
            current_user,
            {
                "event": "owner_bootstrapped",
                "organization_name": organization.name,
                "owner_user_id": organization.owner_user_id,
            },
        ),
        request=request,
    )

    return {
        "message": "Owner account confirmed.",
        "user": public_user(current_user),
        "organization": {
            "id": organization.id,
            "name": organization.name,
            "user_limit": organization.user_limit,
            "owner_user_id": organization.owner_user_id,
        },
        "note": "Log out and log back in so your new owner role is included in your token.",
    }


# LOSSQ_AGENCY_PROFILE_API_V1
AGENCY_PROFILE_FIELDS = [
    "agency_contact_name",
    "agency_email",
    "agency_phone",
    "agency_address",
    "agency_city",
    "agency_state",
    "agency_zip",
    "agency_website",
    "agency_license_number",
    "agency_logo_url",
]


class AgencyProfileUpdateRequest(BaseModel):
    agency_contact_name: str | None = None
    agency_email: str | None = None
    agency_phone: str | None = None
    agency_address: str | None = None
    agency_city: str | None = None
    agency_state: str | None = None
    agency_zip: str | None = None
    agency_website: str | None = None
    agency_license_number: str | None = None
    agency_logo_url: str | None = None


def clean_agency_profile_value(value):
    if value is None:
        return None

    clean = str(value).strip()
    return clean[:500] if clean else None


def agency_profile_payload(organization, current_user=None):
    current_user = current_user or None

    fallback_email = ""
    if current_user is not None:
        fallback_email = getattr(current_user, "email", "") or ""

    if not organization:
        return {
            "organization_id": None,
            "organization_name": "",
            "agency_name": "",
            "agency_contact_name": "",
            "agency_email": fallback_email,
            "agency_phone": "",
            "agency_address": "",
            "agency_city": "",
            "agency_state": "",
            "agency_zip": "",
            "agency_website": "",
            "agency_license_number": "",
            "agency_logo_url": "",
        }

    return {
        "organization_id": getattr(organization, "id", None),
        "organization_name": getattr(organization, "name", "") or "",
        "agency_name": getattr(organization, "name", "") or "",
        "agency_contact_name": getattr(organization, "agency_contact_name", "") or "",
        "agency_email": getattr(organization, "agency_email", "") or fallback_email,
        "agency_phone": getattr(organization, "agency_phone", "") or "",
        "agency_address": getattr(organization, "agency_address", "") or "",
        "agency_city": getattr(organization, "agency_city", "") or "",
        "agency_state": getattr(organization, "agency_state", "") or "",
        "agency_zip": getattr(organization, "agency_zip", "") or "",
        "agency_website": getattr(organization, "agency_website", "") or "",
        "agency_license_number": getattr(organization, "agency_license_number", "") or "",
        "agency_logo_url": getattr(organization, "agency_logo_url", "") or "",
    }


@router.get("/agency-profile")
def get_agency_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    organization = (
        db.query(Organization)
        .filter(Organization.id == current_user.organization_id)
        .first()
    )

    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found.")

    return agency_profile_payload(organization, current_user)


@router.put("/agency-profile")
def update_agency_profile(
    data: AgencyProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    role = str(getattr(current_user, "role", "") or "").lower()

    if role not in {"owner", "admin"}:
        raise HTTPException(
            status_code=403,
            detail="Only an Owner or Admin can update agency profile information.",
        )

    organization = (
        db.query(Organization)
        .filter(Organization.id == current_user.organization_id)
        .first()
    )

    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found.")

    values = data.dict(exclude_unset=True)

    for field in AGENCY_PROFILE_FIELDS:
        if field in values:
            setattr(organization, field, clean_agency_profile_value(values.get(field)))

    organization.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(organization)

    return {
        "message": "Agency profile updated.",
        "agency_profile": agency_profile_payload(organization, current_user),
    }


# LOSSQ_ORG_SCOPED_SUPPORT_LOOKUP_V1
@router.get("/support-lookup")
def organization_support_lookup(
    query: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Organization-scoped support lookup.

    This endpoint intentionally does NOT search globally.
    It only returns users and company information for the logged-in user's organization.
    """
    clean_query = str(query or "").strip()
    clean_lower = clean_query.lower()
    query_digits = "".join(ch for ch in clean_query if ch.isdigit())

    org_id = getattr(current_user, "organization_id", None)

    if not org_id:
        return {
            "organizations": [],
            "organization_count": 0,
            "scope": "organization",
            "message": "No organization found for this user.",
        }

    if not clean_query:
        return {
            "organizations": [],
            "organization_count": 0,
            "scope": "organization",
            "message": "Enter a phone number, email, company name, contact name, or organization ID.",
        }

    organization = (
        db.query(Organization)
        .filter(Organization.id == org_id)
        .first()
    )

    users = (
        db.query(User)
        .filter(User.organization_id == org_id)
        .order_by(User.created_at.desc())
        .all()
    )

    def value_of(obj, field):
        return str(getattr(obj, field, "") or "").strip()

    def digits_of(value):
        return "".join(ch for ch in str(value or "") if ch.isdigit())

    def matches_text(value):
        if not clean_lower:
            return False
        return clean_lower in str(value or "").lower()

    def matches_digits(value):
        if not query_digits:
            return False
        return query_digits in digits_of(value)

    org_match = False

    if organization:
        org_fields = [
            "id",
            "name",
            "agency_contact_name",
            "agency_email",
            "agency_phone",
            "agency_address",
            "agency_city",
            "agency_state",
            "agency_zip",
            "agency_website",
            "agency_license_number",
        ]

        for field in org_fields:
            org_value = value_of(organization, field)
            if matches_text(org_value) or matches_digits(org_value):
                org_match = True
                break

    matched_users = []

    for user in users:
        user_fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "role",
        ]

        full_name = f"{value_of(user, 'first_name')} {value_of(user, 'last_name')}".strip()

        user_match = matches_text(full_name)

        for field in user_fields:
            user_value = value_of(user, field)
            if matches_text(user_value) or matches_digits(user_value):
                user_match = True
                break

        if user_match:
            matched_users.append({
                "id": getattr(user, "id", None),
                "email": getattr(user, "email", ""),
                "first_name": getattr(user, "first_name", ""),
                "last_name": getattr(user, "last_name", ""),
                "role": getattr(user, "role", "user"),
                "organization_id": getattr(user, "organization_id", None),
                "is_email_verified": getattr(user, "is_email_verified", False),
                "is_active": getattr(user, "is_active", True),
                "created_at": str(getattr(user, "created_at", "") or ""),
            })

    # If the company matches, show the company and all users in that company.
    # If only users match, show the company with only those matched users.
    if org_match:
        matched_users = [
            {
                "id": getattr(user, "id", None),
                "email": getattr(user, "email", ""),
                "first_name": getattr(user, "first_name", ""),
                "last_name": getattr(user, "last_name", ""),
                "role": getattr(user, "role", "user"),
                "organization_id": getattr(user, "organization_id", None),
                "is_email_verified": getattr(user, "is_email_verified", False),
                "is_active": getattr(user, "is_active", True),
                "created_at": str(getattr(user, "created_at", "") or ""),
            }
            for user in users
        ]

    if not org_match and not matched_users:
        return {
            "organizations": [],
            "organization_count": 0,
            "scope": "organization",
            "message": "No matching users found inside your organization.",
        }

    org_payload = {
        "id": getattr(organization, "id", org_id) if organization else org_id,
        "name": getattr(organization, "name", "") if organization else "",
        "organization_name": getattr(organization, "name", "") if organization else "",
        "agency_contact_name": getattr(organization, "agency_contact_name", "") if organization else "",
        "agency_email": getattr(organization, "agency_email", "") if organization else "",
        "agency_phone": getattr(organization, "agency_phone", "") if organization else "",
        "agency_address": getattr(organization, "agency_address", "") if organization else "",
        "agency_city": getattr(organization, "agency_city", "") if organization else "",
        "agency_state": getattr(organization, "agency_state", "") if organization else "",
        "agency_zip": getattr(organization, "agency_zip", "") if organization else "",
        "agency_website": getattr(organization, "agency_website", "") if organization else "",
        "agency_license_number": getattr(organization, "agency_license_number", "") if organization else "",
        "plan": getattr(organization, "plan", "") if organization else "",
        "subscription_status": getattr(organization, "subscription_status", "") if organization else "",
        "users": matched_users,
        "user_count": len(matched_users),
        "scope": "organization",
    }

    return {
        "organizations": [org_payload],
        "organization_count": 1,
        "scope": "organization",
    }

