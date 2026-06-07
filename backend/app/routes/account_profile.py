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
    return value.strip(" :-|")


def normalize_policy(value: Any) -> str:
    return clean_value(value).upper()


def is_valid_policy(value: Any) -> bool:
    policy = normalize_policy(value)
    if not policy:
        return False
    if policy in {
        "POLICY",
        "POLICYNUMBER",
        "POLICYTERM",
        "ACCOUNT",
        "ACCOUNTNUMBER",
        "LOB",
        "UPLOAD",
    }:
        return False
    if policy.startswith("UPLOAD-"):
        return False
    if len(policy) < 4:
        return False
    return bool(re.search(r"\d", policy))


def safe_money(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        cleaned = str(value).replace("$", "").replace(",", "").strip()
        if cleaned in {"", "-", "None", "none", "null"}:
            return 0.0
        return float(cleaned)
    except Exception:
        return 0.0


def parse_json_value(value: Any, fallback: Any):
    try:
        if value is None or value == "":
            return fallback
        if isinstance(value, (list, dict)):
            return value
        return json.loads(value)
    except Exception:
        return fallback


def serialize_json(value: Any, fallback: Any):
    try:
        if value is None:
            return json.dumps(fallback)
        if isinstance(value, str):
            try:
                json.loads(value)
                return value
            except Exception:
                return json.dumps(fallback)
        return json.dumps(value)
    except Exception:
        return json.dumps(fallback)


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
        existing_columns = [column["name"] for column in inspector.get_columns("account_profiles")]

        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                db.execute(text(f"ALTER TABLE account_profiles ADD COLUMN {column_name} {column_type}"))

        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Account profile column check failed: {e}")


def safe_profile_policies(profile: AccountProfile):
    """
    Return ONLY the policies saved on this profile.
    This does not merge all organization claims into every profile.
    """
    raw_policies = parse_json_value(getattr(profile, "policies", None), [])
    safe_policies = []

    if isinstance(raw_policies, list):
        for item in raw_policies:
            if not isinstance(item, dict):
                continue

            policy_number = normalize_policy(item.get("policy_number"))
            if not is_valid_policy(policy_number):
                continue

            safe_policies.append(
                {
                    "policy_number": policy_number,
                    "policy_type": clean_value(
                        item.get("policy_type")
                        or item.get("line_of_business")
                        or item.get("coverage")
                        or "Unknown"
                    ),
                    "line_of_business": clean_value(
                        item.get("line_of_business")
                        or item.get("policy_type")
                        or item.get("coverage")
                        or "Unknown"
                    ),
                    "writing_carrier": clean_value(item.get("writing_carrier") or ""),
                    "carrier": clean_value(item.get("carrier") or ""),
                    "effective_date": clean_value(item.get("effective_date") or ""),
                    "expiration_date": clean_value(item.get("expiration_date") or ""),
                    "claim_count": int(float(item.get("claim_count") or item.get("claims") or 0)),
                    "total_incurred": safe_money(item.get("total_incurred")),
                }
            )

    return safe_policies


def profile_to_dict(profile: AccountProfile):
    return {
        "id": getattr(profile, "id", None),
        "business_name": clean_value(getattr(profile, "business_name", "")),
        "carrier_name": clean_value(getattr(profile, "carrier_name", "")),
        "writing_carrier": clean_value(getattr(profile, "writing_carrier", "") or getattr(profile, "carrier_name", "")),
        "agency_name": clean_value(getattr(profile, "agency_name", "")),
        "account_number": clean_value(getattr(profile, "account_number", "")),
        "customer_number": clean_value(getattr(profile, "customer_number", "")),
        "producer_number": clean_value(getattr(profile, "producer_number", "")),
        "policy_number": clean_value(getattr(profile, "policy_number", "")),
        "effective_date": clean_value(getattr(profile, "effective_date", "")),
        "expiration_date": clean_value(getattr(profile, "expiration_date", "")),
        "evaluation_date": clean_value(getattr(profile, "evaluation_date", "")),
        "policies": safe_profile_policies(profile),
        "validation": parse_json_value(getattr(profile, "validation", None), {}),
        "raw_text_preview": clean_value(getattr(profile, "raw_text_preview", "")),
        "profile_source": "account_profile",
    }


def profile_matches_policy(profile: AccountProfile, policy_number: str) -> bool:
    normalized = normalize_policy(policy_number)
    data = profile_to_dict(profile)

    direct_values = [
        data.get("policy_number"),
        data.get("account_number"),
        data.get("customer_number"),
    ]

    if normalized in [normalize_policy(value) for value in direct_values]:
        return True

    for item in data.get("policies") or []:
        if normalize_policy(item.get("policy_number")) == normalized:
            return True

    return False


def find_profile_by_policy(db: Session, current_user: dict, policy_number: str):
    normalized = normalize_policy(policy_number)

    profiles = (
        db.query(AccountProfile)
        .filter(AccountProfile.organization_id == current_user["organization_id"])
        .order_by(AccountProfile.id.desc())
        .all()
    )

    for profile in profiles:
        if profile_matches_policy(profile, normalized):
            return profile

    return None


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
        return blank_profile()

    return profile_to_dict(profile)


@router.get("/blank")
def get_blank_profile():
    return blank_profile()


@router.get("/all")
def get_all_profiles(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Safe list route:
    - Does NOT create profiles.
    - Does NOT rebuild deleted profiles from old claims.
    - Does NOT merge all organization claims into every profile.
    """
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
    """
    Safe policy lookup:
    - Finds a parent profile or child policy inside that profile's saved schedule.
    - Does NOT create a new profile on GET.
    """
    ensure_account_profile_columns(db)

    normalized = normalize_policy(policy_number)

    if not normalized:
        raise HTTPException(status_code=400, detail="Policy number is required")

    profile = find_profile_by_policy(db, current_user, normalized)

    if not profile:
        raise HTTPException(status_code=404, detail="Policy number not found")

    data = profile_to_dict(profile)

    if normalize_policy(data.get("policy_number")) != normalized:
        data["selected_policy_number"] = normalized
        data["policy_number"] = normalized

    return data


@router.put("/")
def upsert_account_profile(
    payload: AccountProfileUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    ensure_account_profile_columns(db)

    policy_number = normalize_policy(payload.policy_number)

    if not is_valid_policy(policy_number):
        raise HTTPException(status_code=400, detail="Valid policy number is required")

    profile = find_profile_by_policy(db, current_user, policy_number)

    if not profile:
        profile = AccountProfile(organization_id=current_user["organization_id"])
        db.add(profile)

    profile.business_name = clean_value(payload.business_name) or "Business Name Not Set"
    profile.carrier_name = clean_value(payload.carrier_name) or "Carrier Not Set"
    profile.agency_name = clean_value(payload.agency_name) or "Agency Not Set"
    profile.policy_number = policy_number
    profile.effective_date = clean_value(payload.effective_date) or "Not Set"
    profile.expiration_date = clean_value(payload.expiration_date) or "Not Set"
    profile.evaluation_date = clean_value(payload.evaluation_date) or datetime.now().date().isoformat()

    if hasattr(profile, "writing_carrier"):
        profile.writing_carrier = clean_value(payload.writing_carrier) or clean_value(payload.carrier_name) or "Carrier Not Set"

    if hasattr(profile, "account_number"):
        profile.account_number = clean_value(payload.account_number) or policy_number

    if hasattr(profile, "customer_number"):
        profile.customer_number = clean_value(payload.customer_number) or policy_number

    if hasattr(profile, "producer_number"):
        profile.producer_number = clean_value(payload.producer_number)

    if hasattr(profile, "policies"):
        # Only save policies from the uploaded/profile payload, never all org claims.
        profile.policies = serialize_json(payload.policies or [], [])

    if hasattr(profile, "validation"):
        profile.validation = serialize_json(payload.validation or {}, {})

    if hasattr(profile, "raw_text_preview"):
        profile.raw_text_preview = clean_value(payload.raw_text_preview)

    db.commit()
    db.refresh(profile)

    return profile_to_dict(profile)


@router.delete("/")
def delete_account_profile_by_query(
    policy_number: str,
    delete_claims: bool = True,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return delete_profile(policy_number, delete_claims, db, current_user)


@router.delete("/{policy_number}")
def delete_profile(
    policy_number: str,
    delete_claims: bool = True,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    ensure_account_profile_columns(db)

    normalized = normalize_policy(policy_number)

    if not normalized:
        raise HTTPException(status_code=400, detail="Policy number is required")

    profile = find_profile_by_policy(db, current_user, normalized)

    related_policy_numbers = {normalized}

    if profile:
        data = profile_to_dict(profile)

        # Only include child policies from THIS saved profile schedule.
        # This route no longer uses all organization claims to expand deletion.
        for value in [data.get("policy_number"), data.get("account_number"), data.get("customer_number")]:
            value = normalize_policy(value)
            if is_valid_policy(value):
                related_policy_numbers.add(value)

        for item in data.get("policies") or []:
            value = normalize_policy(item.get("policy_number"))
            if is_valid_policy(value):
                related_policy_numbers.add(value)

    related_policy_numbers = {value for value in related_policy_numbers if is_valid_policy(value)}

    claims_deleted = 0
    if delete_claims and related_policy_numbers:
        claims_deleted = (
            db.query(Claim)
            .filter(Claim.organization_id == current_user["organization_id"])
            .filter(func.upper(func.trim(Claim.policy_number)).in_(related_policy_numbers))
            .delete(synchronize_session=False)
        )

    profiles_deleted = 0
    if profile:
        db.delete(profile)
        profiles_deleted = 1

    db.commit()

    return {
        "deleted": profiles_deleted > 0 or claims_deleted > 0,
        "policy_number": normalized,
        "profiles_deleted": profiles_deleted,
        "claims_deleted": claims_deleted,
        "related_policy_numbers": sorted(list(related_policy_numbers)),
        "message": "Profile and related claims deleted successfully."
        if (profiles_deleted > 0 or claims_deleted > 0)
        else "Profile not found.",
    }
