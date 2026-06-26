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
    # LOSSQ_ACCOUNT_PROFILE_UPDATE_PHYSICIAN_COUNT_FIELD_V2
    physician_count: Optional[str] = ""
    vehicle_count: Optional[str] = ""
    driver_count: Optional[str] = ""
    property_tiv: Optional[str] = ""
    tiv: Optional[str] = ""
    building_value: Optional[str] = ""
    contents_value: Optional[str] = ""
    square_footage: Optional[str] = ""
    location_count: Optional[str] = ""
    # LOSSQ_PROFILE_LOCATION_LIQUOR_RESPONSE_V1
    liquor_sales: Optional[str] = ""
    alcohol_sales: Optional[str] = ""
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



# LOSSQ_ACCOUNT_PROFILE_PERSISTENCE_FALLBACK_KEY_V1
def lossq_account_profile_persistence_key_v1(data):
    """
    Allows /account-profile/ saves to persist account-level files even when a carrier file lacks a clean policy number.
    """
    data = data if isinstance(data, dict) else {}

    def slug(value):
        value = clean_value(value).upper()
        value = re.sub(r"[^A-Z0-9]+", "-", value).strip("-")
        value = re.sub(r"-+", "-", value)
        return value[:80]

    blocked = {
        "",
        "N-A",
        "NA",
        "NONE",
        "UNKNOWN",
        "POLICY",
        "POLICY-NUMBER",
        "CLAIM",
        "CLAIM-NUMBER",
        "LOSS-RUN",
        "ACCOUNT",
        "CUSTOMER",
        "PROFILE",
    }

    for key in [
        "policy_number",
        "main_policy",
        "main_policy_number",
        "account_number",
        "customer_number",
        "producer_number",
        "client_number",
    ]:
        candidate = slug(data.get(key))
        if candidate and candidate not in blocked:
            return candidate

    for key in ["policy_numbers", "policies", "policy_schedule"]:
        value = data.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    candidate = slug(item.get("policy_number") or item.get("policy") or item.get("number"))
                else:
                    candidate = slug(item)
                if candidate and candidate not in blocked:
                    return candidate

    business_name = slug(
        data.get("business_name")
        or data.get("named_insured")
        or data.get("insured_name")
        or data.get("account_name")
        or data.get("company_name")
    )

    carrier = slug(data.get("carrier_name") or data.get("writing_carrier") or data.get("insurer"))

    if business_name:
        if carrier:
            return slug(f"ACCOUNT-{business_name}-{carrier}")
        return slug(f"ACCOUNT-{business_name}")

    return ""

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
        # LOSSQ_ACCOUNT_PROFILE_ENSURE_PHYSICIAN_COUNT_COLUMN_V2
        "physician_count": "VARCHAR",
        "vehicle_count": "VARCHAR",
        "driver_count": "VARCHAR",
        "property_tiv": "VARCHAR",
        "tiv": "VARCHAR",
        "building_value": "VARCHAR",
        "contents_value": "VARCHAR",
        "square_footage": "VARCHAR",
        "location_count": "VARCHAR",
        "liquor_sales": "VARCHAR",
        "alcohol_sales": "VARCHAR",
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
                # LOSSQ_POLICY_SCHEDULE_EXPOSURE_RETURN_FIELDS_V2
                "limit": clean_value(item.get("limit") or item.get("policy_limit") or item.get("policyLimit") or ""),
                "policy_limit": clean_value(item.get("policy_limit") or item.get("policyLimit") or item.get("limit") or ""),
                "policyLimit": clean_value(item.get("policyLimit") or item.get("policy_limit") or item.get("limit") or ""),
                "premium": clean_value(item.get("premium") or ""),
                "revenue": clean_value(item.get("revenue") or ""),
                "employees": clean_value(item.get("employees") or item.get("employee_count") or item.get("employeeCount") or ""),
                "employee_count": clean_value(item.get("employee_count") or item.get("employeeCount") or item.get("employees") or ""),
                "employeeCount": clean_value(item.get("employeeCount") or item.get("employee_count") or item.get("employees") or ""),
                "physicians": clean_value(item.get("physicians") or item.get("physician_count") or item.get("physicianCount") or ""),
                "physician_count": clean_value(item.get("physician_count") or item.get("physicianCount") or item.get("physicians") or ""),
                "physicianCount": clean_value(item.get("physicianCount") or item.get("physician_count") or item.get("physicians") or ""),
                "claim_count": int(float(item.get("claim_count") or item.get("claims") or 0)),
                "total_incurred": safe_money(item.get("total_incurred") or item.get("incurred")),
            }
        )

    return safe_policies


# LOSSQ_ACCOUNT_PROFILE_ACCOUNT_NUMBER_POLICY_SANITIZER_V1


