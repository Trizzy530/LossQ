from fastapi import APIRouter, UploadFile, File, Depends, Form
from sqlalchemy.orm import Session
from sqlalchemy import text, inspect
import shutil
import os
import json
from datetime import datetime
from typing import List, Any

from app.database import SessionLocal
from app.models.claim import Claim
from app.models.upload_history import UploadHistory
from app.models.account_profile import AccountProfile
from app.role_utils import require_permission
from app.services.audit import record_audit_event
from app.services.loss_run_pipeline import parse_loss_run_file
from app.services.universal_profile import extract_universal_profile_from_text

try:
    from app.services.excel_parser_service import parse_claims_from_excel
except Exception:
    parse_claims_from_excel = None


router = APIRouter(prefix="/upload", tags=["Upload"])

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()



def extract_exposure_inputs_from_raw_text(raw_text: str):
    # LOSSQ_RAW_TEXT_EXPOSURE_INPUT_EXTRACTOR_V1
    # Fallback extractor for clean commercial loss runs with labeled exposure/premium fields.
    import re

    text_value = str(raw_text or "")
    profile = {}

    def clean_value(value):
        value = str(value or "").strip()
        value = re.sub(r"\s+", " ", value)
        value = value.strip(" :|-")
        return value

    def find_value(labels, money=False, percent=False):
        for label in labels:
            if money:
                pattern = rf"{label}\s*[:\-]?\s*(\$?\s*[0-9][0-9,]*(?:\.\d{{2}})?)"
            elif percent:
                pattern = rf"{label}\s*[:\-]?\s*([0-9]+(?:\.\d+)?\s*%?)"
            else:
                pattern = rf"{label}\s*[:\-]?\s*([A-Za-z0-9$%,./#&()\- ]{{1,80}})"

            match = re.search(pattern, text_value, re.IGNORECASE)
            if match:
                value = clean_value(match.group(1))
                if value:
                    return value

        return ""

    mappings = {
        "current_premium": (["Current Premium", "Current Term Premium", "Total Current Premium", "Premium Current"], True, False),
        "expiring_premium": (["Expiring Premium", "Prior Premium", "Prior Term Premium", "Expiring Term Premium"], True, False),
        "target_renewal_premium": (["Target Renewal Premium", "Renewal Target Premium", "Projected Renewal Premium"], True, False),
        "payroll": (["Payroll", "Annual Payroll", "Estimated Payroll"], True, False),
        "revenue": (["Revenue", "Annual Revenue", "Gross Revenue", "Estimated Revenue"], True, False),
        "sales": (["Sales", "Annual Sales", "Gross Sales"], True, False),
        "receipts": (["Receipts", "Gross Receipts", "Annual Receipts"], True, False),
        "property_tiv": (["Property TIV", "Total Insured Value", "TIV"], True, False),
        "tiv": (["TIV", "Total Insured Value"], True, False),
        "building_value": (["Building Value", "Building Limit"], True, False),
        "contents_value": (["Contents Value", "Business Personal Property", "BPP"], True, False),
        "vehicle_count": (["Vehicle Count", "Number of Vehicles", "Vehicles"], False, False),
        "driver_count": (["Driver Count", "Number of Drivers", "Drivers"], False, False),
        "employee_count": (["Employee Count", "Number of Employees", "Employees"], False, False),
        "location_count": (["Location Count", "Number of Locations", "Locations"], False, False),
        "unit_count": (["Unit Count", "Units"], False, False),
        "square_footage": (["Square Footage", "Sq Ft", "Building Square Footage"], False, False),
        "coverage_limit": (["Coverage Limit", "Policy Limit", "Limit"], True, False),
        "limits": (["Limits", "Liability Limits"], False, False),
        "deductible": (["Deductible", "Property Deductible", "Collision Deductible"], True, False),
        "retention": (["Retention", "SIR", "Self Insured Retention"], True, False),
        "cargo_limit": (["Cargo Limit", "Motor Truck Cargo Limit"], True, False),
        "umbrella_limit": (["Umbrella Limit", "Excess Limit"], True, False),
        "experience_mod": (["Experience Mod", "Experience Modification", "EMR", "MOD"], False, False),
        "mod": (["MOD", "Experience Mod", "EMR"], False, False),
        "exposure_change_percent": (["Exposure Change", "Exposure Change Percent", "Exposure Change %"], False, True),
        "class_code": (["Class Code", "Primary Class Code"], False, False),
        "class_codes": (["Class Codes", "Classification Codes"], False, False),
        "line_of_business": (["Line of Business", "Coverage Line", "LOB"], False, False),
        "state": (["State", "Primary State", "Governing State"], False, False),
        "exposure_basis": (["Exposure Basis", "Rating Basis"], False, False),
    }

    for field, config in mappings.items():
        labels, money, percent = config
        value = find_value(labels, money=money, percent=percent)
        if value:
            profile[field] = value

    return profile



