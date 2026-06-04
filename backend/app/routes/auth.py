import os
# import resend
from datetime import datetime, timedelta
from typing import Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.organization import Organization
from app.models.user import User

load_dotenv()

router = APIRouter(prefix="/auth", tags=["Auth"])

SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key-later")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
RESET_TOKEN_EXPIRE_MINUTES = 30
VERIFY_TOKEN_EXPIRE_MINUTES = 1440
INVITE_TOKEN_EXPIRE_MINUTES = 10080

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://lossq.com").rstrip("/")
FROM_EMAIL = os.getenv("FROM_EMAIL", "LossQ <onboarding@resend.dev>")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
security = HTTPBearer()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    organization_name: str
    first_name: Optional[str] = ""
    last_name: Optional[str] = ""


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
    print(f"EMAIL DEBUG -> TO: {to} | SUBJECT: {subject}")
    print(html)
    return {"sent": True}


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


@router.post("/register")
def register_user(data: RegisterRequest, db: Session = Depends(get_db)):
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
        password_hash=pwd_context.hash(data.password),
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

    access_token = create_access_token(new_user)

    verify_token = create_token({"sub": new_user.email, "type": "email_verify"}, VERIFY_TOKEN_EXPIRE_MINUTES)
    verify_link = f"{FRONTEND_URL}/verify-email?token={verify_token}"

    send_email(new_user.email, "Verify your LossQ email", f"Verify your email: {verify_link}")

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
def login_user(data: LoginRequest, db: Session = Depends(get_db)):
    clean_email = data.email.strip().lower()
    user = db.query(User).filter(User.email == clean_email).first()

    if not user or not pwd_context.verify(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not bool(user.is_active):
        raise HTTPException(status_code=403, detail="User account is disabled")

    user.last_login_at = datetime.utcnow()
    db.commit()

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
        },
        "session_timeout_minutes": ACCESS_TOKEN_EXPIRE_MINUTES,
    }


@router.put("/me")
def update_me(data: UpdateMeRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current_user.first_name = (data.first_name or "").strip()
    current_user.last_name = (data.last_name or "").strip()
    current_user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(current_user)
    return {"message": "Profile updated.", "user": public_user(current_user)}


@router.post("/change-password")
def change_password(data: ChangePasswordRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not pwd_context.verify(data.current_password, current_user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")
    current_user.password_hash = pwd_context.hash(data.new_password)
    current_user.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Password changed successfully."}


@router.post("/verify-password")
def verify_password(data: VerifyPasswordRequest, current_user: User = Depends(get_current_user)):
    if not pwd_context.verify(data.password, current_user.password_hash):
        raise HTTPException(status_code=401, detail="Password verification failed")
    security_token = create_token({"sub": current_user.email, "user_id": current_user.id, "type": "security_check"}, 10)
    return {"verified": True, "security_token": security_token, "expires_minutes": 10}


@router.post("/invite")
def invite_user(data: InviteUserRequest, current_user: User = Depends(require_admin_or_owner), db: Session = Depends(get_db)):
    clean_email = data.email.strip().lower()
    invite_role = (data.role or "user").strip().lower()

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
    send_email(clean_email, "You have been invited to LossQ", f"Accept invite: {invite_link}")

    return {"message": "Invite created.", "invite_email": clean_email, "invite_role": invite_role, "invite_link": invite_link, "expires_minutes": INVITE_TOKEN_EXPIRE_MINUTES}


@router.post("/accept-invite")
def accept_invite(data: AcceptInviteRequest, db: Session = Depends(get_db)):
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
        password_hash=pwd_context.hash(data.password),
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

    token = create_access_token(new_user)
    return {"message": "Invite accepted.", "access_token": token, "token_type": "bearer", "session_timeout_minutes": ACCESS_TOKEN_EXPIRE_MINUTES, "user": public_user(new_user)}


@router.get("/users")
def list_org_users(current_user: User = Depends(require_admin_or_owner), db: Session = Depends(get_db)):
    organization = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    users = db.query(User).filter(User.organization_id == current_user.organization_id).order_by(User.role.asc(), User.email.asc()).all()
    active_users = [user for user in users if bool(user.is_active)]
    limit = int((organization.user_limit if organization else 0) or 0)
    return {
        "organization": {"id": organization.id if organization else None, "name": organization.name if organization else "", "user_limit": limit, "active_user_count": len(active_users), "remaining_users": max(limit - len(active_users), 0)},
        "users": [public_user(user) for user in users],
    }


@router.delete("/users/{user_id}")
def remove_org_user(user_id: int, current_user: User = Depends(require_admin_or_owner), db: Session = Depends(get_db)):
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

    target_user.is_active = False
    target_user.updated_at = datetime.utcnow()
    db.commit()
    return {"message": f"{target_user.email} was removed from the account.", "removed_user": public_user(target_user)}


@router.post("/forgot-password")
def forgot_password(data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    clean_email = data.email.strip().lower()
    user = db.query(User).filter(User.email == clean_email).first()
    if not user:
        return {"message": "If an account exists, a reset email has been sent."}

    reset_token = create_token({"sub": user.email, "type": "password_reset"}, RESET_TOKEN_EXPIRE_MINUTES)
    reset_link = f"{FRONTEND_URL}/reset-password?token={reset_token}"
    send_email(user.email, "Reset your LossQ password", f"Reset password: {reset_link}")
    return {"message": "If an account exists, a reset email has been sent."}


@router.post("/reset-password")
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    payload = decode_token_or_400(data.token, "password_reset")
    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=400, detail="Invalid reset token")
    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.password_hash = pwd_context.hash(data.new_password)
    user.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Password reset successful. You can now log in."}


@router.get("/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):
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
    return {"message": "Email verified successfully.", "email": email, "status": "verified"}


@router.get("/validate")
def validate_token(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    user = get_current_user(credentials=credentials, db=db)
    return {"valid": True, "user": public_user(user), "session_timeout_minutes": ACCESS_TOKEN_EXPIRE_MINUTES}


@router.post("/bootstrap-owner")
def bootstrap_owner(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
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


@router.get("/debug-auth-version")
def debug_auth_version():
    return {
        "auth_version": "owner-admin-invite-security-v1",
        "features": ["owner account", "admin invites", "admin can remove users", "owner can remove admins and users", "user limit per account", "password reset", "email verification", "24 hour token timeout"],
    }