# LOSSQ_ACCOUNT_PROFILE_TRUE_ACCOUNT_IDENTIFIER_V1
def lossq_account_profile_is_true_account_identifier(value):
    text = str(value or "").strip().upper()
    if not text:
        return False
    return bool(
        re.search(r"\b(ACCT|ACCOUNT|CUST|CUSTOMER|CLIENT)\b", text)
        or re.search(r"[-_ ](ACCT|ACCOUNT|CUST|CUSTOMER|CLIENT)[-_ ]", text)
    )

def lossq_account_profile_looks_like_policy_number(value):
    value = str(value or "").strip().upper()
    if not value:
        return False
    return False if lossq_account_profile_is_true_account_identifier(value) else bool(re.search(r"\b[A-Z]{1,8}[- ]?\d{2,6}[- ]?[A-Z0-9]{2,12}\b", value))


def lossq_account_profile_clean_account_number(value):
    # LOSSQ_ACCOUNT_PROFILE_TRUE_ACCOUNT_NUMBER_CLEANER_V1
    clean = clean_value(value)
    if not clean:
        return ""

    compact = re.sub(r"[^A-Z0-9]+", "", clean.upper())

    true_account_signal = any(token in compact for token in [
        "ACCT",
        "ACCOUNT",
        "CUSTOMER",
        "CLIENT",
        "CUST",
    ])

    if true_account_signal:
        return clean

    if lossq_account_profile_looks_like_policy_number(clean):
        return ""

    return clean