def parse_file(file_path: str, filename: str):
    lower_name = str(filename or "").lower()

    if lower_name.endswith(".pdf"):
        result = parse_loss_run_file(file_path, filename)

        profile = result.get("profile") or {}
        policies = result.get("policies") or []
        claims = result.get("claims") or []
        validation = result.get("validation") or {}

        raw_text_preview = result.get("raw_text_preview", "")[:50000]
        profile = extract_universal_profile_from_text(
            raw_text=raw_text_preview,
            existing_profile=profile,
            claims=claims,
            filename=filename,
        )

        raw_exposure_inputs = extract_exposure_inputs_from_raw_text(raw_text_preview)
        for exposure_field, exposure_value in raw_exposure_inputs.items():
            if exposure_value not in ("", None, [], {}):
                profile[exposure_field] = profile.get(exposure_field) or exposure_value

        profile["policies"] = merge_policy_lists_for_upload(
            profile.get("policies"),
            policies,
        )
        profile["validation"] = validation
        profile["raw_text_preview"] = raw_text_preview

        return claims, profile

    if lower_name.endswith(".csv") or lower_name.endswith(".xlsx"):
        if parse_claims_from_excel:
            claims = parse_claims_from_excel(file_path)
            return claims, {}

        return [], {}

    return [], {}


def parse_date(value: Any):
    if not value:
        return None

    if isinstance(value, datetime):
        return value.date().isoformat()

    raw = str(value).strip()

    if not raw or raw.lower() in ["needs review", "not set", "none", "nan"]:
        return None

    formats = ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%m-%d-%y"]

    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except Exception:
            pass

    return raw


def days_between(start_value: Any, end_value: Any):
    start = parse_date(start_value)
    end = parse_date(end_value)

    if not start:
        return None

    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end) if end else datetime.now()
        return max((end_dt - start_dt).days, 0)
    except Exception:
        return None


def pick(data: dict, keys: list[str], default=None):
    for key in keys:
        if key in data and data[key] not in [None, "", "Needs Review", "Not Set"]:
            return data[key]

    return default


def clean_profile_value(value):
    if value is None:
        return ""

    cleaned = str(value).strip()

    if cleaned.lower() in ["", "none", "nan", "needs review", "not set"]:
        return ""

    return cleaned



def is_bad_policy_key_for_upload(value: Any):
    cleaned = clean_profile_value(value).upper().replace(" ", "").strip()

    if not cleaned:
        return True

    bad_values = {
        "LINE-COVERAGE",
        "LINECOVERAGE",
        "POLICY",
        "POLICYNUMBER",
        "POLICY-NUMBER",
        "ACCOUNTNUMBER",
        "ACCOUNT-NUMBER",
        "EXPOSUREBASIS",
        "EXPOSURE-BASIS",
        "CURRENT-PREMIUM",
        "EXPIRING-PREMIUM",
        "TARGET-RENEWAL",
        "TARGETRENEWAL",
    }

    if cleaned in bad_values:
        return True

    if "COVERAGE" in cleaned and not any(ch.isdigit() for ch in cleaned):
        return True

    return False


def choose_upload_account_key(profile_data: dict, direct_profile: dict | None = None):
    direct_profile = direct_profile or {}
    candidates = [
        profile_data.get("account_number"),
        profile_data.get("customer_number"),
        direct_profile.get("account_number"),
        direct_profile.get("customer_number"),
        profile_data.get("policy_number"),
        direct_profile.get("policy_number"),
    ]

    for candidate in candidates:
        cleaned = clean_profile_value(candidate)
        if cleaned and not is_bad_policy_key_for_upload(cleaned):
            return cleaned

    policies = profile_data.get("policies") if isinstance(profile_data.get("policies"), list) else []
    for item in policies:
        if not isinstance(item, dict):
            continue
        cleaned = clean_profile_value(item.get("policy_number"))
        if cleaned and not is_bad_policy_key_for_upload(cleaned):
            return cleaned

    return ""


