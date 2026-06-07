from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text, inspect, func
from typing import Optional, Any
import json
import re
from datetime import datetime

from app.database import SessionLocal
from app.auth_utils import get_current_user
from app.models.account_profile import AccountProfile
from app.models.claim import Claim

router = APIRouter(prefix="/account-profile", tags=["Account Profile"])


class AccountProfileUpdate(BaseModel):
    business_name: Optional[str] = ""
    carrier_name: Optional[str] = ""
    agency_name: Optional[str] = ""
    policy_number: Optional[str] = ""
    effective_date: Optional[str] = ""
    expiration_date: Optional[str] = ""
    evaluation_date: Optional[str] = ""
    writing_carrier: Optional[str] = ""
    account_number: Optional[str] = ""
    customer_number: Optional[str] = ""
    producer_number: Optional[str] = ""
    policies: Optional[Any] = None
    validation: Optional[Any] = None
    raw_text_preview: Optional[str] = ""


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def clean_value(value: Any) -> str:
    value = str(value or "").strip()
    value = re.sub(r"\s+", " ", value)
    value = value.strip(" :-|")
    return value


def normalize_policy_number(value: Any) -> str:
    return clean_value(value).upper()


def serialize_json(value: Any, fallback: Any):
    try:
        if value is None:
            return json.dumps(fallback)
        if isinstance(value, str):
            return value
        return json.dumps(value)
    except Exception:
        return json.dumps(fallback)


def parse_json_value(value: Any, fallback: Any):
    try:
        if value is None or value == "":
            return fallback
        if isinstance(value, (list, dict)):
            return value
        return json.loads(value)
    except Exception:
        return fallback


def is_placeholder(value: Any) -> bool:
    cleaned = clean_value(value).lower()
    return cleaned in {
        "",
        "business name not set",
        "unnamed business",
        "not set",
        "none",
        "null",
        "-",
    }


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


def profile_to_dict(profile: AccountProfile):
    return {
        "business_name": clean_value(getattr(profile, "business_name", "")),
        "carrier_name": clean_value(getattr(profile, "carrier_name", "")),
        "writing_carrier": clean_value(
            getattr(profile, "writing_carrier", "")
            or getattr(profile, "carrier_name", "")
        ),
        "agency_name": clean_value(getattr(profile, "agency_name", "")),
        "account_number": clean_value(getattr(profile, "account_number", "")),
        "customer_number": clean_value(getattr(profile, "customer_number", "")),
        "producer_number": clean_value(getattr(profile, "producer_number", "")),
        "policy_number": clean_value(getattr(profile, "policy_number", "")),
        "effective_date": clean_value(getattr(profile, "effective_date", "")),
        "expiration_date": clean_value(getattr(profile, "expiration_date", "")),
        "evaluation_date": clean_value(getattr(profile, "evaluation_date", "")),
        "policies": parse_json_value(getattr(profile, "policies", None), []),
        "validation": parse_json_value(getattr(profile, "validation", None), {}),
        "raw_text_preview": clean_value(getattr(profile, "raw_text_preview", "")),
        "profile_source": "account_profile",
    }


