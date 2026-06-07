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


def normalize_policy_number(value: Any) -> str:
    return clean_value(value).upper()


def money_float(value: Any) -> float:
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
    return clean_value(value).lower() in {"", "business name not set", "unnamed business", "not set", "none", "null", "-"}


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


def profile_to_dict(profile: AccountProfile):
    return {
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
        "policies": parse_json_value(getattr(profile, "policies", None), []),
        "validation": parse_json_value(getattr(profile, "validation", None), {}),
        "raw_text_preview": clean_value(getattr(profile, "raw_text_preview", "")),
        "profile_source": "account_profile",
    }


def build_policy_rollup_from_claims(claims: list[Claim]):
    grouped: dict[str, dict[str, Any]] = {}
    for claim in claims:
        policy_number = normalize_policy_number(getattr(claim, "policy_number", ""))
        if not policy_number:
            continue
        lob = clean_value(getattr(claim, "line_of_business", "")) or "Unknown"
        total = money_float(getattr(claim, "total_incurred", 0))
        if policy_number not in grouped:
            grouped[policy_number] = {"policy_number": policy_number, "policy_type": lob, "line_of_business": lob, "claim_count": 0, "total_incurred": 0.0}
        grouped[policy_number]["claim_count"] += 1
        grouped[policy_number]["total_incurred"] += total
    return list(grouped.values())


def find_profile_by_policy(db: Session, current_user: dict, normalized_policy_number: str):
    profiles = db.query(AccountProfile).filter(AccountProfile.organization_id == current_user["organization_id"]).order_by(AccountProfile.id.desc()).all()
    for profile in profiles:
        data = profile_to_dict(profile)
        direct_values = [data.get("policy_number"), data.get("account_number"), data.get("customer_number")]
        if normalized_policy_number in [normalize_policy_number(v) for v in direct_values]:
            return profile
        for policy_item in data.get("policies") or []:
            if normalize_policy_number(policy_item.get("policy_number")) == normalized_policy_number:
                return profile
    return None