def merge_policy_lists_for_upload(*policy_lists):
    merged = {}

    for policy_list in policy_lists:
        if not isinstance(policy_list, list):
            continue

        for item in policy_list:
            if not isinstance(item, dict):
                continue

            key = clean_profile_value(
                item.get("policy_number") or item.get("policy") or item.get("number")
            ).upper()

            if not key or is_bad_policy_key_for_upload(key):
                key = clean_profile_value(
                    item.get("line_of_business") or item.get("coverage") or item.get("policy_type")
                ).upper()

            if not key:
                continue

            existing = merged.get(key, {})
            combined = dict(existing)

            for field, value in item.items():
                if value not in ("", None) and not combined.get(field):
                    combined[field] = value

            merged[key] = combined

    return list(merged.values())



def ensure_claim_timeline_columns(db: Session):
    required_columns = {
        "date_reported": "VARCHAR",
        "date_closed": "VARCHAR",
        "open_days": "INTEGER",
        "claim_age": "INTEGER",
    }

    try:
        inspector = inspect(db.bind)
        existing_columns = [column["name"] for column in inspector.get_columns("claims")]

        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                db.execute(text(f"ALTER TABLE claims ADD COLUMN {column_name} {column_type}"))

        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Claim timeline column check failed: {e}")

def ensure_account_profile_columns(db: Session):
    required_columns = {
        "writing_carrier": "VARCHAR",
        "account_number": "VARCHAR",
        "customer_number": "VARCHAR",
        "producer_number": "VARCHAR",
        "policies": "TEXT",
        "validation": "TEXT",
        "raw_text_preview": "TEXT",

        # LOSSQ_EXPOSURE_INPUT_FIELDS_V1
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


def normalize_claim_data(raw: dict, fallback_policy_number: str, current_user: dict):
    extracted_policy_number = clean_profile_value(
        pick(raw, ["policy_number", "policy_no", "policy"], "")
    )

    final_policy_number = extracted_policy_number or clean_profile_value(fallback_policy_number)

    date_of_loss = parse_date(
        pick(raw, ["date_of_loss", "loss_date", "date_of_accident", "accident_date"])
    )

    date_reported = parse_date(
        pick(raw, ["date_reported", "reported_date", "report_date"])
    )

    date_closed = parse_date(
        pick(raw, ["date_closed", "closed_date", "closure_date"])
    )

    status = pick(raw, ["status", "claim_status"], "Open")

    open_days = days_between(date_reported or date_of_loss, date_closed)
    claim_age = days_between(date_of_loss, None)

    return {
        "claim_number": pick(raw, ["claim_number", "claim_no", "claim_id"], "Unknown"),
        "policy_id": raw.get("policy_id"),
        "policy_number": final_policy_number,
        "line_of_business": pick(raw, ["line_of_business", "lob", "coverage_line"]),
        "claim_type": pick(raw, ["claim_type", "type"]),
        "cause_of_loss": pick(raw, ["cause_of_loss", "cause"]),
        "claimant_type": pick(raw, ["claimant_type"]),
        "date_of_loss": date_of_loss,
        "date_reported": date_reported,
        "date_closed": date_closed,
        "open_days": open_days,
        "claim_age": claim_age,
        "status": status,
        "description": pick(raw, ["description", "claim_description", "narrative"]),
        "paid_amount": float(pick(raw, ["paid_amount", "paid", "total_paid"], 0) or 0),
        "reserve_amount": float(
            pick(raw, ["reserve_amount", "reserve", "outstanding_reserve"], 0) or 0
        ),
        "total_incurred": float(
            pick(raw, ["total_incurred", "incurred", "total"], 0) or 0
        ),
        "litigation": bool(pick(raw, ["litigation", "is_litigated"], False)),
        "litigation_status": pick(raw, ["litigation_status"]),
        "attorney_assigned": bool(pick(raw, ["attorney_assigned"], False)),
        "suit_filed": bool(pick(raw, ["suit_filed"], False)),
        "venue_state": pick(raw, ["venue_state"]),
        "injury_type": pick(raw, ["injury_type"]),
        "flag": pick(raw, ["flag"]),
        "organization_id": current_user["organization_id"],
        "uploaded_by_user_id": current_user["user_id"],
        "uploaded_at": datetime.now().isoformat(),
    }


def extract_profile_data(
    parsed_claims: list[dict],
    fallback_policy_number: str,
    direct_profile: dict | None = None,
):
    direct_profile = direct_profile or {}

    profile = {
        "business_name": clean_profile_value(direct_profile.get("business_name")),
        "carrier_name": clean_profile_value(direct_profile.get("carrier_name")),
        "writing_carrier": clean_profile_value(
            direct_profile.get("writing_carrier") or direct_profile.get("carrier_name")
        ),
        "agency_name": clean_profile_value(direct_profile.get("agency_name")),
        "account_number": clean_profile_value(
            direct_profile.get("account_number") or direct_profile.get("customer_number")
        ),
        "customer_number": clean_profile_value(
            direct_profile.get("customer_number") or direct_profile.get("account_number")
        ),
        "producer_number": clean_profile_value(direct_profile.get("producer_number")),
        "policy_number": clean_profile_value(
            direct_profile.get("policy_number") or direct_profile.get("account_number")
        ),
        "effective_date": parse_date(direct_profile.get("effective_date")) or "",
        "expiration_date": parse_date(direct_profile.get("expiration_date")) or "",
        "evaluation_date": parse_date(direct_profile.get("evaluation_date")) or "",
        "policies": direct_profile.get("policies") or [],
        "validation": direct_profile.get("validation") or {},
        "raw_text_preview": direct_profile.get("raw_text_preview") or "",
    }


    exposure_input_fields = [
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
    ]

    for field in exposure_input_fields:
        value = direct_profile.get(field)
        if value not in ("", None, [], {}):
            profile[field] = value


    for item in parsed_claims:
        if not profile["business_name"]:
            profile["business_name"] = clean_profile_value(
                pick(item, ["business_name", "insured_name", "named_insured", "account_name"], "")
            )

        if not profile["carrier_name"]:
            profile["carrier_name"] = clean_profile_value(
                pick(item, ["carrier_name", "insurance_carrier", "carrier"], "")
            )

        if not profile["writing_carrier"]:
            profile["writing_carrier"] = clean_profile_value(
                pick(item, ["writing_carrier", "carrier_name", "insurance_carrier", "carrier"], "")
            )

        if not profile["agency_name"]:
            profile["agency_name"] = clean_profile_value(
                pick(item, ["agency_name", "broker_name", "agency", "producer_name"], "")
            )

        if not profile["account_number"]:
            profile["account_number"] = clean_profile_value(
                pick(item, ["account_number", "customer_number", "account_no", "customer_no"], "")
            )

        if not profile["customer_number"]:
            profile["customer_number"] = profile["account_number"]

        if not profile["policy_number"]:
            profile["policy_number"] = clean_profile_value(
                pick(item, ["policy_number", "policy_no", "policy"], "")
            )

        if not profile["effective_date"]:
            profile["effective_date"] = parse_date(
                pick(item, ["effective_date", "policy_effective_date"])
            ) or ""

        if not profile["expiration_date"]:
            profile["expiration_date"] = parse_date(
                pick(item, ["expiration_date", "policy_expiration_date", "expiry_date"])
            ) or ""

    if not profile["policy_number"]:
        profile["policy_number"] = clean_profile_value(
            profile.get("account_number") or fallback_policy_number
        )

    if not profile["writing_carrier"]:
        profile["writing_carrier"] = profile["carrier_name"]

    return profile


def serialize_json(value, fallback):
    try:
        if value is None:
            return json.dumps(fallback)
        if isinstance(value, str):
            return value
        return json.dumps(value)
    except Exception:
        return json.dumps(fallback)


def serialize_json(value, fallback):
    try:
        if value is None:
            return json.dumps(fallback)

        if isinstance(value, str):
            return value

        return json.dumps(value)
    except Exception:
        return json.dumps(fallback)



def derive_exposure_inputs_from_policy_schedule(profile_data: dict):
    # LOSSQ_POLICY_SCHEDULE_TO_EXPOSURE_INPUTS_V1
    # Copies exposure/premium values that were detected inside policy schedule rows
    # into top-level Exposure Inputs fields.
    import re

    profile_data = profile_data or {}
    policies = profile_data.get("policies") or []

    if not isinstance(policies, list):
        return profile_data

    money_values_for_premium = []

    def first_money(value):
        match = re.search(r"\$?\s*[0-9][0-9,]*(?:\.\d{2})?", str(value or ""))
        return match.group(0).replace(" ", "") if match else ""

    def first_number(value):
        match = re.search(r"\b[0-9][0-9,]*\b", str(value or ""))
        return match.group(0) if match else ""

    def set_if_blank(field, value):
        value = str(value or "").strip()
        if value and not profile_data.get(field):
            profile_data[field] = value

    def scan_text(value):
        text_value = str(value or "")
        lower = text_value.lower()

        if "payroll" in lower:
            set_if_blank("payroll", first_money(text_value))

        if "revenue" in lower or "sales" in lower:
            money = first_money(text_value)
            set_if_blank("revenue", money)
            set_if_blank("sales", money)

        if "receipt" in lower:
            set_if_blank("receipts", first_money(text_value))

        if "vehicle" in lower:
            vehicle_match = re.search(r"vehicles?\s*[:\-]?\s*([0-9,]+)", text_value, re.I)
            set_if_blank("vehicle_count", vehicle_match.group(1) if vehicle_match else first_number(text_value))

        if "driver" in lower:
            driver_match = re.search(r"drivers?\s*[:\-]?\s*([0-9,]+)", text_value, re.I)
            set_if_blank("driver_count", driver_match.group(1) if driver_match else first_number(text_value))

        if "employee" in lower:
            employee_match = re.search(r"employees?\s*[:\-]?\s*([0-9,]+)", text_value, re.I)
            set_if_blank("employee_count", employee_match.group(1) if employee_match else first_number(text_value))

        if "tiv" in lower or "total insured value" in lower:
            money = first_money(text_value)
            set_if_blank("property_tiv", money)
            set_if_blank("tiv", money)

        if "limit" in lower:
            money = first_money(text_value)
            set_if_blank("coverage_limit", money)
            set_if_blank("limits", text_value.strip())

        if "deductible" in lower:
            set_if_blank("deductible", first_money(text_value))

        if "retention" in lower or "sir" in lower:
            set_if_blank("retention", first_money(text_value))

        if "class" in lower and "code" in lower:
            class_match = re.search(r"class(?:ification)?\s*codes?\s*[:\-]?\s*([A-Za-z0-9,\- ]+)", text_value, re.I)
            if class_match:
                set_if_blank("class_codes", class_match.group(1).strip())
                set_if_blank("class_code", class_match.group(1).strip())

    for policy in policies:
        if not isinstance(policy, dict):
            continue

        line = (
            policy.get("line_of_business")
            or policy.get("policy_type")
            or policy.get("coverage")
            or policy.get("line")
            or ""
        )

        if line and not profile_data.get("line_of_business"):
            profile_data["line_of_business"] = str(line).strip()

        for field_name, value in policy.items():
            value_text = str(value or "").strip()
            if not value_text:
                continue

            scan_text(value_text)

            field_lower = str(field_name or "").lower()

            if "premium" in field_lower:
                money = first_money(value_text)
                if money:
                    money_values_for_premium.append(money)

            # Some clean policy tables put exposure basis in one column and premium in the next.
            # If a row has exposure text and another field is only a money value, treat that money as premium.
            if re.fullmatch(r"\$?\s*[0-9][0-9,]*(?:\.\d{2})?", value_text):
                row_text = " ".join(str(v or "") for v in policy.values()).lower()
                if any(word in row_text for word in ["payroll", "vehicles", "drivers", "revenue", "limit", "tiv"]):
                    money_values_for_premium.append(value_text.replace(" ", ""))

    if money_values_for_premium and not profile_data.get("current_premium"):
        total = 0.0
        for item in money_values_for_premium:
            try:
                total += float(str(item).replace("$", "").replace(",", "").strip())
            except Exception:
                pass

        if total > 0:
            profile_data["current_premium"] = f"${total:,.0f}"

    if not profile_data.get("exposure_basis"):
        basis_parts = []
        for field in ["payroll", "revenue", "vehicle_count", "driver_count", "property_tiv", "coverage_limit"]:
            if profile_data.get(field):
                basis_parts.append(f"{field.replace('_', ' ').title()}: {profile_data.get(field)}")
        if basis_parts:
            profile_data["exposure_basis"] = "; ".join(basis_parts)

    return profile_data



def upsert_account_profile(db: Session, profile_data: dict, current_user: dict):
    policy_number = clean_profile_value(
        profile_data.get("policy_number") or profile_data.get("account_number")
    )

    if not policy_number:
        return None

    existing = (
        db.query(AccountProfile)
        .filter(AccountProfile.organization_id == current_user["organization_id"])
        .filter(AccountProfile.policy_number == policy_number)
        .first()
    )

    fields_to_save = [
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
        "raw_text_preview",

        # LOSSQ_SAVE_EXPOSURE_FIELDS_TO_PROFILE_V1
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
    ]

    policies_json = serialize_json(profile_data.get("policies") or [], [])
    validation_json = serialize_json(profile_data.get("validation") or {}, {})

    if existing:
        for field in fields_to_save:
            value = clean_profile_value(profile_data.get(field))

            if value and hasattr(existing, field):
                setattr(existing, field, value)

        if hasattr(existing, "policies"):
            existing.policies = policies_json

        if hasattr(existing, "validation"):
            existing.validation = validation_json

        return existing

    new_profile = AccountProfile(
        business_name=profile_data.get("business_name") or "Business Name Not Set",
        carrier_name=profile_data.get("carrier_name") or "Carrier Not Set",
        writing_carrier=profile_data.get("writing_carrier")
        or profile_data.get("carrier_name")
        or "Carrier Not Set",
        agency_name=profile_data.get("agency_name") or "Agency Not Set",
        account_number=profile_data.get("account_number") or policy_number,
        customer_number=profile_data.get("customer_number")
        or profile_data.get("account_number")
        or policy_number,
        producer_number=profile_data.get("producer_number") or "",
        policy_number=policy_number,
        effective_date=profile_data.get("effective_date") or "Not Set",
        expiration_date=profile_data.get("expiration_date") or "Not Set",
        evaluation_date=profile_data.get("evaluation_date")
        or datetime.now().date().isoformat(),
        policies=policies_json,
        validation=validation_json,
        raw_text_preview=profile_data.get("raw_text_preview") or "",
        organization_id=current_user["organization_id"],
    )

    db.add(new_profile)
    db.flush()
    db.refresh(new_profile)
    return new_profile

@router.post("/loss-run")
async def upload_loss_run(
    file: UploadFile = File(...),
    policy_number: str = Form(default=""),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("upload")),
):
    return await save_uploaded_files(
        files=[file],
        policy_number=policy_number,
        db=db,
        current_user=current_user,
    )


