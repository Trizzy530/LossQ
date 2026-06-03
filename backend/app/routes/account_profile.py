from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.auth_utils import get_current_user
from app.models.account_profile import AccountProfile

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
    profile = (
        db.query(AccountProfile)
        .filter(
            AccountProfile.organization_id == current_user["organization_id"],
            AccountProfile.policy_number == policy_number,
        )
        .first()
    )

    if not profile:
        raise HTTPException(status_code=404, detail="Policy number not found")

    return profile


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

@router.delete("/delete")
def delete_account_profile_by_query(
    policy_number: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    profile = (
        db.query(AccountProfile)
        .filter(
            AccountProfile.organization_id == current_user["organization_id"],
            AccountProfile.policy_number == policy_number,
        )
        .first()
    )

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    db.delete(profile)
    db.commit()

    return {
        "message": "Profile deleted",
        "policy_number": policy_number,
    }

@router.delete("/{policy_number}")
def delete_profile(
    policy_number: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    profile = (
        db.query(AccountProfile)
        .filter(
            AccountProfile.organization_id == current_user["organization_id"],
            AccountProfile.policy_number == policy_number,
        )
        .first()
    )

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    db.delete(profile)
    db.commit()

    return {"message": "Profile deleted"}