def create_profile_from_claims(db: Session, policy_number: str, claims: list[Claim], current_user: dict, template_profile: AccountProfile | None = None):
    template = profile_to_dict(template_profile) if template_profile else {}
    policies = build_policy_rollup_from_claims(claims)
    total_incurred = sum(money_float(claim.total_incurred or 0) for claim in claims)
    validation = {"is_valid": len(claims) > 0, "confidence_score": 85 if claims else 50, "needs_manual_review": not bool(claims), "needs_review": [] if claims else ["No claim rows were found."], "policy_count": len(policies), "claim_count": len(claims), "calculated_total_incurred": total_incurred}
    profile = AccountProfile(
        organization_id=current_user["organization_id"],
        business_name=template.get("business_name") or "Business Name Not Set",
        carrier_name=template.get("carrier_name") or "Carrier Not Set",
        writing_carrier=template.get("writing_carrier") or template.get("carrier_name") or "Carrier Not Set",
        agency_name=template.get("agency_name") or "Agency Not Set",
        account_number=policy_number,
        customer_number=policy_number,
        producer_number="",
        policy_number=policy_number,
        effective_date=template.get("effective_date") or "Not Set",
        expiration_date=template.get("expiration_date") or "Not Set",
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
def get_default_profile(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    ensure_account_profile_columns(db)
    profile = db.query(AccountProfile).filter(AccountProfile.organization_id == current_user["organization_id"]).order_by(AccountProfile.id.desc()).first()
    if not profile:
        return {"business_name": "", "carrier_name": "", "writing_carrier": "", "agency_name": "", "account_number": "", "customer_number": "", "producer_number": "", "policy_number": "", "effective_date": "", "expiration_date": "", "evaluation_date": "", "policies": [], "validation": {}, "profile_source": "blank"}
    return profile_to_dict(profile)


@router.get("/blank")
def blank_profile():
    return {"business_name": "", "carrier_name": "", "writing_carrier": "", "agency_name": "", "account_number": "", "customer_number": "", "producer_number": "", "policy_number": "", "effective_date": "", "expiration_date": "", "evaluation_date": "", "policies": [], "validation": {}, "profile_source": "blank"}


@router.get("/all")
def get_all_profiles(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    ensure_account_profile_columns(db)
    profiles = db.query(AccountProfile).filter(AccountProfile.organization_id == current_user["organization_id"]).order_by(AccountProfile.id.desc()).all()
    return [profile_to_dict(profile) for profile in profiles]


@router.get("/policy/{policy_number}")
def get_profile_by_policy(policy_number: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    ensure_account_profile_columns(db)
    normalized_policy_number = normalize_policy_number(policy_number)
    if not normalized_policy_number:
        raise HTTPException(status_code=400, detail="Policy number is required")

    profile = find_profile_by_policy(db, current_user, normalized_policy_number)
    if profile:
        profile_data = profile_to_dict(profile)
        if normalize_policy_number(profile_data.get("policy_number")) != normalized_policy_number:
            profile_data["selected_policy_number"] = normalized_policy_number
            profile_data["policy_number"] = normalized_policy_number
        return profile_data

    claims = db.query(Claim).filter(Claim.organization_id == current_user["organization_id"], func.upper(func.trim(Claim.policy_number)) == normalized_policy_number).all()
    if not claims:
        raise HTTPException(status_code=404, detail="Policy number not found")

    template_profile = db.query(AccountProfile).filter(AccountProfile.organization_id == current_user["organization_id"]).order_by(AccountProfile.id.desc()).first()
    repaired_profile = create_profile_from_claims(db, normalized_policy_number, claims, current_user, template_profile)
    return profile_to_dict(repaired_profile)


@router.put("/")
def upsert_account_profile(payload: AccountProfileUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    ensure_account_profile_columns(db)
    policy_number = normalize_policy_number(payload.policy_number)
    if not policy_number:
        raise HTTPException(status_code=400, detail="Policy number is required")

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
        profile.policies = serialize_json(payload.policies, [])
    if hasattr(profile, "validation"):
        profile.validation = serialize_json(payload.validation, {})
    if hasattr(profile, "raw_text_preview"):
        profile.raw_text_preview = clean_value(payload.raw_text_preview)
    db.commit()
    db.refresh(profile)
    return profile_to_dict(profile)


@router.delete("/")
def delete_account_profile_by_query(policy_number: str, delete_claims: bool = True, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return delete_profile(policy_number, delete_claims, db, current_user)


@router.delete("/{policy_number}")
def delete_profile(policy_number: str, delete_claims: bool = True, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    ensure_account_profile_columns(db)
    normalized_policy_number = normalize_policy_number(policy_number)
    profile = find_profile_by_policy(db, current_user, normalized_policy_number)
    related_policy_numbers = {normalized_policy_number}
    if profile:
        data = profile_to_dict(profile)
        related_policy_numbers.add(normalize_policy_number(data.get("policy_number")))
        related_policy_numbers.add(normalize_policy_number(data.get("account_number")))
        for item in data.get("policies") or []:
            related_policy_numbers.add(normalize_policy_number(item.get("policy_number")))
    related_policy_numbers = {item for item in related_policy_numbers if item}
    claims_deleted = 0
    if delete_claims:
        claims_deleted = db.query(Claim).filter(Claim.organization_id == current_user["organization_id"]).filter(func.upper(func.trim(Claim.policy_number)).in_(related_policy_numbers)).delete(synchronize_session=False)
    profiles_deleted = 0
    if profile:
        db.delete(profile)
        profiles_deleted = 1
    db.commit()
    return {"deleted": profiles_deleted > 0 or claims_deleted > 0, "policy_number": normalized_policy_number, "profiles_deleted": profiles_deleted, "claims_deleted": claims_deleted, "related_policy_numbers": sorted(list(related_policy_numbers)), "message": "Profile and related claims deleted successfully." if (profiles_deleted > 0 or claims_deleted > 0) else "Profile not found."}
