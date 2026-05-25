import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from jose import jwt
from pydantic import BaseModel

from app.database import SessionLocal
from app.models.user import User
from app.models.organization import Organization

load_dotenv()

router = APIRouter(prefix="/auth", tags=["Auth"])

SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key-later")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

class RegisterRequest(BaseModel):
    email: str
    password: str
    organization_name: str

class LoginRequest(BaseModel):
    email: str
    password: str

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

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

    return {"access_token": token, "token_type": "bearer", "user": {
        "id": new_user.id,
        "email": new_user.email,
        "organization_id": new_user.organization_id,
    }}

@router.post("/login")
def login_user(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()

    if not user or not pwd_context.verify(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token({
        "sub": user.email,
        "user_id": user.id,
        "role": user.role,
        "organization_id": user.organization_id,
    })

    return {"access_token": token, "token_type": "bearer", "user": {
        "id": user.id,
        "email": user.email,
        "organization_id": user.organization_id,
    }}