def extract_business_name_from_text(text_value: Any) -> str:
    text_value = clean_value(text_value)
    if not text_value:
        return ""

    patterns = [
        r"(?:Named\s*Insured|NamedInsured|Insured|Account\s*Name|Customer)\s*[:\-]\s*(.*?)(?:Policy\s*Number|PolicyNumber|Claim\s*Number|ClaimNumber|Report\s*Run\s*Date|ReportRunDate|Page\s+\d+|$)",
        r"\b([A-Z][A-Za-z0-9&.,'’\-\s]{2,100}\s+(?:LLC|L\.L\.C\.|Inc\.?|Corporation|Corp\.?|Company|Co\.?|Ltd\.?))\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text_value, flags=re.IGNORECASE)
        if match:
            value = clean_value(match.group(1))
            value = re.sub(r"([a-z])([A-Z])", r"\1 \2", value)
            value = re.sub(
                r"(?:Policy\s*Number|PolicyNumber|Claim\s*Number|ClaimNumber|Report\s*Run\s*Date|ReportRunDate).*",
                "",
                value,
                flags=re.IGNORECASE,
            )
            value = clean_value(value)

            if value and not is_placeholder(value):
                return value[:120]

    return ""


def derive_business_name_from_claims(claims: list[Claim]) -> str:
    for claim in claims:
        for attr in [
            "business_name",
            "insured",
            "insured_name",
            "named_insured",
            "account_name",
            "company_name",
        ]:
            if hasattr(claim, attr):
                value = clean_value(getattr(claim, attr, ""))
                if value and not is_placeholder(value):
                    return value[:120]

        description = clean_value(getattr(claim, "description", ""))
        value = extract_business_name_from_text(description)
        if value:
            return value[:120]

    return ""


def derive_carrier_from_claims(claims: list[Claim]) -> str:
    for claim in claims:
        for attr in ["carrier_name", "carrier", "writing_carrier"]:
            if hasattr(claim, attr):
                value = clean_value(getattr(claim, attr, ""))
                if value and not is_placeholder(value):
                    return value[:120]
    return ""


def create_or_repair_profile_from_claims(
    db: Session,
    *,
    policy_number: str,
    claims: list[Claim],
    current_user: dict,
):
    business_name = derive_business_name_from_claims(claims)
    carrier_name = derive_carrier_from_claims(claims)

    total_incurred = sum(float(claim.total_incurred or 0) for claim in claims)

    policies = [
        {
            "policy_number": policy_number,
            "policy_type": "Needs Review",
            "line_of_business": "Needs Review",
            "claim_count": len(claims),
            "total_incurred": total_incurred,
        }
    ]

    validation = {
        "is_valid": bool(business_name),
        "confidence_score": 70 if business_name else 50,
        "needs_manual_review": not bool(business_name),
        "needs_review": [] if business_name else ["Business/account name was not detected."],
        "policy_count": 1,
        "claim_count": len(claims),
        "calculated_total_incurred": total_incurred,
    }

    profile = AccountProfile(
        organization_id=current_user["organization_id"],
        business_name=business_name or "Business Name Not Set",
        carrier_name=carrier_name or "Carrier Not Set",
        writing_carrier=carrier_name or "Carrier Not Set",
        agency_name="Agency Not Set",
        account_number=policy_number,
        customer_number=policy_number,
        producer_number="",
        policy_number=policy_number,
        effective_date="Not Set",
        expiration_date="Not Set",
        evaluation_date=datetime.now().date().isoformat(),
        policies=serialize_json(policies, []),
        validation=serialize_json(validation, {}),
        raw_text_preview="",
    )

    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


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
            "writing_carrier": "",
            "agency_name": "",
            "account_number": "",
            "customer_number": "",
            "producer_number": "",
            "policy_number": "",
            "effective_date": "",
            "expiration_date": "",
            "evaluation_date": "",
            "policies": [],
            "validation": {},
            "profile_source": "blank",
        }

    return profile_to_dict(profile)


@router.get("/blank")
def blank_profile():
    return {
        "business_name": "",
        "carrier_name": "",
        "writing_carrier": "",
        "agency_name": "",
        "account_number": "",
        "customer_number": "",
        "producer_number": "",
        "policy_number": "",
        "effective_date": "",
        "expiration_date": "",
        "evaluation_date": "",
        "policies": [],
        "validation": {},
        "profile_source": "blank",
    }


