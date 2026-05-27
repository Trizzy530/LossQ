import os
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

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

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


def create_token(data: dict, expires_minutes: int):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(data: dict):
    return create_token(data, ACCESS_TOKEN_EXPIRE_MINUTES)


@router.post("/register")
def register_user(data: RegisterRequest, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == data.email).first()

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
        email=data.email,
        password_hash=pwd_context.hash(data.password),
        role="user",
        organization_id=organization.id,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    token = create_access_token({
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

    return {
        "access_token": token,
        "token_type": "bearer",
        "email_verification_status": "pending",
        "verification_link_placeholder": verify_link,
        "user": {
            "id": new_user.id,
            "email": new_user.email,
            "organization_id": new_user.organization_id,
        },
    }


@router.post("/login")
def login_user(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()

    if not user or not pwd_context.verify(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

if not user.email_verified:
    raise HTTPException(
        status_code=403,
        detail="Please verify your email before accessing LossQ"
    )

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
    user = db.query(User).filter(User.email == data.email).first()

    if not user:
        return {
            "message": "If an account exists, a reset link will be sent."
        }

    reset_token = create_token(
        {"sub": user.email, "type": "password_reset"},
        RESET_TOKEN_EXPIRE_MINUTES,
    )

    reset_link = f"{FRONTEND_URL}/reset-password?token={reset_token}"

    return {
        "message": "Password reset link generated.",
        "reset_link_placeholder": reset_link,
    }


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

    user = db.query(User).filter(User.email == email).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    user.password_hash = pwd_context.hash(data.new_password)

    db.commit()

    return {"message": "Password reset successful. You can now log in."}


@router.get("/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        token_type = payload.get("type")

        if token_type != "email_verify" or not email:
            raise HTTPException(status_code=400, detail="Invalid verification token")

    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    user = db.query(User).filter(User.email == email).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.email_verified = True
user.onboarding_status = "active"

db.commit()

return {
    "message": "Email verified successfully.",
    "email": email,
    "status": "verified",
}