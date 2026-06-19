import os
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy import text

from app.database import SessionLocal
from app.models.user import User
from app.services.audit import record_audit_event

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable is required")
ALGORITHM = "HS256"

security = HTTPBearer()


# LOSSQ_SINGLE_ACTIVE_SESSION_AUTH_UTILS_V1
def ensure_single_session_columns(db):
    """
    Defensive schema guard for live deployments.
    This makes sure auth_utils can enforce session checks even if a protected
    route is hit before the auth route runs its own schema repair.
    """
    statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS active_session_id VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS active_session_started_at TIMESTAMP",
    ]

    for statement in statements:
        try:
            db.execute(text(statement))
            db.commit()
        except Exception:
            db.rollback()


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = payload.get("user_id")
    email = payload.get("sub")
    token_session_id = payload.get("session_id")

    db = SessionLocal()
    try:
        ensure_single_session_columns(db)

        query = db.query(User)
        user = None

        if user_id:
            user = query.filter(User.id == user_id).first()

        if not user and email:
            user = query.filter(User.email == email).first()

        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        if not bool(getattr(user, "is_active", True)):
            raise HTTPException(status_code=403, detail="User account is disabled")

        active_session_id = getattr(user, "active_session_id", None)

        # Backward-compatible for users who have not logged in since deployment.
        if active_session_id:
            if not token_session_id or str(token_session_id) != str(active_session_id):
                # LOSSQ_SINGLE_SESSION_AUTH_UTILS_AUDIT_REJECTED_V1
                try:
                    record_audit_event(
                        db,
                        current_user={
                            "email": user.email,
                            "user_id": user.id,
                            "role": user.role,
                            "organization_id": user.organization_id,
                        },
                        action="single_session_rejected",
                        resource_type="user_session",
                        resource_id=str(user.id),
                        details={
                            "event": "old_session_rejected",
                            "reason": "account_signed_in_elsewhere",
                            "token_session_present": bool(token_session_id),
                        },
                    )
                except Exception as exc:
                    print("LOSSQ_SINGLE_SESSION_AUTH_UTILS_AUDIT_REJECTED_ERROR:", str(exc)[:300])

                raise HTTPException(
                    status_code=401,
                    detail="Session expired because this account was signed in somewhere else.",
                )

        return {
            "email": user.email,
            "user_id": user.id,
            "role": user.role,
            "organization_id": user.organization_id,
            "session_id": active_session_id,
        }
    finally:
        db.close()