@router.get("/all")
def get_all_profiles(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    ensure_account_profile_columns(db)

    profiles = (
        db.query(AccountProfile)
        .filter(AccountProfile.organization_id == current_user["organization_id"])
        .order_by(AccountProfile.id.desc())
        .all()
    )

    return [profile_to_dict(profile) for profile in profiles]


@router.get("/policy/{policy_number}")
def get_profile_by_policy(
    policy_number: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    ensure_account_profile_columns(db)

    normalized_policy_number = normalize_policy_number(policy_number)

    if not normalized_policy_number:
        raise HTTPException(status_code=400, detail="Policy number is required")

    profile = (
        db.query(AccountProfile)
        .filter(
            AccountProfile.organization_id == current_user["organization_id"],
            func.upper(AccountProfile.policy_number) == normalized_policy_number,
        )
        .first()
    )

    if profile:
        profile_data = profile_to_dict(profile)

        if not is_placeholder(profile_data.get("business_name")):
            return profile_data

        claims_for_repair = (
            db.query(Claim)
            .filter(
                Claim.organization_id == current_user["organization_id"],
                func.upper(Claim.policy_number) == normalized_policy_number,
            )
            .all()
        )

        repaired_name = derive_business_name_from_claims(claims_for_repair)
        if repaired_name:
            profile.business_name = repaired_name
            if hasattr(profile, "account_number") and not profile.account_number:
                profile.account_number = normalized_policy_number
            if hasattr(profile, "customer_number") and not profile.customer_number:
                profile.customer_number = normalized_policy_number
            db.commit()
            db.refresh(profile)
            return profile_to_dict(profile)

        return profile_data

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

    repaired_profile = create_or_repair_profile_from_claims(
        db,
        policy_number=normalized_policy_number,
        claims=claims,
        current_user=current_user,
    )

    return profile_to_dict(repaired_profile)


@router.put("/")
def upsert_account_profile(
    payload: AccountProfileUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    ensure_account_profile_columns(db)

    policy_number = normalize_policy_number(payload.policy_number)

    if not policy_number:
        raise HTTPException(status_code=400, detail="Policy number is required")

    profile = (
        db.query(AccountProfile)
        .filter(
            AccountProfile.organization_id == current_user["organization_id"],
            func.upper(AccountProfile.policy_number) == policy_number,
        )
        .first()
    )

    if not profile:
        profile = AccountProfile(organization_id=current_user["organization_id"])
        db.add(profile)

    profile.business_name = clean_value(payload.business_name) or "Business Name Not Set"
    profile.carrier_name = clean_value(payload.carrier_name) or "Carrier Not Set"
    profile.agency_name = clean_value(payload.agency_name) or "Agency Not Set"
    profile.policy_number = policy_number
    profile.effective_date = clean_value(payload.effective_date) or "Not Set"
    profile.expiration_date = clean_value(payload.expiration_date) or "Not Set"
    profile.evaluation_date = (
        clean_value(payload.evaluation_date) or datetime.now().date().isoformat()
    )

    if hasattr(profile, "writing_carrier"):
        profile.writing_carrier = (
            clean_value(payload.writing_carrier)
            or clean_value(payload.carrier_name)
            or "Carrier Not Set"
        )

    if hasattr(profile, "account_number"):
        profile.account_number = clean_value(payload.account_number) or policy_number

    if hasattr(profile, "customer_number"):
        profile.customer_number = clean_value(payload.customer_number) or policy_number

    if hasattr(profile, "producer_number"):
        profile.producer_number = clean_value(payload.producer_number)

    if hasattr(profile, "policies"):
        profile.policies = serialize_json(payload.policies, [])

    if hasattr(profile, "validation"):
        profile.validation = serialize_json(payload.validation, {})

    if hasattr(profile, "raw_text_preview"):
        profile.raw_text_preview = clean_value(payload.raw_text_preview)

    db.commit()
    db.refresh(profile)

    return profile_to_dict(profile)


@router.delete("/cleanup-placeholder-profiles")
def cleanup_placeholder_profiles(
    keep_policy_numbers: str = "",
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    ensure_account_profile_columns(db)

    keep_set = {
        item.strip().upper()
        for item in str(keep_policy_numbers or "").split(",")
        if item.strip()
    }

    profiles = (
        db.query(AccountProfile)
        .filter(AccountProfile.organization_id == current_user["organization_id"])
        .all()
    )

    deleted_policy_numbers = []

    for profile in profiles:
        policy_number = normalize_policy_number(profile.policy_number)
        business_name = clean_value(profile.business_name)

        if policy_number in keep_set:
            continue

        if is_placeholder(business_name):
            deleted_policy_numbers.append(policy_number)
            db.delete(profile)

    db.commit()

    return {
        "deleted_count": len(deleted_policy_numbers),
        "deleted_policy_numbers": deleted_policy_numbers[:200],
        "kept_policy_numbers": sorted(list(keep_set)),
    }


@router.delete("/")
def delete_account_profile_by_query(
    policy_number: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return delete_profile(policy_number, db, current_user)


@router.delete("/{policy_number}")
def delete_profile(
    policy_number: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    ensure_account_profile_columns(db)

    normalized_policy_number = normalize_policy_number(policy_number)

    profile = (
        db.query(AccountProfile)
        .filter(
            AccountProfile.organization_id == current_user["organization_id"],
            func.upper(AccountProfile.policy_number) == normalized_policy_number,
        )
        .first()
    )

    if not profile:
        return {
            "deleted": False,
            "policy_number": normalized_policy_number,
            "message": "Profile not found.",
        }

    db.delete(profile)
    db.commit()

    return {
        "deleted": True,
        "policy_number": normalized_policy_number,
        "message": "Profile deleted successfully.",
    }