# LOSSQ_ACCOUNT_PROFILE_ALL_ROUTE_V1
def lossq_account_profile_to_dict(profile):
    policies = parse_json_value(getattr(profile, "policies", None), [])
    validation = parse_json_value(getattr(profile, "validation", None), {})

    # LOSSQ_PROFILE_TO_DICT_EXPOSURE_BASIS_FALLBACK_V1
    exposure_basis_value = clean_value(getattr(profile, "exposure_basis", ""))

    def lossq_extract_from_exposure_basis_v1(label: str) -> str:
        if not exposure_basis_value:
            return ""
        match = re.search(rf"{re.escape(label)}\s*:\s*([^|]+)", exposure_basis_value, re.IGNORECASE)
        if not match:
            return ""
        return clean_value(match.group(1)).replace(",", "")

    location_count_value = (
        clean_value(getattr(profile, "location_count", ""))
        or clean_value(getattr(profile, "locations", ""))
        or clean_value(getattr(profile, "locationCount", ""))
        or lossq_extract_from_exposure_basis_v1("Locations")
        or lossq_extract_from_exposure_basis_v1("Location Count")
    )

    liquor_sales_value = (
        clean_value(getattr(profile, "liquor_sales", ""))
        or clean_value(getattr(profile, "liquorSales", ""))
        or clean_value(getattr(profile, "alcohol_sales", ""))
        or lossq_extract_from_exposure_basis_v1("Liquor Sales")
        or lossq_extract_from_exposure_basis_v1("Alcohol Sales")
    )

    return {
        "id": getattr(profile, "id", None),
        "business_name": clean_value(getattr(profile, "business_name", "")),
        "insured": clean_value(getattr(profile, "business_name", "")),
        "named_insured": clean_value(getattr(profile, "business_name", "")),
        "carrier_name": clean_value(getattr(profile, "carrier_name", "")),
        "writing_carrier": clean_value(getattr(profile, "writing_carrier", "") or getattr(profile, "carrier_name", "")),
        "agency_name": clean_value(getattr(profile, "agency_name", "")),
        "account_number": lossq_account_profile_clean_account_number(getattr(profile, "account_number", "")),
        "customer_number": lossq_account_profile_clean_account_number(getattr(profile, "customer_number", "")),
        "producer_number": clean_value(getattr(profile, "producer_number", "")),
        "policy_number": clean_value(getattr(profile, "policy_number", "")),
        "effective_date": clean_value(getattr(profile, "effective_date", "")),
        "expiration_date": clean_value(getattr(profile, "expiration_date", "")),
        "evaluation_date": clean_value(getattr(profile, "evaluation_date", "")),
        "line_of_business": clean_value(getattr(profile, "line_of_business", "")),
        "current_premium": clean_value(getattr(profile, "current_premium", "")),
        "expiring_premium": clean_value(getattr(profile, "expiring_premium", "")),
        "target_renewal_premium": clean_value(getattr(profile, "target_renewal_premium", "")),
        "state": clean_value(getattr(profile, "state", "")),
        "class_code": clean_value(getattr(profile, "class_code", "")),
        "class_codes": clean_value(getattr(profile, "class_codes", "")),
        "payroll": clean_value(getattr(profile, "payroll", "")),
        "revenue": clean_value(getattr(profile, "revenue", "")),
        "sales": clean_value(getattr(profile, "sales", "")),
        "employee_count": clean_value(getattr(profile, "employee_count", "")),
        # LOSSQ_ACCOUNT_PROFILE_EXPOSURE_RESPONSE_ALIASES_V2
        "employeeCount": clean_value(getattr(profile, "employee_count", "")),
        "Employee Count": clean_value(getattr(profile, "employee_count", "")),
        "physician_count": clean_value(getattr(profile, "physician_count", "")),
        "physicianCount": clean_value(getattr(profile, "physician_count", "")),
        "physicians": clean_value(getattr(profile, "physician_count", "")),
        "Physician Count": clean_value(getattr(profile, "physician_count", "")),
        "limits": clean_value(getattr(profile, "limits", "")),
        "coverage_limit": clean_value(getattr(profile, "coverage_limit", "")),
        "coverageLimit": clean_value(getattr(profile, "coverage_limit", "")),
        "policy_limits": clean_value(getattr(profile, "coverage_limit", "") or getattr(profile, "limits", "")),
        "policyLimits": clean_value(getattr(profile, "coverage_limit", "") or getattr(profile, "limits", "")),
        "Policy Limits": clean_value(getattr(profile, "coverage_limit", "") or getattr(profile, "limits", "")),
        "lineOfBusiness": clean_value(getattr(profile, "line_of_business", "")),
        "primary_line_of_business": clean_value(getattr(profile, "line_of_business", "")),
        "primaryLineOfBusiness": clean_value(getattr(profile, "line_of_business", "")),
        "vehicle_count": clean_value(getattr(profile, "vehicle_count", "")),
        "driver_count": clean_value(getattr(profile, "driver_count", "")),
        "property_tiv": clean_value(getattr(profile, "property_tiv", "")),
        "tiv": clean_value(getattr(profile, "tiv", "")),
        "building_value": clean_value(getattr(profile, "building_value", "")),
        "contents_value": clean_value(getattr(profile, "contents_value", "")),
        "square_footage": clean_value(getattr(profile, "square_footage", "")),
        "location_count": location_count_value,
        "locations": location_count_value,
        "locationCount": location_count_value,
        # LOSSQ_ACCOUNT_PROFILE_EXPOSURE_INPUTS_RESPONSE_OBJECT_V2
        "exposure_inputs": {
            "primary_line_of_business": clean_value(getattr(profile, "line_of_business", "")),
            "primaryLineOfBusiness": clean_value(getattr(profile, "line_of_business", "")),
            "line_of_business": clean_value(getattr(profile, "line_of_business", "")),
            "lineOfBusiness": clean_value(getattr(profile, "line_of_business", "")),
            "policy_limits": clean_value(getattr(profile, "coverage_limit", "") or getattr(profile, "limits", "")),
            "policyLimits": clean_value(getattr(profile, "coverage_limit", "") or getattr(profile, "limits", "")),
            "Policy Limits": clean_value(getattr(profile, "coverage_limit", "") or getattr(profile, "limits", "")),
            "coverage_limit": clean_value(getattr(profile, "coverage_limit", "")),
            "coverageLimit": clean_value(getattr(profile, "coverage_limit", "")),
            "limits": clean_value(getattr(profile, "limits", "")),
            "physician_count": clean_value(getattr(profile, "physician_count", "")),
            "physicianCount": clean_value(getattr(profile, "physician_count", "")),
            "physicians": clean_value(getattr(profile, "physician_count", "")),
            "Physician Count": clean_value(getattr(profile, "physician_count", "")),
            "employee_count": clean_value(getattr(profile, "employee_count", "")),
            "employeeCount": clean_value(getattr(profile, "employee_count", "")),
            "current_premium": clean_value(getattr(profile, "current_premium", "")),
            "currentPremium": clean_value(getattr(profile, "current_premium", "")),
            "expiring_premium": clean_value(getattr(profile, "expiring_premium", "")),
            "expiringPremium": clean_value(getattr(profile, "expiring_premium", "")),
            "revenue": clean_value(getattr(profile, "revenue", "")),
            "professional_revenue": clean_value(getattr(profile, "revenue", "")),
            "professionalRevenue": clean_value(getattr(profile, "revenue", "")),
        },
        "exposureInputs": {
            "primary_line_of_business": clean_value(getattr(profile, "line_of_business", "")),
            "policy_limits": clean_value(getattr(profile, "coverage_limit", "") or getattr(profile, "limits", "")),
            "policyLimits": clean_value(getattr(profile, "coverage_limit", "") or getattr(profile, "limits", "")),
            "coverage_limit": clean_value(getattr(profile, "coverage_limit", "")),
            "coverageLimit": clean_value(getattr(profile, "coverage_limit", "")),
            "physician_count": clean_value(getattr(profile, "physician_count", "")),
            "physicianCount": clean_value(getattr(profile, "physician_count", "")),
            "physicians": clean_value(getattr(profile, "physician_count", "")),
        },
        "liquor_sales": liquor_sales_value,
        "liquorSales": liquor_sales_value,
        "alcohol_sales": liquor_sales_value,
        "unit_count": clean_value(getattr(profile, "unit_count", "")),
        "cargo_limit": clean_value(getattr(profile, "cargo_limit", "")),
        "umbrella_limit": clean_value(getattr(profile, "umbrella_limit", "")),
        "experience_mod": clean_value(getattr(profile, "experience_mod", "")),
        "mod": clean_value(getattr(profile, "mod", "")),
        "exposure_change_percent": clean_value(getattr(profile, "exposure_change_percent", "")),
        "cyber_revenue": clean_value(getattr(profile, "cyber_revenue", "")),
        "professional_revenue": clean_value(getattr(profile, "professional_revenue", "")),
        "exposure_basis": exposure_basis_value,
        "underwriter_notes": clean_value(getattr(profile, "underwriter_notes", "")),
        "policies": normalize_policy_list(policies),
        "validation": validation if isinstance(validation, dict) else {},
        "raw_text_preview": clean_value(getattr(profile, "raw_text_preview", "")),
        "created_at": str(getattr(profile, "created_at", "") or ""),
        "updated_at": str(getattr(profile, "updated_at", "") or ""),
    }



