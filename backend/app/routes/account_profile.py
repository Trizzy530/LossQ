import os
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text, inspect, func, or_
from typing import Optional, Any
import json
import re
from datetime import datetime

from app.database import SessionLocal
from app.auth_utils import get_current_user
from app.models.account_profile import AccountProfile
from app.models.upload_history import UploadHistory
from app.models.claim import Claim
from app.services.audit import record_audit_event

router = APIRouter(prefix="/account-profile", tags=["Account Profile"])


class AccountProfileUpdate(BaseModel):
    # Stable row identity. Frontend can send this when editing an existing profile.
    id: Optional[int] = None

    business_name: Optional[str] = ""
    carrier_name: Optional[str] = ""
    agency_name: Optional[str] = ""

    # Stable account identifiers should be preferred over child policy number.
    account_number: Optional[str] = ""
    customer_number: Optional[str] = ""
    producer_number: Optional[str] = ""

    # This can be the parent account policy, primary policy, or selected child policy.
    policy_number: Optional[str] = ""

    effective_date: Optional[str] = ""
    expiration_date: Optional[str] = ""
    evaluation_date: Optional[str] = ""
    writing_carrier: Optional[str] = ""

    # These DB columns are TEXT in the current model, so they are stored as JSON strings.
    policies: Optional[Any] = None
    validation: Optional[Any] = None
    raw_text_preview: Optional[str] = ""

    # LOSSQ_ACCOUNT_PROFILE_UPDATE_EXPOSURE_FIELDS_V1
    current_premium: Optional[str] = ""
    expiring_premium: Optional[str] = ""
    target_renewal_premium: Optional[str] = ""
    line_of_business: Optional[str] = ""
    state: Optional[str] = ""
    class_code: Optional[str] = ""
    class_codes: Optional[str] = ""
    limits: Optional[str] = ""
    coverage_limit: Optional[str] = ""
    deductible: Optional[str] = ""
    retention: Optional[str] = ""
    payroll: Optional[str] = ""
    revenue: Optional[str] = ""
    sales: Optional[str] = ""
    receipts: Optional[str] = ""
    employee_count: Optional[str] = ""
    vehicle_count: Optional[str] = ""
    driver_count: Optional[str] = ""
    property_tiv: Optional[str] = ""
    tiv: Optional[str] = ""
    building_value: Optional[str] = ""
    contents_value: Optional[str] = ""
    square_footage: Optional[str] = ""
    location_count: Optional[str] = ""
    unit_count: Optional[str] = ""
    cargo_limit: Optional[str] = ""
    umbrella_limit: Optional[str] = ""
    experience_mod: Optional[str] = ""
    mod: Optional[str] = ""
    exposure_change_percent: Optional[str] = ""
    cyber_revenue: Optional[str] = ""
    professional_revenue: Optional[str] = ""
    exposure_basis: Optional[str] = ""
    underwriter_notes: Optional[str] = ""


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


def normalize_key(value: Any) -> str:
    return clean_value(value).upper()


def is_valid_identifier(value: Any) -> bool:
    value = normalize_key(value)
    if not value:
        return False

    blocked = {
        "POLICY",
        "POLICYNUMBER",
        "POLICY NUMBER",
        "POLICYTERM",
        "POLICY TERM",
        "ACCOUNT",
        "ACCOUNTNUMBER",
        "ACCOUNT NUMBER",
        "CUSTOMER",
        "LOB",
        "UPLOAD",
        "NONE",
        "NULL",
        "-",
    }

    if value in blocked:
        return False

    if value.startswith("UPLOAD-"):
        return False

    if len(value) < 3:
        return False

    # Most valid account/policy identifiers have at least one number.
    return bool(re.search(r"\d", value))


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
    """
    AccountProfile.policies and AccountProfile.validation are TEXT columns.
    Keep JSON as strings at the DB layer.
    """
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
        # LOSSQ_EXPOSURE_SAVE_RETURN_FINAL_V1
        "current_premium": "VARCHAR",
        "expiring_premium": "VARCHAR",
        "target_renewal_premium": "VARCHAR",
        "line_of_business": "VARCHAR",
        "state": "VARCHAR",
        "class_code": "VARCHAR",
        "class_codes": "VARCHAR",
        "limits": "VARCHAR",
        "coverage_limit": "VARCHAR",
        "deductible": "VARCHAR",
        "retention": "VARCHAR",
        "payroll": "VARCHAR",
        "revenue": "VARCHAR",
        "sales": "VARCHAR",
        "receipts": "VARCHAR",
        "employee_count": "VARCHAR",
        "vehicle_count": "VARCHAR",
        "driver_count": "VARCHAR",
        "property_tiv": "VARCHAR",
        "tiv": "VARCHAR",
        "building_value": "VARCHAR",
        "contents_value": "VARCHAR",
        "square_footage": "VARCHAR",
        "location_count": "VARCHAR",
        "unit_count": "VARCHAR",
        "cargo_limit": "VARCHAR",
        "umbrella_limit": "VARCHAR",
        "experience_mod": "VARCHAR",
        "mod": "VARCHAR",
        "exposure_change_percent": "VARCHAR",
        "cyber_revenue": "VARCHAR",
        "professional_revenue": "VARCHAR",
        "exposure_basis": "VARCHAR",
        "underwriter_notes": "TEXT",
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


