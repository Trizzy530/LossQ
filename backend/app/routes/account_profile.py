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
