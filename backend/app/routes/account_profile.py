from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text, inspect, func

from app.database import SessionLocal
from app.auth_utils import get_current_user
from app.models.account_profile import AccountProfile
from app.models.claim import Claim

router = APIRouter(prefix="/account-profile", tags=["Account Profile"])


class AccountProfileUpdate(BaseModel):
    business_name: str
    carrier_name: str
    agency_name: str
    policy_number: str
    effective_date: str
    expiration_date: str
    evaluation_date: str


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/")
def get_default_profile(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):

    ensure_account_profile_columns(db)


    profile = (
        db.query(AccountProfile)
        .filter(AccountProfile.organization_id == current_user["organization_id"])
        .order_by(AccountProfile.id.desc())
        .first()
    )

    if not profile:
        return {
            "business_name": "",
            "carrier_name": "",
            "agency_name": "",
            "policy_number": "",
            "effective_date": "",
            "expiration_date": "",
            "evaluation_date": "",
        }

    return profile


@router.get("/blank")
def blank_profile():
    return {
        "business_name": "",
        "carrier_name": "",
        "agency_name": "",
        "policy_number": "",
        "effective_date": "",
        "expiration_date": "",
        "evaluation_date": "",
    }


@router.get("/all")
def get_all_profiles(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # Saved Carrier Profiles should only show real saved account profiles.
    # Do not list every policy number found in old claim rows, because that pollutes
    # the dropdown with stale uploads and header/parser artifacts.
    return (
        db.query(AccountProfile)
        .filter(AccountProfile.organization_id == current_user["organization_id"])
        .order_by(AccountProfile.id.desc())
        .all()
    )


@router.get("/policy/{policy_number}")
def get_profile_by_policy(
    policy_number: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    normalized_policy_number = str(policy_number or "").strip().upper()

    profile = (
        db.query(AccountProfile)
        .filter(
            AccountProfile.organization_id == current_user["organization_id"],
            func.upper(AccountProfile.policy_number) == normalized_policy_number,
        )
        .first()
    )

    if not profile:
        claims = (
            db.query(Claim)
            .filter(
                Claim.organization_id == current_user["organization_id"],
                func.upper(Claim.policy_number) == normalized_policy_number,
            )
            .all()
        )

        if not claims:
            raise HTTPException(status_code=404, detail="Policy number not found")

        total_paid = sum(float(claim.paid_amount or 0) for claim in claims)
        total_reserve = sum(float(claim.reserve_amount or 0) for claim in claims)
        total_incurred = sum(float(claim.total_incurred or 0) for claim in claims)
        open_claims = len([claim for claim in claims if str(claim.status or "").lower() == "open"])
        closed_claims = len([claim for claim in claims if str(claim.status or "").lower() == "closed"])

        return {
            "business_name": "",
            "carrier_name": "Carrier Not Set",
            "writing_carrier": "Carrier Not Set",
            "agency_name": "",
            "account_number": "",
            "customer_number": "",
            "producer_number": "",
            "policy_number": normalized_policy_number,
            "effective_date": "",
            "expiration_date": "",
            "evaluation_date": "",
            "profile_source": "claims_fallback",
            "claim_count": len(claims),
            "open_claims": open_claims,
            "closed_claims": closed_claims,
            "total_paid": total_paid,
            "total_reserve": total_reserve,
            "total_incurred": total_incurred,
        }

    return profile

def ensure_account_profile_columns(db: Session):
    required_columns = {
        "writing_carrier": "VARCHAR",
        "account_number": "VARCHAR",
        "customer_number": "VARCHAR",
        "producer_number": "VARCHAR",
        "policies": "TEXT",
        "validation": "TEXT",
        "raw_text_preview": "TEXT",
    }

    try:
        inspector = inspect(db.bind)
        existing_columns = [
            column["name"] for column in inspector.get_columns("account_profiles")
        ]

        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                db.execute(
                    text(
                        f"ALTER TABLE account_profiles ADD COLUMN {column_name} {column_type}"
                    )
                )

        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Account profile column check failed: {e}")


@router.put("/")
def upsert_account_profile(
    payload: AccountProfileUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    profile = (
        db.query(AccountProfile)
        .filter(
            AccountProfile.organization_id == current_user["organization_id"],
            AccountProfile.policy_number == payload.policy_number,
        )
        .first()
    )

    if not profile:
        profile = AccountProfile(organization_id=current_user["organization_id"])
        db.add(profile)

    profile.business_name = payload.business_name
    profile.carrier_name = payload.carrier_name
    profile.agency_name = payload.agency_name
    profile.policy_number = payload.policy_number
    profile.effective_date = payload.effective_date
    profile.expiration_date = payload.expiration_date
    profile.evaluation_date = payload.evaluation_date

    db.commit()
    db.refresh(profile)

    return profile

@router.delete("/cleanup-placeholder-profiles")
def cleanup_placeholder_profiles(
    keep_policy_numbers: str = "",
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    keep_set = {
        item.strip().upper()
        for item in str(keep_policy_numbers or "").split(",")
        if item.strip()
    }

    business_placeholders = {
        "",
        "business name not set",
        "unnamed business",
        "not set",
        "none",
        "null",
    }

    carrier_placeholders = {
        "",
        "carrier not set",
        "business name not set",
        "unnamed business",
        "not set",
        "none",
        "null",
    }

    profiles = (
        db.query(AccountProfile)
        .filter(AccountProfile.organization_id == current_user["organization_id"])
        .all()
    )

    deleted_policy_numbers = []

    for profile in profiles:
        policy_number = str(profile.policy_number or "").strip().upper()
        business_name = str(profile.business_name or "").strip().lower()
        carrier_name = str(
            profile.carrier_name or profile.writing_carrier or ""
        ).strip().lower()

        if policy_number in keep_set:
            continue

        is_placeholder_business = business_name in business_placeholders
        is_placeholder_carrier = carrier_name in carrier_placeholders

        if is_placeholder_business and is_placeholder_carrier:
            deleted_policy_numbers.append(policy_number)
            db.delete(profile)

    db.commit()

    return {
        "message": "Placeholder carrier profiles cleaned.",
        "deleted_count": len(deleted_policy_numbers),
        "deleted_policy_numbers": deleted_policy_numbers[:200],
        "kept_policy_numbers": sorted(list(keep_set)),
    }


@router.delete("/delete")
def delete_account_profile_by_query(
    policy_number: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    normalized_policy_number = str(policy_number or "").strip().upper()

    profile = (
        db.query(AccountProfile)
        .filter(
            AccountProfile.organization_id == current_user["organization_id"],
            func.upper(AccountProfile.policy_number) == normalized_policy_number,
        )
        .first()
    )

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    db.delete(profile)
    db.commit()

    return {
        "message": "Profile deleted",
        "policy_number": normalized_policy_number,
    }

@router.delete("/{policy_number}")
def delete_profile(
    policy_number: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    normalized_policy_number = str(policy_number or "").strip().upper()

    profile = (
        db.query(AccountProfile)
        .filter(
            AccountProfile.organization_id == current_user["organization_id"],
            func.upper(AccountProfile.policy_number) == normalized_policy_number,
        )
        .first()
    )

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    db.delete(profile)
    db.commit()

    return {"message": "Profile deleted"}