def normalize_policy_list(raw_policies: Any):
    """
    Only normalize policies already saved on the profile/upload payload.
    Do not merge all organization claims here.
    """
    policies = parse_json_value(raw_policies, [])

    if not isinstance(policies, list):
        return []

    safe_policies = []
    seen = set()

    for item in policies:
        if not isinstance(item, dict):
            continue

        policy_number = normalize_key(
            item.get("policy_number")
            or item.get("policyNumber")
            or item.get("policy_no")
            or item.get("number")
        )

        if not is_valid_identifier(policy_number):
            continue

        if policy_number in seen:
            continue

        seen.add(policy_number)

        line_of_business = clean_value(
            item.get("line_of_business")
            or item.get("policy_type")
            or item.get("coverage")
            or item.get("lob")
            or "Unknown"
        )

        safe_policies.append(
            {
                "policy_number": policy_number,
                "policy_type": clean_value(item.get("policy_type") or line_of_business or "Unknown"),
                "line_of_business": line_of_business or "Unknown",
                "writing_carrier": clean_value(item.get("writing_carrier") or item.get("carrier") or ""),
                "carrier": clean_value(item.get("carrier") or item.get("writing_carrier") or ""),
                "effective_date": clean_value(item.get("effective_date") or item.get("effective") or ""),
                "expiration_date": clean_value(item.get("expiration_date") or item.get("expiration") or ""),
                "claim_count": int(float(item.get("claim_count") or item.get("claims") or 0)),
                "total_incurred": safe_money(item.get("total_incurred") or item.get("incurred")),
            }
        )

    return safe_policies