@router.post("/loss-runs")
async def upload_multiple_loss_runs(
    files: List[UploadFile] = File(...),
    policy_number: str = Form(default=""),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("upload")),
):
    return await save_uploaded_files(
        files=files,
        policy_number=policy_number,
        db=db,
        current_user=current_user,
    )


@router.post("/debug-loss-run")
async def debug_loss_run_parser(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_permission("upload")),
):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    safe_filename = (file.filename or "debug_loss_run.pdf").replace(" ", "_")
    file_path = os.path.join(UPLOAD_DIR, f"DEBUG-{timestamp}_{safe_filename}")

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    result = parse_loss_run_file(file_path, safe_filename)

    profile = result.get("profile") or {}
    policies = result.get("policies") or []
    claims = result.get("claims") or []
    validation = result.get("validation") or {}

    return {
        "profile": profile,
        "policy_count": len(policies),
        "policies": policies,
        "claim_count": len(claims),
        "claims": claims,
        "validation": validation,
        "raw_text_preview": result.get("raw_text_preview", "")[:3000],
    }


async def save_uploaded_files(files, policy_number, db, current_user):
    ensure_claim_timeline_columns(db)
    ensure_account_profile_columns(db)

    total_saved = 0
    total_duplicates_skipped = 0
    uploaded_files = []
    all_parsed_claims = []
    direct_profile = {}

    upload_session_id = datetime.now().strftime("%Y%m%d%H%M%S")
    clean_input_policy = str(policy_number or "").strip()

    for file in files:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        safe_filename = (file.filename or "loss_run.pdf").replace(" ", "_")
        file_path = os.path.join(UPLOAD_DIR, f"{timestamp}_{safe_filename}")

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        parsed_claims, parsed_profile = parse_file(file_path, file.filename or safe_filename)

        file_policy_number = clean_input_policy
        file_account_key_for_claims = ""

        claim_policy_number = ""
        for claim_data in parsed_claims:
            claim_policy = clean_profile_value(claim_data.get("policy_number"))
            if claim_policy:
                claim_policy_number = claim_policy
                break

        if parsed_profile:
            parsed_policy = clean_profile_value(parsed_profile.get("policy_number"))
            parsed_account = clean_profile_value(
                parsed_profile.get("account_number") or parsed_profile.get("customer_number")
            )

            # LOSSQ_DUPLICATE_REHOME_TO_PARSED_ACCOUNT_KEY_V1
            # Use the extracted account/customer key to re-home duplicate claims during upload.
            if parsed_account and not is_bad_policy_key_for_upload(parsed_account):
                file_account_key_for_claims = parsed_account

            # Important:
            # Prefer the actual policy number found on claim rows.
            # Do not let customer/account number override real claim policy number.
            if parsed_policy:
                file_policy_number = parsed_policy
            elif claim_policy_number:
                file_policy_number = claim_policy_number
            elif parsed_account:
                file_policy_number = parsed_account

            for key, value in parsed_profile.items():
                if key in ["policies", "validation", "raw_text_preview"]:
                    direct_profile[key] = value
                    continue

                if value and not direct_profile.get(key):
                    direct_profile[key] = value

        if not file_policy_number and claim_policy_number:
            file_policy_number = claim_policy_number

        if not file_policy_number:
            file_policy_number = (
                direct_profile.get("policy_number")
                or direct_profile.get("account_number")
                or f"UPLOAD-{upload_session_id}-{len(uploaded_files) + 1}"
            )

        if not direct_profile.get("policy_number"):
            direct_profile["policy_number"] = file_policy_number

        all_parsed_claims.extend(parsed_claims)

        file_saved = 0
        file_duplicates = 0

        for claim_data in parsed_claims:
            normalized = normalize_claim_data(
                raw=claim_data,
                fallback_policy_number=file_policy_number,
                current_user=current_user,
            )

            claim_number = str(normalized.get("claim_number") or "").strip().upper()
            policy_value = str(
                normalized.get("policy_number") or file_policy_number
            ).strip()

            normalized["claim_number"] = claim_number
            normalized["policy_number"] = policy_value

            if not claim_number or claim_number == "UNKNOWN":
                print("Skipping claim without valid claim number")
                continue

            duplicate_query = db.query(Claim).filter(
                Claim.organization_id == current_user["organization_id"],
                Claim.claim_number == claim_number,
                Claim.policy_number == policy_value,
            )

            existing_claim = duplicate_query.first()

            if existing_claim:
                # LOSSQ_REHOME_DUPLICATE_CLAIMS_TO_ACCOUNT_KEY
                # If the claim already exists from an earlier upload, re-home it to the corrected
                # account/profile key so it survives logout/login and appears under the right profile.
                safe_profile_data = locals().get("profile_data", {}) or {}

                corrected_policy_key = (
                    file_account_key_for_claims
                    or safe_profile_data.get("account_number")
                    or safe_profile_data.get("customer_number")
                    or safe_profile_data.get("policy_number")
                    or policy_number
                    or policy_value
                )

                if corrected_policy_key and not is_bad_policy_key_for_upload(corrected_policy_key):
                    existing_claim.policy_number = corrected_policy_key

                if normalized.get("line_of_business"):
                    existing_claim.line_of_business = normalized.get("line_of_business")

                if normalized.get("claim_type"):
                    existing_claim.claim_type = normalized.get("claim_type")

                if normalized.get("cause_of_loss"):
                    existing_claim.cause_of_loss = normalized.get("cause_of_loss")

                if normalized.get("status"):
                    existing_claim.status = normalized.get("status")

                if normalized.get("paid_amount") is not None:
                    existing_claim.paid_amount = normalized.get("paid_amount")

                if normalized.get("reserve_amount") is not None:
                    existing_claim.reserve_amount = normalized.get("reserve_amount")

                if normalized.get("total_incurred") is not None:
                    existing_claim.total_incurred = normalized.get("total_incurred")

                file_duplicates += 1
                total_duplicates_skipped += 1
                continue

            db.add(Claim(**normalized))
            file_saved += 1
            total_saved += 1

        upload_record = UploadHistory(
            filename=file.filename,
            stored_path=file_path,
            content_type=file.content_type,
            claims_saved=file_saved,
            uploaded_at=datetime.now().isoformat(),
            uploaded_by_user_id=current_user["user_id"],
            organization_id=current_user["organization_id"],
        )

        db.add(upload_record)

        uploaded_files.append(
            {
                "filename": file.filename,
                "claims_saved": file_saved,
                "duplicates_skipped": file_duplicates,
                "policy_number": file_policy_number,
            }
        )

    profile_data = extract_profile_data(
        parsed_claims=all_parsed_claims,
        fallback_policy_number=direct_profile.get("policy_number")
        or direct_profile.get("account_number")
        or clean_input_policy
        or f"UPLOAD-{upload_session_id}",
        direct_profile=direct_profile,
    )

    if not profile_data.get("policy_number"):
        profile_data["policy_number"] = (
            profile_data.get("account_number")
            or direct_profile.get("policy_number")
            or f"UPLOAD-{upload_session_id}"
        )

    primary_claim_policy_number = ""
    for claim_data in all_parsed_claims:
        claim_policy_number = clean_profile_value(claim_data.get("policy_number"))
        if claim_policy_number and not is_bad_policy_key_for_upload(claim_policy_number):
            primary_claim_policy_number = claim_policy_number
            break

    profile_account_key = choose_upload_account_key(profile_data, direct_profile)

    if profile_account_key:
        profile_data["account_number"] = profile_data.get("account_number") or profile_account_key
        profile_data["customer_number"] = (
            profile_data.get("customer_number")
            or profile_data.get("account_number")
            or profile_account_key
        )

    # Main saved profile key should be the stable account key.
    # Real policy numbers stay in profile_data["policies"].
    if is_bad_policy_key_for_upload(profile_data.get("policy_number")):
        profile_data["policy_number"] = profile_account_key or primary_claim_policy_number or f"UPLOAD-{upload_session_id}"

    profile_data = derive_exposure_inputs_from_policy_schedule(profile_data)

    profile = upsert_account_profile(db, profile_data, current_user)

    record_audit_event(
        db,
        current_user=current_user,
        action="loss_run_uploaded",
        resource_type="upload",
        resource_id=profile_data.get("policy_number"),
        details={
            "policy_number": profile_data.get("policy_number"),
            "account_number": profile_data.get("account_number"),
            "saved_claims": total_saved,
            "duplicates_skipped": total_duplicates_skipped,
            "profile_auto_populated": bool(profile),
            "policy_count": len(profile_data.get("policies") or []),
            "validation": profile_data.get("validation") or {},
            "uploaded_files": uploaded_files,
        },
    )

    db.commit()

    account_profile_id = None
    if profile is not None:
        try:
            db.refresh(profile)
            account_profile_id = getattr(profile, "id", None)
        except Exception:
            account_profile_id = getattr(profile, "id", None)

    profile_response = dict(profile_data or {})
    profile_response["id"] = account_profile_id
    profile_response["account_profile_id"] = account_profile_id
    profile_response["selected_profile_id"] = account_profile_id
    profile_response["selected_policy_number"] = profile_data.get("policy_number")

    return {
        "message": "Loss run file(s) uploaded successfully",
        "saved_claims": total_saved,
        "duplicates_skipped": total_duplicates_skipped,
        "policy_number": profile_data.get("policy_number"),
        "account_number": profile_data.get("account_number"),
        "account_profile_id": account_profile_id,
        "selected_profile_id": account_profile_id,
        "selected_policy_number": profile_data.get("policy_number"),
        "profile_auto_populated": bool(profile),
        "profile": profile_response,
        "account_profile": profile_response,
        "policies": profile_data.get("policies") or [],
        "claims": all_parsed_claims,
        "parsed_claims": all_parsed_claims,
        "saved_claim_rows": all_parsed_claims,
        "parsed_claim_count": len(all_parsed_claims),
        "saved_claim_count": total_saved,
        "validation": profile_data.get("validation") or {},
        "uploaded_files": uploaded_files,
    }
