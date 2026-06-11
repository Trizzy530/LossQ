import os
from fastapi import APIRouter, Depends, HTTPException, Query
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
from app.models.upload_history import UploadHistory
from app.models.claim import Claim

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

    profile.business_name = clean_value(payload.business_name) or "Business Name Not Set"
    profile.carrier_name = clean_value(payload.carrier_name) or "Carrier Not Set"
    profile.agency_name = clean_value(payload.agency_name) or "Agency Not Set"

    profile.account_number = account_number or customer_number or primary_policy or save_key
    profile.customer_number = customer_number or account_number or primary_policy or save_key
    profile.producer_number = clean_value(payload.producer_number)

    profile.policy_number = primary_policy or profile.account_number

    profile.effective_date = clean_value(payload.effective_date) or "Not Set"
    profile.expiration_date = clean_value(payload.expiration_date) or "Not Set"
    profile.evaluation_date = clean_value(payload.evaluation_date) or datetime.now().date().isoformat()

    profile.writing_carrier = (
        clean_value(payload.writing_carrier)
        or clean_value(payload.carrier_name)
        or "Carrier Not Set"
    )

    profile.policies = serialize_json(safe_policies, [])
    profile.validation = serialize_json(payload.validation or {}, {})
    profile.raw_text_preview = clean_value(payload.raw_text_preview)

    db.commit()
    db.refresh(profile)

    return profile_to_dict(profile)



def hard_delete_profile_traces(db, current_user: dict, profile, delete_claims: bool = True):
    # LOSSQ_HARD_DELETE_PROFILE_TRACES_V1
    # Hard delete every backend trace tied to a deleted profile/account.
    import json

    org_id = current_user["organization_id"]
    deleted_claims = 0
    deleted_upload_history = 0
    deleted_files = 0

    profile_keys = []
    profile_text_parts = []

    def add_key(value):
        cleaned = str(value or "").strip()
        if cleaned and cleaned not in profile_keys:
            profile_keys.append(cleaned)

    if profile is not None:
        add_key(getattr(profile, "policy_number", None))
        add_key(getattr(profile, "account_number", None))
        add_key(getattr(profile, "customer_number", None))

        profile_text_parts.extend([
            str(getattr(profile, "business_name", "") or ""),
            str(getattr(profile, "carrier_name", "") or ""),
            str(getattr(profile, "writing_carrier", "") or ""),
            str(getattr(profile, "policy_number", "") or ""),
            str(getattr(profile, "account_number", "") or ""),
            str(getattr(profile, "customer_number", "") or ""),
        ])

        try:
            policies_value = getattr(profile, "policies", None)
            policies = json.loads(policies_value) if isinstance(policies_value, str) else policies_value
            if isinstance(policies, list):
                for item in policies:
                    if isinstance(item, dict):
                        add_key(item.get("policy_number"))
                        add_key(item.get("policy"))
                        add_key(item.get("number"))
                        profile_text_parts.append(json.dumps(item))
        except Exception:
            pass

    profile_text = " ".join(profile_text_parts).lower()

    # Add profile-name based hints for test/demo files and real customer names.
    name_tokens = []
    for raw_name in [
        getattr(profile, "business_name", "") if profile is not None else "",
        getattr(profile, "account_name", "") if profile is not None and hasattr(profile, "account_name") else "",
    ]:
        cleaned_name = str(raw_name or "").strip().lower()
        if cleaned_name:
            name_tokens.append(cleaned_name)

    if delete_claims and profile_keys:
        claim_query = db.query(Claim).filter(Claim.organization_id == org_id)
        claim_query = claim_query.filter(Claim.policy_number.in_(profile_keys))
        deleted_claims = claim_query.delete(synchronize_session=False)

    # Delete UploadHistory rows that likely belong to the deleted account/profile.
    upload_query = db.query(UploadHistory).filter(UploadHistory.organization_id == org_id)
    uploads = upload_query.all()

    for upload in uploads:
        upload_text = " ".join([
            str(getattr(upload, "filename", "") or ""),
            str(getattr(upload, "stored_path", "") or ""),
            str(getattr(upload, "content_type", "") or ""),
        ]).lower()

        should_delete_upload = False

        for key in profile_keys:
            if str(key).lower() and str(key).lower() in upload_text:
                should_delete_upload = True

        for token in name_tokens:
            first_word = token.split(" ")[0] if token else ""
            if first_word and first_word in upload_text:
                should_delete_upload = True

        # If filename does not include account name/key, do not over-delete unrelated uploads.
        if should_delete_upload:
            stored_path = getattr(upload, "stored_path", None)
            if stored_path and os.path.exists(stored_path):
                try:
                    os.remove(stored_path)
                    deleted_files += 1
                except Exception:
                    pass

            db.delete(upload)
            deleted_upload_history += 1

    return {
        "profile_keys": profile_keys,
        "deleted_claims": deleted_claims,
        "deleted_upload_history": deleted_upload_history,
        "deleted_files": deleted_files,
    }



@router.delete("/")
def delete_account_profile_by_query(
    profile_id: Optional[int] = Query(default=None),
    policy_number: Optional[str] = Query(default=None),
    delete_claims: bool = Query(default=True),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if profile_id:
        return delete_profile_by_id(profile_id, delete_claims, db, current_user)

    if not policy_number:
        raise HTTPException(status_code=400, detail="profile_id or policy_number is required")

    return delete_profile_by_policy(policy_number, delete_claims, db, current_user)


@router.delete("/id/{profile_id}")
def delete_profile_by_id(
    profile_id: int,
    delete_claims: bool = True,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
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
    )