def profile_to_dict(profile: AccountProfile):
    return {
        "id": getattr(profile, "id", None),
        "business_name": clean_value(getattr(profile, "business_name", "")),
        "carrier_name": clean_value(getattr(profile, "carrier_name", "")),
        "writing_carrier": clean_value(
            getattr(profile, "writing_carrier", "") or getattr(profile, "carrier_name", "")
        ),
        "agency_name": clean_value(getattr(profile, "agency_name", "")),
        "account_number": clean_value(getattr(profile, "account_number", "")),
        "customer_number": clean_value(getattr(profile, "customer_number", "")),
        "producer_number": clean_value(getattr(profile, "producer_number", "")),
        "policy_number": clean_value(getattr(profile, "policy_number", "")),
        "effective_date": clean_value(getattr(profile, "effective_date", "")),
        "expiration_date": clean_value(getattr(profile, "expiration_date", "")),
        "evaluation_date": clean_value(getattr(profile, "evaluation_date", "")),
        "policies": normalize_policy_list(getattr(profile, "policies", None)),
        "validation": parse_json_value(getattr(profile, "validation", None), {}),
        "raw_text_preview": clean_value(getattr(profile, "raw_text_preview", "")),
        "current_premium": clean_value(getattr(profile, "current_premium", "")),
        "expiring_premium": clean_value(getattr(profile, "expiring_premium", "")),
        "target_renewal_premium": clean_value(getattr(profile, "target_renewal_premium", "")),
        "line_of_business": clean_value(getattr(profile, "line_of_business", "")),
        "state": clean_value(getattr(profile, "state", "")),
        "class_code": clean_value(getattr(profile, "class_code", "")),
        "class_codes": clean_value(getattr(profile, "class_codes", "")),
        "limits": clean_value(getattr(profile, "limits", "")),
        "coverage_limit": clean_value(getattr(profile, "coverage_limit", "")),
        "deductible": clean_value(getattr(profile, "deductible", "")),
        "retention": clean_value(getattr(profile, "retention", "")),
        "payroll": clean_value(getattr(profile, "payroll", "")),
        "revenue": clean_value(getattr(profile, "revenue", "")),
        "sales": clean_value(getattr(profile, "sales", "")),
        "receipts": clean_value(getattr(profile, "receipts", "")),
        "employee_count": clean_value(getattr(profile, "employee_count", "")),
        "vehicle_count": clean_value(getattr(profile, "vehicle_count", "")),
        "driver_count": clean_value(getattr(profile, "driver_count", "")),
        "property_tiv": clean_value(getattr(profile, "property_tiv", "")),
        "tiv": clean_value(getattr(profile, "tiv", "")),
        "building_value": clean_value(getattr(profile, "building_value", "")),
        "contents_value": clean_value(getattr(profile, "contents_value", "")),
        "square_footage": clean_value(getattr(profile, "square_footage", "")),
        "location_count": clean_value(getattr(profile, "location_count", "")),
        "unit_count": clean_value(getattr(profile, "unit_count", "")),
        "cargo_limit": clean_value(getattr(profile, "cargo_limit", "")),
        "umbrella_limit": clean_value(getattr(profile, "umbrella_limit", "")),
        "experience_mod": clean_value(getattr(profile, "experience_mod", "")),
        "mod": clean_value(getattr(profile, "mod", "")),
        "exposure_change_percent": clean_value(getattr(profile, "exposure_change_percent", "")),
        "cyber_revenue": clean_value(getattr(profile, "cyber_revenue", "")),
        "professional_revenue": clean_value(getattr(profile, "professional_revenue", "")),
        "exposure_basis": clean_value(getattr(profile, "exposure_basis", "")),
        "underwriter_notes": clean_value(getattr(profile, "underwriter_notes", "")),
        "profile_source": "account_profile",
    }


def profile_contains_policy(profile: AccountProfile, policy_number: str) -> bool:
    target = normalize_key(policy_number)
    data = profile_to_dict(profile)

    for value in [data.get("policy_number"), data.get("account_number"), data.get("customer_number")]:
        if normalize_key(value) == target:
            return True

    for item in data.get("policies") or []:
        if normalize_key(item.get("policy_number")) == target:
            return True

    return False


def find_profile_by_id(db: Session, current_user: dict, profile_id: Optional[int]):
    if not profile_id:
        return None

    return (
        db.query(AccountProfile)
        .filter(
            AccountProfile.id == profile_id,
            AccountProfile.organization_id == current_user["organization_id"],
        )
        .first()
    )


def find_profile_for_save(db: Session, current_user: dict, payload: AccountProfileUpdate):
    """
    Save priority:
    1. Exact profile row ID when provided.
    2. Account number.
    3. Customer number.
    4. Primary policy number.
    This avoids treating a child policy as the main account identity.
    """
    profile = find_profile_by_id(db, current_user, payload.id)
    if profile:
        return profile

    account_number = normalize_key(payload.account_number)
    customer_number = normalize_key(payload.customer_number)
    policy_number = normalize_key(payload.policy_number)

    lookup_candidates = []

    if is_valid_identifier(account_number):
        lookup_candidates.append(("account_number", account_number))

    if is_valid_identifier(customer_number):
        lookup_candidates.append(("customer_number", customer_number))

    if is_valid_identifier(policy_number):
        lookup_candidates.append(("policy_number", policy_number))

    for column_name, value in lookup_candidates:
        column = getattr(AccountProfile, column_name, None)
        if column is None:
            continue

        profile = (
            db.query(AccountProfile)
            .filter(
                AccountProfile.organization_id == current_user["organization_id"],
                func.upper(func.trim(column)) == value,
            )
            .order_by(AccountProfile.id.desc())
            .first()
        )

        if profile:
            return profile

    return None


