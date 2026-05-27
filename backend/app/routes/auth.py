import os
import resend
from dotenv import load_dotenv
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from jose import jwt, JWTError
from pydantic import BaseModel

from app.database import SessionLocal
from app.models.user import User
from app.models.organization import Organization

load_dotenv()

router = APIRouter(prefix="/auth", tags=["Auth"])

SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key-later")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440
RESET_TOKEN_EXPIRE_MINUTES = 30
VERIFY_TOKEN_EXPIRE_MINUTES = 1440

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://loss-q.vercel.app")
FROM_EMAIL = os.getenv("FROM_EMAIL", "LossQ <onboarding@resend.dev>")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


class RegisterRequest(BaseModel):
    email: str
    password: str
    organization_name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_token(data: dict, minutes: int):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(data: dict):
    return create_token(data, ACCESS_TOKEN_EXPIRE_MINUTES)


def send_email(to: str, subject: str, html: str):
    if not RESEND_API_KEY:
        return {"sent": False, "reason": "RESEND_API_KEY missing"}

    try:
        return resend.Emails.send({
            "from": FROM_EMAIL,
            "to": [to],
            "subject": subject,
            "html": html,
        })
    except Exception as e:
        return {"sent": False, "reason": str(e)}


@router.post("/register")
def register_user(data: RegisterRequest, db: Session = Depends(get_db)):
    clean_email = data.email.strip().lower()

    existing_user = db.query(User).filter(User.email == clean_email).first()

    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    organization = db.query(Organization).filter(
        Organization.name == data.organization_name
    ).first()

    if not organization:
        organization = Organization(name=data.organization_name)
        db.add(organization)
        db.commit()
        db.refresh(organization)

    new_user = User(
        email=clean_email,
        password_hash=pwd_context.hash(data.password),
        role="user",
        organization_id=organization.id,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    access_token = create_access_token({
        "sub": new_user.email,
        "user_id": new_user.id,
        "role": new_user.role,
        "organization_id": new_user.organization_id,
    })

    verify_token = create_token(
        {"sub": new_user.email, "type": "email_verify"},
        VERIFY_TOKEN_EXPIRE_MINUTES,
    )

    verify_link = f"{FRONTEND_URL}/verify-email?token={verify_token}"

    send_email(
        to=new_user.email,
        subject="Verify your LossQ email",
        html=f"""
        <div style="font-family:Arial,sans-serif;line-height:1.6">
          <h2>Welcome to LossQ</h2>
          <p>Please verify your email to finish securing your account.</p>
          <p>
            <a href="{verify_link}" style="background:#2563eb;color:white;padding:12px 18px;border-radius:8px;text-decoration:none;">
              Verify Email
            </a>
          </p>
          <p>If the button does not work, copy this link:</p>
          <p>{verify_link}</p>
        </div>
        """,
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "email_verification_status": "pending",
        "user": {
            "id": new_user.id,
            "email": new_user.email,
            "organization_id": new_user.organization_id,
        },
    }


@router.post("/login")
def login_user(data: LoginRequest, db: Session = Depends(get_db)):
    clean_email = data.email.strip().lower()

    user = db.query(User).filter(User.email == clean_email).first()

    if not user or not pwd_context.verify(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token({
        "sub": user.email,
        "user_id": user.id,
        "role": user.role,
        "organization_id": user.organization_id,
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "organization_id": user.organization_id,
        },
    }


@router.post("/forgot-password")
def forgot_password(data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    clean_email = data.email.strip().lower()

    user = db.query(User).filter(User.email == clean_email).first()

    if not user:
        return {"message": "If an account exists, a reset email has been sent."}

    reset_token = create_token(
        {"sub": user.email, "type": "password_reset"},
        RESET_TOKEN_EXPIRE_MINUTES,
    )

    reset_link = f"{FRONTEND_URL}/reset-password?token={reset_token}"

    send_email(
        to=user.email,
        subject="Reset your LossQ password",
        html=f"""
        <div style="font-family:Arial,sans-serif;line-height:1.6">
          <h2>Reset your LossQ password</h2>
          <p>This link expires in 30 minutes.</p>
          <p>
            <a href="{reset_link}" style="background:#2563eb;color:white;padding:12px 18px;border-radius:8px;text-decoration:none;">
              Reset Password
            </a>
          </p>
          <p>If the button does not work, copy this link:</p>
          <p>{reset_link}</p>
        </div>
        """,
    )

    return {"message": "If an account exists, a reset email has been sent."}


@router.post("/reset-password")
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(data.token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        token_type = payload.get("type")

        if token_type != "password_reset" or not email:
            raise HTTPException(status_code=400, detail="Invalid reset token")

    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    user = db.query(User).filter(User.email == email).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password_hash = pwd_context.hash(data.new_password)
    db.commit()

    return {"message": "Password reset successful. You can now log in."}


@router.get("/verify-email")
def verify_email(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        token_type = payload.get("type")

        if token_type != "email_verify" or not email:
            raise HTTPException(status_code=400, detail="Invalid verification token")

    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    return {
        "message": "Email verified successfully.",
        "email": email,
        "status": "verified",
    }