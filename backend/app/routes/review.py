from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.claim import Claim
from app.role_utils import require_permission
from app.services.audit import record_audit_event
from app.services.review_confirmation import prepare_review_confirmation
from app.routes.upload import normalize_claim_data
from app.routes.upload_v2 import force_save_account_profile_v2


router = APIRouter(prefix="/review", tags=["Extraction Review"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/confirm")
def confirm_reviewed_extraction(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("upload")),
):
    """Persist a human-reviewed extraction as one organization-scoped transaction."""

    try:
        prepared = prepare_review_confirmation(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    claim_columns = {column.name for column in Claim.__table__.columns}
    confirmed_at = datetime.now(timezone.utc).isoformat()
    organization_id = current_user["organization_id"]
    validation = dict(payload.get("validation") or {})
    validation.update(
        {
            "manual_review_confirmed": True,
            "manual_review_confirmed_at": confirmed_at,
            "manual_review_warning_count": len(prepared.warnings),
            "manual_review_warnings": list(prepared.warnings),
            "requires_review": False,
            "extraction_status": "human_verified",
        }
    )
    prepared.profile["validation"] = validation

    try:
        saved_profile = force_save_account_profile_v2(
            db, profile_data=prepared.profile, current_user=current_user
        )
        if saved_profile is None:
            raise ValueError("The reviewed account profile could not be saved.")

        deleted_claims = (
            db.query(Claim)
            .filter(
                Claim.organization_id == organization_id,
                func.upper(func.trim(Claim.policy_number)).in_(prepared.policy_numbers),
            )
            .delete(synchronize_session=False)
        )
        db.flush()

        saved_claims = []
        for claim in prepared.claims:
            normalized = normalize_claim_data(
                raw=claim,
                fallback_policy_number=claim["policy_number"],
                current_user=current_user,
            )
            safe_claim = {key: value for key, value in normalized.items() if key in claim_columns}
            safe_claim["organization_id"] = organization_id
            safe_claim["uploaded_by_user_id"] = current_user.get("user_id")
            safe_claim["uploaded_at"] = confirmed_at
            safe_claim["claim_number"] = claim["claim_number"]
            safe_claim["policy_number"] = claim["policy_number"]

            row = Claim(**safe_claim)
            db.add(row)
            db.flush()
            saved_claims.append(
                {
                    "id": row.id,
                    "claim_number": row.claim_number,
                    "policy_number": row.policy_number,
                    "status": row.status,
                    "paid_amount": row.paid_amount,
                    "reserve_amount": row.reserve_amount,
                    "total_incurred": row.total_incurred,
                }
            )

        db.commit()
        db.refresh(saved_profile)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Reviewed extraction could not be saved. No claim changes were committed.",
        ) from exc

    record_audit_event(
        db,
        current_user=current_user,
        action="loss_run_review_confirmed",
        resource_type="account_profile",
        resource_id=prepared.profile["policy_number"],
        details={
            "source": payload.get("source") or "manual_review",
            "policy_numbers": list(prepared.policy_numbers),
            "claims_saved": len(saved_claims),
            "claims_replaced": deleted_claims,
            "warnings_acknowledged": list(prepared.warnings),
            "confirmed_at": confirmed_at,
        },
    )

    return {
        "message": "Reviewed extraction confirmed and saved.",
        "status": "human_verified",
        "policy_number": prepared.profile["policy_number"],
        "policy_numbers": list(prepared.policy_numbers),
        "claims_saved": len(saved_claims),
        "claims_replaced": deleted_claims,
        "warnings_acknowledged": list(prepared.warnings),
        "profile_id": getattr(saved_profile, "id", None),
        "claims": saved_claims,
    }