def find_profile_by_policy(db: Session, current_user: dict, policy_number: str):
    """
    Read-only lookup.
    It can find parent profiles that contain child policies, but it does not create anything.
    """
    normalized = normalize_key(policy_number)

    direct_match = (
        db.query(AccountProfile)
        .filter(
            AccountProfile.organization_id == current_user["organization_id"],
            func.upper(func.trim(AccountProfile.policy_number)) == normalized,
        )
        .order_by(AccountProfile.id.desc())
        .first()
    )

    if direct_match:
        return direct_match

    account_match = (
        db.query(AccountProfile)
        .filter(
            AccountProfile.organization_id == current_user["organization_id"],
            func.upper(func.trim(AccountProfile.account_number)) == normalized,
        )
        .order_by(AccountProfile.id.desc())
        .first()
    )

    if account_match:
        return account_match

    profiles = (
        db.query(AccountProfile)
        .filter(AccountProfile.organization_id == current_user["organization_id"])
        .order_by(AccountProfile.id.desc())
        .all()
    )

    for profile in profiles:
        if profile_contains_policy(profile, normalized):
            return profile

    return None


def blank_profile():
    return {
        "id": None,
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


def profile_delete_audit_details(profile_snapshot: dict | None = None, extra: dict | None = None):
    snapshot = profile_snapshot or {}

    details = {
        "profile_id": snapshot.get("id"),
        "business_name": snapshot.get("business_name"),
        "carrier_name": snapshot.get("carrier_name") or snapshot.get("writing_carrier"),
        "policy_number": snapshot.get("policy_number"),
        "account_number": snapshot.get("account_number"),
        "customer_number": snapshot.get("customer_number"),
        "line_of_business": snapshot.get("line_of_business"),
    }

    if extra:
        details.update(extra)

    return details


def related_policy_numbers_for_profile(profile: AccountProfile):
    data = profile_to_dict(profile)
    related = set()

    for value in [data.get("policy_number"), data.get("account_number"), data.get("customer_number")]:
        if is_valid_identifier(value):
            related.add(normalize_key(value))

    for item in data.get("policies") or []:
        value = normalize_key(item.get("policy_number"))
        if is_valid_identifier(value):
            related.add(value)

    return related


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
def get_blank_profile(current_user: dict = Depends(get_current_user)):
    return blank_profile()


@router.get("/all")
def get_all_profiles(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Safe list route:
    - Does NOT create profiles.
    - Does NOT recreate deleted profiles.
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


@router.get("/id/{profile_id}")
def get_profile_by_id(
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    ensure_account_profile_columns(db)

    profile = find_profile_by_id(db, current_user, profile_id)

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    return profile_to_dict(profile)


@router.get("/policy/{policy_number}")
def get_profile_by_policy(
    policy_number: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Read-only policy lookup.
    This never creates/recreates a profile.
    """
    ensure_account_profile_columns(db)

    normalized = normalize_key(policy_number)

    if not normalized:
        raise HTTPException(status_code=400, detail="Policy number is required")

    profile = find_profile_by_policy(db, current_user, normalized)

    if not profile:
        raise HTTPException(status_code=404, detail="Policy number not found")

    data = profile_to_dict(profile)

    if normalize_key(data.get("policy_number")) != normalized:
        data["selected_policy_number"] = normalized
        data["policy_number"] = normalized

    return data


@router.put("/")
def upsert_account_profile(
    payload: AccountProfileUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Stable save route:
    - Prefer exact profile ID.
    - Then account_number.
    - Then customer_number.
    - Only then fallback to policy_number.
    """
    ensure_account_profile_columns(db)

    account_number = normalize_key(payload.account_number)
    customer_number = normalize_key(payload.customer_number)
    policy_number = normalize_key(payload.policy_number)

    save_key = account_number or customer_number or policy_number

    if not is_valid_identifier(save_key):
        raise HTTPException(
            status_code=400,
            detail="Valid account_number, customer_number, or policy_number is required",
        )

    profile = find_profile_for_save(db, current_user, payload)

    if not profile:
        profile = AccountProfile(organization_id=current_user["organization_id"])
        db.add(profile)

    safe_policies = normalize_policy_list(payload.policies or [])

    # If the upload payload did not include a policy schedule, keep existing policies
    # when editing an existing profile. This prevents accidental wipes on manual saves.
    if not safe_policies and getattr(profile, "id", None):
        safe_policies = normalize_policy_list(getattr(profile, "policies", None))

    primary_policy = policy_number
    if not is_valid_identifier(primary_policy) and safe_policies:
        primary_policy = normalize_key(safe_policies[0].get("policy_number"))

    profile.business_name = clean_value(payload.business_name)
    profile.carrier_name = clean_value(payload.carrier_name)
    profile.agency_name = clean_value(payload.agency_name)

    profile.account_number = account_number or customer_number or primary_policy or save_key
    profile.customer_number = customer_number or account_number or primary_policy or save_key
    profile.producer_number = clean_value(payload.producer_number)

    profile.policy_number = primary_policy or profile.account_number

    profile.effective_date = clean_value(payload.effective_date)
    profile.expiration_date = clean_value(payload.expiration_date)
    profile.evaluation_date = clean_value(payload.evaluation_date) or datetime.now().date().isoformat()

    profile.writing_carrier = (
        clean_value(payload.writing_carrier)
        or clean_value(payload.carrier_name)
        or "Carrier Not Set"
    )

    # Save automatic extraction + manual override exposure inputs.
    for field in [
        "current_premium",
        "expiring_premium",
        "target_renewal_premium",
        "line_of_business",
        "state",
        "class_code",
        "class_codes",
        "limits",
        "coverage_limit",
        "deductible",
        "retention",
        "payroll",
        "revenue",
        "sales",
        "receipts",
        "employee_count",
        "vehicle_count",
        "driver_count",
        "property_tiv",
        "tiv",
        "building_value",
        "contents_value",
        "square_footage",
        "location_count",
        "unit_count",
        "cargo_limit",
        "umbrella_limit",
        "experience_mod",
        "mod",
        "exposure_change_percent",
        "cyber_revenue",
        "professional_revenue",
        "exposure_basis",
        "underwriter_notes",
    ]:
        if hasattr(profile, field) and hasattr(payload, field):
            setattr(profile, field, clean_value(getattr(payload, field, "")))

    profile.policies = serialize_json(safe_policies, [])
    profile.validation = serialize_json(payload.validation or {}, {})
    profile.raw_text_preview = clean_value(payload.raw_text_preview)

    db.commit()
    db.refresh(profile)

    return profile_to_dict(profile)


def hard_delete_profile_traces(db, current_user: dict, profile, delete_claims: bool = True):
    # LOSSQ_HARD_DELETE_PROFILE_TRACES_V2
    # Permanently wipes backend traces tied to a deleted account profile.
    # This prevents deleted profiles from being recognized again after reupload.

    from sqlalchemy import or_, func

    deleted_claims = 0
    deleted_upload_history = 0
    deleted_files = 0

    organization_id = current_user["organization_id"]

    profile_keys = []
    profile_name_hints = []

    def clean_key(value):
        return str(value or "").strip()

    def add_key(value):
        cleaned = clean_key(value)
        if cleaned and cleaned.upper() not in {"NOT SET", "NONE", "NULL", "N/A"}:
            if cleaned not in profile_keys:
                profile_keys.append(cleaned)

    def add_name_hint(value):
        cleaned = clean_key(value)
        if cleaned and cleaned.upper() not in {"NOT SET", "NONE", "NULL", "N/A", "BUSINESS NAME NOT SET", "CARRIER NOT SET"}:
            lowered = cleaned.lower()
            if lowered not in profile_name_hints:
                profile_name_hints.append(lowered)

    if profile is not None:
        add_key(getattr(profile, "policy_number", None))
        add_key(getattr(profile, "account_number", None))
        add_key(getattr(profile, "customer_number", None))
        add_key(getattr(profile, "producer_number", None))

        add_name_hint(getattr(profile, "business_name", None))
        add_name_hint(getattr(profile, "carrier_name", None))
        add_name_hint(getattr(profile, "writing_carrier", None))

        # Pull child policy numbers from the saved policies JSON/text column.
        try:
            policies_value = getattr(profile, "policies", None)
            parsed_policies = []

            if isinstance(policies_value, str) and policies_value.strip():
                parsed_policies = json.loads(policies_value)
            elif isinstance(policies_value, list):
                parsed_policies = policies_value

            if isinstance(parsed_policies, list):
                for item in parsed_policies:
                    if isinstance(item, dict):
                        add_key(item.get("policy_number"))
                        add_key(item.get("account_number"))
                        add_key(item.get("customer_number"))
                        add_key(item.get("policy"))
                        add_key(item.get("policyNumber"))
                    else:
                        add_key(item)
        except Exception:
            pass

    # Delete claims that match policy/account/customer identifiers OR business/carrier hints.
    if delete_claims:
        claim_query = db.query(Claim).filter(Claim.organization_id == organization_id)

        claim_filters = []

        if profile_keys:
            upper_keys = [key.upper() for key in profile_keys]

            if hasattr(Claim, "policy_number"):
                claim_filters.append(func.upper(func.trim(Claim.policy_number)).in_(upper_keys))

            if hasattr(Claim, "claim_number"):
                claim_filters.append(func.upper(func.trim(Claim.claim_number)).in_(upper_keys))

        for hint in profile_name_hints:
            like_hint = f"%{hint}%"

            if hasattr(Claim, "insured_name"):
                claim_filters.append(func.lower(Claim.insured_name).like(like_hint))

            if hasattr(Claim, "business_name"):
                claim_filters.append(func.lower(Claim.business_name).like(like_hint))

            if hasattr(Claim, "carrier_name"):
                claim_filters.append(func.lower(Claim.carrier_name).like(like_hint))

            if hasattr(Claim, "raw_text"):
                claim_filters.append(func.lower(Claim.raw_text).like(like_hint))

        if claim_filters:
            deleted_claims = (
                claim_query
                .filter(or_(*claim_filters))
                .delete(synchronize_session=False)
            )

    # Delete upload history rows that match the same profile identifiers/name hints.
    upload_rows = (
        db.query(UploadHistory)
        .filter(UploadHistory.organization_id == organization_id)
        .all()
    )

    for upload in upload_rows:
        upload_text_parts = []

        for attr in [
            "filename",
            "file_name",
            "original_filename",
            "policy_number",
            "account_number",
            "customer_number",
            "business_name",
            "carrier_name",
            "status",
            "notes",
            "raw_text_preview",
        ]:
            if hasattr(upload, attr):
                upload_text_parts.append(str(getattr(upload, attr) or ""))

        upload_text = " ".join(upload_text_parts).lower()

        should_delete_upload = False

        for key in profile_keys:
            if key and key.lower() in upload_text:
                should_delete_upload = True
                break

        if not should_delete_upload:
            for hint in profile_name_hints:
                if hint and hint in upload_text:
                    should_delete_upload = True
                    break

        if should_delete_upload:
            for path_attr in ["file_path", "path", "stored_path", "saved_path"]:
                if hasattr(upload, path_attr):
                    file_path = getattr(upload, path_attr, None)
                    if file_path:
                        try:
                            if os.path.exists(file_path):
                                os.remove(file_path)
                                deleted_files += 1
                        except Exception:
                            pass

            db.delete(upload)
            deleted_upload_history += 1

    return {
        "profile_keys": profile_keys,
        "profile_name_hints": profile_name_hints,
        "deleted_claims": deleted_claims,
        "deleted_upload_history": deleted_upload_history,
        "deleted_files": deleted_files,
    }




# LOSSQ_HARD_PURGE_PROFILE_ID_V1
@router.delete("/hard-purge-id/{profile_id}")
def hard_purge_profile_by_id(
    profile_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Hard purge one exact AccountProfile row and all claims tied to its account,
    policy number, account number, customer number, and policy schedule.
    """
    org_id = current_user["organization_id"]

    profile = (
        db.query(AccountProfile)
        .filter(
            AccountProfile.id == profile_id,
            AccountProfile.organization_id == org_id,
        )
        .first()
    )

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found for this organization.")

    profile_snapshot = profile_to_dict(profile)

    keys = set()

    def add_key(value):
        value = clean_value(value).upper()
        if value and value not in {"NONE", "NULL", "UNKNOWN"}:
            keys.add(value)

    add_key(getattr(profile, "policy_number", ""))
    add_key(getattr(profile, "account_number", ""))
    add_key(getattr(profile, "customer_number", ""))

    try:
        policies = parse_json_field(getattr(profile, "policies", None), [])
        if isinstance(policies, list):
            for item in policies:
                if isinstance(item, dict):
                    add_key(item.get("policy_number"))
                    add_key(item.get("policyNumber"))
                    add_key(item.get("number"))
                    add_key(item.get("account_number"))
                    add_key(item.get("accountNumber"))
    except Exception:
        pass

    deleted_claims = 0
    deleted_upload_history = 0

    try:
        from app.models.claim import Claim

        filters = []
        for key in keys:
            filters.append(func.upper(func.coalesce(Claim.policy_number, "")).like(f"%{key}%"))
            filters.append(func.upper(func.coalesce(Claim.claim_number, "")).like(f"%{key}%"))

        if filters:
            deleted_claims = (
                db.query(Claim)
                .filter(
                    Claim.organization_id == org_id,
                    or_(*filters),
                )
                .delete(synchronize_session=False)
            )
    except Exception as e:
        print(f"Hard purge profile claims failed: {e}")

    try:
        from app.models.upload_history import UploadHistory

        filters = []
        for key in keys:
            filters.append(func.upper(func.coalesce(UploadHistory.policy_number, "")).like(f"%{key}%"))
            filters.append(func.upper(func.coalesce(UploadHistory.filename, "")).like(f"%{key}%"))

        if filters:
            deleted_upload_history = (
                db.query(UploadHistory)
                .filter(
                    UploadHistory.organization_id == org_id,
                    or_(*filters),
                )
                .delete(synchronize_session=False)
            )
    except Exception as e:
        print(f"Hard purge profile upload history failed: {e}")

    db.delete(profile)
    db.commit()

    record_audit_event(
        db,
        current_user=current_user,
        action="account_profile_hard_purged",
        resource_type="account_profile",
        resource_id=str(profile_id),
        details=profile_delete_audit_details(
            profile_snapshot,
            {
                "event": "account_profile_hard_purged",
                "profile_id": profile_id,
                "keys_used": sorted(list(keys)),
                "deleted_claims": deleted_claims,
                "deleted_profiles": 1,
                "deleted_upload_history": deleted_upload_history,
            },
        ),
        request=request,
    )

    return {
        "message": "Hard profile purge completed.",
        "profile_id": profile_id,
        "keys_used": sorted(list(keys)),
        "deleted_claims": deleted_claims,
        "deleted_profiles": 1,
        "deleted_upload_history": deleted_upload_history,
    }




@router.delete("/")
def delete_account_profile_by_query(
    request: Request,
    profile_id: Optional[int] = Query(default=None),
    policy_number: Optional[str] = Query(default=None),
    delete_claims: bool = Query(default=True),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if profile_id:
        return delete_profile_by_id(profile_id, delete_claims, db, current_user, request=request)

    if not policy_number:
        raise HTTPException(status_code=400, detail="profile_id or policy_number is required")

    return delete_profile_by_policy(policy_number, delete_claims, db, current_user, request=request)


@router.delete("/id/{profile_id}")
def delete_profile_by_id(
    profile_id: int,
    delete_claims: bool = True,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    request: Request = None,
):
    """
    Safest delete route.
    Deletes the exact profile row first, then claims tied to that profile's own saved schedule.
    """
    ensure_account_profile_columns(db)

    profile = find_profile_by_id(db, current_user, profile_id)

    if not profile:
        return {
            "deleted": False,
            "profile_id": profile_id,
            "profiles_deleted": 0,
            "claims_deleted": 0,
            "related_policy_numbers": [],
            "message": "Profile not found.",
        }

    related_policy_numbers = related_policy_numbers_for_profile(profile)
    profile_snapshot = profile_to_dict(profile)

    claims_deleted = 0
    if delete_claims and related_policy_numbers:
        claims_deleted = (
            db.query(Claim)
            .filter(Claim.organization_id == current_user["organization_id"])
            .filter(func.upper(func.trim(Claim.policy_number)).in_(related_policy_numbers))
            .delete(synchronize_session=False)
        )

    # LOSSQ_HARD_DELETE_CALL_V1
    hard_delete_result = hard_delete_profile_traces(db, current_user, profile, delete_claims=delete_claims)

    db.delete(profile)
    db.commit()

    record_audit_event(
        db,
        current_user=current_user,
        action="account_profile_deleted",
        resource_type="account_profile",
        resource_id=str(profile_id),
        details=profile_delete_audit_details(
            profile_snapshot,
            {
                "event": "account_profile_deleted",
                "profile_id": profile_id,
                "delete_claims": delete_claims,
                "claims_deleted": claims_deleted,
                "hard_delete": hard_delete_result,
                "related_policy_numbers": sorted(list(related_policy_numbers)),
            },
        ),
        request=request,
    )

    return {
        "deleted": True,
        "hard_delete": hard_delete_result,
        "profile_id": profile_id,
        "profiles_deleted": 1,
        "claims_deleted": claims_deleted,
        "related_policy_numbers": sorted(list(related_policy_numbers)),
        "message": "Exact profile and related claims deleted successfully.",
    }


@router.delete("/{policy_number}")
def delete_profile_by_policy(
    policy_number: str,
    delete_claims: bool = True,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    request: Request = None,
):
    """
    Backward-compatible delete route.
    Prefer /account-profile/id/{profile_id} from the frontend when possible.
    """
    ensure_account_profile_columns(db)

    normalized = normalize_key(policy_number)

    if not normalized:
        raise HTTPException(status_code=400, detail="Policy number is required")

    profile = find_profile_by_policy(db, current_user, normalized)

    if not profile:
        return {
            "deleted": False,
            "policy_number": normalized,
            "profiles_deleted": 0,
            "claims_deleted": 0,
            "related_policy_numbers": [],
            "message": "Profile not found.",
        }

    return delete_profile_by_id(
        profile_id=profile.id,
        delete_claims=delete_claims,
        db=db,
        current_user=current_user,
        request=request,
    )



# LOSSQ_HARD_PURGE_ACCOUNT_BY_KEY_V1
@router.delete("/hard-purge/{account_key}")
def hard_purge_account_by_key(
    account_key: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Emergency hard purge for stale account data.

    Deletes all profiles, claims, upload history, and related rows that contain
    the shared account/policy key, such as 742918.

    This prevents LossQ from reusing old claim rows after backend/parser fixes.
    """
    key = clean_value(account_key).upper()

    if not key or len(key) < 4:
        raise HTTPException(status_code=400, detail="Account key must be at least 4 characters.")

    org_id = current_user["organization_id"]
    like_key = f"%{key}%"

    deleted_claims = 0
    deleted_profiles = 0
    deleted_upload_history = 0

    try:
        from app.models.claim import Claim
        deleted_claims = (
            db.query(Claim)
            .filter(
                Claim.organization_id == org_id,
                or_(
                    func.upper(func.coalesce(Claim.policy_number, "")).like(like_key),
                    func.upper(func.coalesce(Claim.claim_number, "")).like(like_key),
                ),
            )
            .delete(synchronize_session=False)
        )
    except Exception as e:
        print(f"Hard purge claim cleanup failed: {e}")

    try:
        from app.models.upload_history import UploadHistory
        deleted_upload_history = (
            db.query(UploadHistory)
            .filter(
                UploadHistory.organization_id == org_id,
                or_(
                    func.upper(func.coalesce(UploadHistory.policy_number, "")).like(like_key),
                    func.upper(func.coalesce(UploadHistory.filename, "")).like(like_key),
                ),
            )
            .delete(synchronize_session=False)
        )
    except Exception as e:
        print(f"Hard purge upload history cleanup failed: {e}")

    try:
        deleted_profiles = (
            db.query(AccountProfile)
            .filter(
                AccountProfile.organization_id == org_id,
                or_(
                    func.upper(func.coalesce(AccountProfile.policy_number, "")).like(like_key),
                    func.upper(func.coalesce(AccountProfile.account_number, "")).like(like_key),
                    func.upper(func.coalesce(AccountProfile.customer_number, "")).like(like_key),
                    func.upper(func.coalesce(AccountProfile.business_name, "")).like(like_key),
                    func.upper(func.coalesce(AccountProfile.named_insured, "")).like(like_key),
                    func.upper(func.coalesce(AccountProfile.policies, "")).like(like_key),
                ),
            )
            .delete(synchronize_session=False)
        )
    except Exception as e:
        print(f"Hard purge profile cleanup failed: {e}")

    db.commit()

    record_audit_event(
        db,
        current_user=current_user,
        action="account_hard_purged",
        resource_type="account_profile",
        resource_id=key,
        details={
            "event": "account_hard_purged",
            "account_key": key,
            "deleted_claims": deleted_claims,
            "deleted_profiles": deleted_profiles,
            "deleted_upload_history": deleted_upload_history,
            "organization_id": current_user.get("organization_id"),
        },
        request=request,
    )

    return {
        "message": "Hard purge completed.",
        "account_key": key,
        "deleted_claims": deleted_claims,
        "deleted_profiles": deleted_profiles,
        "deleted_upload_history": deleted_upload_history,
    }