# LOSSQ_ACCOUNT_PROFILE_ROOT_PUT_SAVE_ROUTE_V1
@router.put("")
@router.put("/")
def save_account_profile_root(payload: AccountProfileUpdate, current_user: dict = Depends(get_current_user)):
    """
    Persistent save endpoint used by the dashboard.
    Fixes frontend PUT /account-profile/ returning 404 and causing uploaded profiles
    to disappear after refresh/logout.
    """
    db = SessionLocal()
    try:
        ensure_account_profile_columns(db)

        organization_id = current_user.get("organization_id") if isinstance(current_user, dict) else None
        if organization_id is None:
            raise HTTPException(status_code=400, detail="Organization is required to save account profile.")

        data = payload.dict() if hasattr(payload, "dict") else {}
        data = data if isinstance(data, dict) else {}

        def clean_local(value):
            return re.sub(r"\\s+", " ", str(value or "").replace("\\ufeff", "").strip()).strip(" :-|/")

        def slug_local(value):
            value = clean_local(value).upper()
            value = re.sub(r"[^A-Z0-9]+", "-", value).strip("-")
            value = re.sub(r"-+", "-", value)
            return value[:90]

        profile_id = data.get("id")

        policy_number = clean_local(
            data.get("policy_number")
            or data.get("main_policy")
            or data.get("main_policy_number")
        )

        if not policy_number:
            policy_numbers = data.get("policy_numbers")
            if isinstance(policy_numbers, list):
                for item in policy_numbers:
                    candidate = clean_local(item)
                    if candidate:
                        policy_number = candidate
                        break

        if not policy_number:
            policies = data.get("policies") or data.get("policy_schedule") or []
            if isinstance(policies, list):
                for item in policies:
                    if isinstance(item, dict):
                        candidate = clean_local(item.get("policy_number") or item.get("policy") or item.get("number"))
                    else:
                        candidate = clean_local(item)

                    if candidate:
                        policy_number = candidate
                        break

        if not policy_number:
            account_key = clean_local(
                data.get("account_number")
                or data.get("customer_number")
                or data.get("client_number")
                or data.get("producer_number")
            )
            if account_key:
                policy_number = account_key

        if not policy_number:
            business_key = slug_local(
                data.get("business_name")
                or data.get("named_insured")
                or data.get("insured_name")
                or data.get("account_name")
                or data.get("company_name")
            )
            carrier_key = slug_local(data.get("carrier_name") or data.get("writing_carrier") or data.get("insurer"))

            if business_key and carrier_key:
                policy_number = f"ACCOUNT-{business_key}-{carrier_key}"
            elif business_key:
                policy_number = f"ACCOUNT-{business_key}"

        if not policy_number:
            raise HTTPException(status_code=400, detail="A policy number, account number, or business name is required to save this profile.")

        query = db.query(AccountProfile)

        if profile_id:
            profile = (
                query
                .filter(AccountProfile.id == profile_id)
                .filter(AccountProfile.organization_id == organization_id)
                .first()
            )
        else:
            profile = (
                query
                .filter(AccountProfile.organization_id == organization_id)
                .filter(AccountProfile.policy_number == policy_number)
                .first()
            )

        if profile is None:
            profile = AccountProfile(
                organization_id=organization_id,
                policy_number=policy_number,
            )
            db.add(profile)

        data["policy_number"] = data.get("policy_number") or policy_number
        data["main_policy"] = data.get("main_policy") or policy_number
        data["main_policy_number"] = data.get("main_policy_number") or policy_number

        save_fields = [
            "business_name",
            "carrier_name",
            "writing_carrier",
            "agency_name",
            "account_number",
            "customer_number",
            "producer_number",
            "policy_number",
            "effective_date",
            "expiration_date",
            "evaluation_date",
            "line_of_business",
            "state",
            "class_code",
            "class_codes",
            "limits",
            "coverage_limit",
            "deductible",
            "exposure_basis",
            "current_premium",
            "expiring_premium",
            "target_renewal_premium",
            "payroll",
            "revenue",
            "sales",
            "receipts",
            "employee_count",
            "physician_count",
            "vehicle_count",
            "driver_count",
            "property_tiv",
            "tiv",
            "building_value",
            "contents_value",
            "square_footage",
            "location_count",
            "underwriter_notes",
            "raw_text_preview",
            "policies",
            "validation",
        ]

        for field in save_fields:
            if not hasattr(profile, field):
                continue

            value = data.get(field)

            if field == "policies":
                value = serialize_json(value, [])

            if field == "validation":
                value = serialize_json(value, {})

            if value not in (None, ""):
                setattr(profile, field, value)

        db.commit()
        db.refresh(profile)

        record_audit_event(
            db,
            current_user=current_user,
            action="account_profile_saved",
            resource_type="account_profile",
            resource_id=str(getattr(profile, "id", "")),
            details={
                "profile_id": getattr(profile, "id", None),
                "policy_number": getattr(profile, "policy_number", ""),
                "business_name": getattr(profile, "business_name", ""),
            },
        )

        return lossq_account_profile_to_dict(profile)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Account profile save failed: {str(exc)}")
    finally:
        db.close()


# LOSSQ_ACCOUNT_PROFILE_ROOT_GET_ROUTE_V1
@router.get("")
@router.get("/")
def get_account_profile_root(current_user: dict = Depends(get_current_user)):
    """
    Safe root profile read endpoint for dashboard calls to /account-profile/.
    Prevents 405 while /account-profile/all remains the profile-list source.
    """
    db = SessionLocal()
    try:
        ensure_account_profile_columns(db)

        organization_id = current_user.get("organization_id") if isinstance(current_user, dict) else None
        query = db.query(AccountProfile)

        if organization_id is not None:
            query = query.filter(AccountProfile.organization_id == organization_id)

        profile = query.order_by(AccountProfile.id.desc()).first()

        if not profile:
            return {}

        return lossq_account_profile_to_dict(profile)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Account profile read failed: {str(exc)}")
    finally:
        db.close()

@router.get("/all")
def list_account_profiles(current_user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        ensure_account_profile_columns(db)

        organization_id = current_user.get("organization_id") if isinstance(current_user, dict) else None

        query = db.query(AccountProfile)

        if organization_id is not None:
            query = query.filter(AccountProfile.organization_id == organization_id)

        profiles = query.order_by(AccountProfile.id.desc()).all()
        profile_rows = [lossq_account_profile_to_dict(profile) for profile in profiles]

        if profile_rows:
            return profile_rows

        # LOSSQ_ACCOUNT_PROFILE_ALL_FALLBACK_CLAIMS_UPLOAD_HISTORY_V3
        # If account_profiles is empty, rebuild visible saved profiles from
        # persisted claims first, then upload history. This keeps saved uploads
        # visible after logout/login without relying on browser cache.
        import json as _lossq_json
        import re as _lossq_re

        def _clean(value):
            return str(value or "").strip()

        def _norm(value):
            return _clean(value).upper()

        def _money(value):
            raw = _lossq_re.sub(r"[^0-9.\-]", "", _clean(value).replace(",", ""))

            try:
                return float(raw or 0)
            except Exception:
                return 0.0

        def _looks_blank(value):
            return _norm(value) in {"", "UNKNOWN", "N/A", "NA", "NONE", "NULL", "-"}

        def _as_dict(value):
            if isinstance(value, dict):
                return value

            if isinstance(value, str) and value.strip():
                try:
                    parsed = _lossq_json.loads(value)
                    return parsed if isinstance(parsed, dict) else {}
                except Exception:
                    return {}

            return {}

        def _first_from_object(obj, *names):
            for name in names:
                try:
                    value = getattr(obj, name, "")
                except Exception:
                    value = ""

                if value not in ("", None, [], {}):
                    return value

            return ""

        def _first_from_dict(data, *names):
            data = data if isinstance(data, dict) else {}

            for name in names:
                value = data.get(name)

                if value not in ("", None, [], {}):
                    return value

            return ""

        def _policy_line(policy_number, raw_line):
            policy = _norm(policy_number)
            line = _clean(raw_line)

            if _lossq_re.search(r"(^|[-_\s])(CGL|GL)([-_\s]|$)", policy):
                return "CGL"

            if line.lower() in {
                "bodily injury",
                "property damage",
                "completed ops",
                "completed operations",
                "bi",
                "pd",
            }:
                return "CGL"

            return line

        fallback_profiles = []

        # 1) Claim fallback: best fallback because claims carry real policy numbers.
        try:
            claim_query = db.query(Claim)

            if organization_id is not None and hasattr(Claim, "organization_id"):
                claim_query = claim_query.filter(Claim.organization_id == organization_id)

            claim_rows = claim_query.order_by(Claim.id.desc()).limit(3000).all()

            grouped = {}

            for claim in claim_rows:
                policy_number = _clean(_first_from_object(
                    claim,
                    "policy_number",
                    "policyNumber",
                    "policy_no",
                    "policy",
                ))

                if _looks_blank(policy_number):
                    continue

                key = _norm(policy_number)

                profile = grouped.setdefault(key, {
                    "id": f"claims-fallback-{key}",
                    "profile_id": None,
                    "business_name": "",
                    "insured_name": "",
                    "display_name": "",
                    "account_name": "",
                    "carrier_name": "",
                    "writing_carrier": "",
                    "carrier": "",
                    "policy_number": key,
                    "policyNumber": key,
                    "main_policy": key,
                    "mainPolicy": key,
                    "line_of_business": "",
                    "policy_type": "",
                    "claim_count": 0,
                    "total_claims": 0,
                    "open_claims": 0,
                    "closed_claims": 0,
                    "total_incurred": 0.0,
                    "lossq_claim_fallback_profile": True,
                })

                business_name = _clean(_first_from_object(
                    claim,
                    "business_name",
                    "insured_name",
                    "named_insured",
                    "account_name",
                    "customer_name",
                ))

                if business_name and not profile["business_name"]:
                    profile["business_name"] = business_name
                    profile["insured_name"] = business_name
                    profile["display_name"] = business_name
                    profile["account_name"] = business_name

                carrier_name = _clean(_first_from_object(
                    claim,
                    "carrier_name",
                    "writing_carrier",
                    "carrier",
                ))

                if carrier_name and not profile["carrier_name"]:
                    profile["carrier_name"] = carrier_name
                    profile["writing_carrier"] = carrier_name
                    profile["carrier"] = carrier_name

                line_value = _policy_line(
                    key,
                    _first_from_object(
                        claim,
                        "line_of_business",
                        "policy_type",
                        "coverage",
                        "line",
                        "claim_type",
                    )
                )

                if line_value and not profile["line_of_business"]:
                    profile["line_of_business"] = line_value
                    profile["policy_type"] = line_value

                status = _clean(_first_from_object(claim, "status", "claim_status")).lower()

                profile["claim_count"] += 1
                profile["total_claims"] += 1

                if status == "closed":
                    profile["closed_claims"] += 1
                else:
                    profile["open_claims"] += 1

                profile["total_incurred"] += _money(
                    _first_from_object(
                        claim,
                        "total_incurred",
                        "incurred",
                        "incurred_amount",
                        "total",
                        "loss_amount",
                    )
                )

            for policy_number, profile in grouped.items():
                if not profile["business_name"]:
                    profile["business_name"] = f"Saved profile {policy_number}"
                    profile["insured_name"] = profile["business_name"]
                    profile["display_name"] = profile["business_name"]
                    profile["account_name"] = profile["business_name"]

                policy_row = {
                    "policy_number": policy_number,
                    "policyNumber": policy_number,
                    "line_of_business": profile.get("line_of_business") or "",
                    "lineOfBusiness": profile.get("line_of_business") or "",
                    "policy_type": profile.get("policy_type") or profile.get("line_of_business") or "",
                    "policyType": profile.get("policy_type") or profile.get("line_of_business") or "",
                    "coverage": profile.get("line_of_business") or "",
                    "carrier": profile.get("carrier_name") or "",
                    "carrier_name": profile.get("carrier_name") or "",
                    "claim_count": profile.get("claim_count") or 0,
                    "claims": profile.get("claim_count") or 0,
                    "total_incurred": profile.get("total_incurred") or 0,
                }

                profile["policies"] = [policy_row]
                profile["policy_schedule"] = [policy_row]
                profile["policySchedule"] = [policy_row]

                fallback_profiles.append(profile)

            if fallback_profiles:
                print("LOSSQ_ACCOUNT_PROFILE_ALL_FALLBACK_CLAIMS_UPLOAD_HISTORY_V3_CLAIMS", {
                    "organization_id": organization_id,
                    "profiles": len(fallback_profiles),
                })
                return fallback_profiles

        except Exception as claim_fallback_exc:
            print("LOSSQ_ACCOUNT_PROFILE_ALL_FALLBACK_CLAIMS_UPLOAD_HISTORY_V3_CLAIMS_ERROR", str(claim_fallback_exc)[:500])

        # 2) Upload history fallback: keeps uploaded files visible even if profile rows were not created.
        try:
            history_query = db.query(UploadHistory)

            if organization_id is not None and hasattr(UploadHistory, "organization_id"):
                history_query = history_query.filter(UploadHistory.organization_id == organization_id)

            history_rows = history_query.order_by(UploadHistory.id.desc()).limit(300).all()

            history_profiles = []

            for item in history_rows:
                metadata = {}

                for meta_name in [
                    "metadata",
                    "profile",
                    "profile_data",
                    "parsed_profile",
                    "account_profile",
                    "result",
                    "response",
                    "validation",
                ]:
                    metadata = _as_dict(_first_from_object(item, meta_name))

                    if metadata:
                        break

                policy_number = _clean(
                    _first_from_object(
                        item,
                        "policy_number",
                        "policyNumber",
                        "main_policy",
                        "mainPolicy",
                    )
                    or _first_from_dict(
                        metadata,
                        "policy_number",
                        "policyNumber",
                        "main_policy",
                        "mainPolicy",
                    )
                )

                filename = _clean(_first_from_object(
                    item,
                    "filename",
                    "file_name",
                    "fileName",
                    "original_filename",
                    "originalFilename",
                    "name",
                ))

                row_id = _clean(_first_from_object(item, "id")) or str(len(history_profiles) + 1)

                if _looks_blank(policy_number):
                    policy_number = f"UPLOAD-{row_id}"

                business_name = _clean(
                    _first_from_object(
                        item,
                        "business_name",
                        "businessName",
                        "insured_name",
                        "insuredName",
                        "account_name",
                        "accountName",
                    )
                    or _first_from_dict(
                        metadata,
                        "business_name",
                        "businessName",
                        "insured_name",
                        "insuredName",
                        "account_name",
                        "accountName",
                    )
                    or filename
                    or f"Saved upload {row_id}"
                )

                carrier_name = _clean(
                    _first_from_object(
                        item,
                        "carrier_name",
                        "carrierName",
                        "writing_carrier",
                        "writingCarrier",
                        "carrier",
                    )
                    or _first_from_dict(
                        metadata,
                        "carrier_name",
                        "carrierName",
                        "writing_carrier",
                        "writingCarrier",
                        "carrier",
                    )
                )

                line_value = _policy_line(
                    policy_number,
                    _first_from_object(
                        item,
                        "line_of_business",
                        "lineOfBusiness",
                        "policy_type",
                        "policyType",
                        "coverage",
                        "line",
                    )
                    or _first_from_dict(
                        metadata,
                        "line_of_business",
                        "lineOfBusiness",
                        "policy_type",
                        "policyType",
                        "coverage",
                        "line",
                    )
                )

                policy_row = {
                    "policy_number": policy_number,
                    "policyNumber": policy_number,
                    "line_of_business": line_value,
                    "lineOfBusiness": line_value,
                    "policy_type": line_value,
                    "policyType": line_value,
                    "coverage": line_value,
                    "carrier": carrier_name,
                    "carrier_name": carrier_name,
                    "claim_count": _first_from_object(item, "saved_claims", "saved_claim_count", "claim_count") or 0,
                    "claims": _first_from_object(item, "saved_claims", "saved_claim_count", "claim_count") or 0,
                    "total_incurred": _first_from_object(item, "total_incurred", "incurred") or 0,
                }

                history_profiles.append({
                    **metadata,
                    "id": f"upload-history-{row_id}",
                    "business_name": business_name,
                    "insured_name": business_name,
                    "display_name": business_name,
                    "account_name": business_name,
                    "carrier_name": carrier_name,
                    "writing_carrier": carrier_name,
                    "carrier": carrier_name,
                    "policy_number": policy_number,
                    "policyNumber": policy_number,
                    "main_policy": policy_number,
                    "mainPolicy": policy_number,
                    "line_of_business": line_value,
                    "policy_type": line_value,
                    "policies": [policy_row],
                    "policy_schedule": [policy_row],
                    "policySchedule": [policy_row],
                    "filename": filename,
                    "uploaded_filename": filename,
                    "lossq_upload_history_fallback_profile": True,
                })

            if history_profiles:
                print("LOSSQ_ACCOUNT_PROFILE_ALL_FALLBACK_CLAIMS_UPLOAD_HISTORY_V3_HISTORY", {
                    "organization_id": organization_id,
                    "profiles": len(history_profiles),
                })
                return history_profiles

        except Exception as history_fallback_exc:
            print("LOSSQ_ACCOUNT_PROFILE_ALL_FALLBACK_CLAIMS_UPLOAD_HISTORY_V3_HISTORY_ERROR", str(history_fallback_exc)[:500])

        return []
    finally:
        db.close()


@router.get("/policy/{policy_number}")
def get_account_profile_by_policy(policy_number: str, current_user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        ensure_account_profile_columns(db)

        organization_id = current_user.get("organization_id") if isinstance(current_user, dict) else None
        key = clean_value(policy_number)

        query = db.query(AccountProfile)
        if organization_id is not None:
            query = query.filter(AccountProfile.organization_id == organization_id)

        profiles = query.all()

        for profile in profiles:
            profile_keys = [
                clean_value(getattr(profile, "policy_number", "")),
                clean_value(getattr(profile, "account_number", "")),
                clean_value(getattr(profile, "customer_number", "")),
            ]

            for policy in normalize_policy_list(getattr(profile, "policies", None)):
                profile_keys.append(clean_value(policy.get("policy_number", "")))

            if key and key.upper() in {item.upper() for item in profile_keys if item}:
                return lossq_account_profile_to_dict(profile)

        raise HTTPException(status_code=404, detail="Account profile not found")
    finally:
        db.close()


# LOSSQ_PERSISTENT_ACCOUNT_PROFILE_DELETE_BY_ID_V4_SINGLE_ROUTE
@router.delete("/id/{profile_id}")
def delete_account_profile_by_id(
    profile_id: int,
    delete_claims: bool = False,
    current_user: dict = Depends(get_current_user),
):
    """
    Permanently deletes an account profile for the current organization.
    This is the only active /account-profile/id/{profile_id} delete route.
    Claim cleanup is best-effort and cannot block profile deletion.
    """
    db = SessionLocal()
    try:
        ensure_account_profile_columns(db)

        organization_id = current_user.get("organization_id") if isinstance(current_user, dict) else None

        query = db.query(AccountProfile).filter(AccountProfile.id == profile_id)

        if organization_id is not None and hasattr(AccountProfile, "organization_id"):
            query = query.filter(AccountProfile.organization_id == organization_id)

        profile = query.first()

        if not profile:
            return {
                "ok": True,
                "deleted": False,
                "already_deleted": True,
                "profile_id": profile_id,
            }

        policy_number = clean_value(getattr(profile, "policy_number", ""))
        business_name = clean_value(getattr(profile, "business_name", ""))
        account_number = lossq_account_profile_clean_account_number(getattr(profile, "account_number", ""))
        customer_number = lossq_account_profile_clean_account_number(getattr(profile, "customer_number", ""))

        policy_numbers = set()
        for value in [policy_number]:
            if value:
                policy_numbers.add(value)

        try:
            for policy in normalize_policy_list(getattr(profile, "policies", None)):
                child_policy = clean_value(policy.get("policy_number", ""))
                if child_policy:
                    policy_numbers.add(child_policy)
        except Exception as policy_exc:
            print("LOSSQ_PROFILE_DELETE_POLICY_LIST_PARSE_WARNING:", str(policy_exc)[:500])

        # Delete the profile first so it cannot reappear in Saved Profiles after refresh.
        db.delete(profile)
        db.commit()

        claims_deleted = 0
        claim_cleanup_error = ""

        if delete_claims:
            try:
                claim_query = db.query(Claim)

                if organization_id is not None and hasattr(Claim, "organization_id"):
                    claim_query = claim_query.filter(Claim.organization_id == organization_id)

                if policy_numbers:
                    claims_deleted += (
                        claim_query
                        .filter(Claim.policy_number.in_(list(policy_numbers)))
                        .delete(synchronize_session=False)
                    )

                db.commit()
            except Exception as claim_exc:
                db.rollback()
                claim_cleanup_error = str(claim_exc)[:500]
                print("LOSSQ_PROFILE_DELETE_CLAIM_CLEANUP_WARNING:", claim_cleanup_error)

        return {
            "ok": True,
            "deleted": True,
            "profile_id": profile_id,
            "business_name": business_name,
            "account_number": account_number,
            "customer_number": customer_number,
            "policy_number": policy_number,
            "policy_numbers": list(policy_numbers),
            "claims_deleted": claims_deleted,
            "claim_cleanup_error": claim_cleanup_error,
        }

    except Exception as exc:
        db.rollback()
        print("LOSSQ_PROFILE_DELETE_ROUTE_ERROR:", str(exc)[:1000])
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Profile delete failed.",
                "error": str(exc)[:300],
            },
        )
    finally:
        db.close()
