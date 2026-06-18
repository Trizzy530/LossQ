import csv
from fastapi import HTTPException, APIRouter, UploadFile, File, Depends, Form
from sqlalchemy.orm import Session
from sqlalchemy import text, inspect, func
import shutil
import os
import json
from datetime import datetime
from typing import List, Any

from app.database import SessionLocal
from app.models.claim import Claim
from app.models.upload_history import UploadHistory
from app.models.account_profile import AccountProfile
import re
from app.services.audit import record_audit_event
from app.services.loss_run_pipeline import parse_loss_run_file
from app.services.universal_profile import extract_universal_profile_from_text
import traceback
from app.role_utils import require_permission
from app.services.row_policy_preservation import preserve_row_policy_fields

try:
    from app.services.excel_parser_service import parse_claims_from_excel
except Exception:
    parse_claims_from_excel = None



# LOSSQ_UPLOAD_SECURITY_PHASE_2_V1
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "25"))
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024

ALLOWED_UPLOAD_EXTENSIONS = {
    ".pdf",
    ".csv",
    ".xlsx",
    ".xls",
    ".png",
    ".jpg",
    ".jpeg",
    ".txt",
}

ALLOWED_UPLOAD_CONTENT_TYPES = {
    "application/pdf",
    "text/csv",
    "text/plain",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "image/png",
    "image/jpeg",
    "application/octet-stream",  # Some browsers send this for CSV/XLSX/PDF.
}

BLOCKED_UPLOAD_EXTENSIONS = {
    ".exe",
    ".bat",
    ".cmd",
    ".com",
    ".scr",
    ".js",
    ".vbs",
    ".ps1",
    ".sh",
    ".php",
    ".py",
    ".jar",
    ".msi",
    ".dll",
    ".html",
    ".htm",
    ".svg",
}


def sanitize_upload_filename(filename: str):
    filename = str(filename or "upload").strip()
    filename = filename.replace("\\", "_").replace("/", "_")
    filename = re.sub(r"[^A-Za-z0-9._ -]", "_", filename)
    filename = re.sub(r"\s+", "_", filename)
    filename = filename.strip("._- ")

    if not filename:
        filename = "upload"

    if len(filename) > 140:
        stem, ext = os.path.splitext(filename)
        filename = f"{stem[:120]}{ext}"

    return filename


async def validate_upload_file_security(file):
    filename = sanitize_upload_filename(getattr(file, "filename", "") or "")
    content_type = str(getattr(file, "content_type", "") or "").lower().strip()
    _, ext = os.path.splitext(filename.lower())

    if not ext:
        raise HTTPException(
            status_code=400,
            detail="Upload blocked. File must include a valid extension.",
        )

    if ext in BLOCKED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Upload blocked. This file type is not allowed.",
        )

    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Upload blocked. Allowed file types are PDF, CSV, XLSX, XLS, PNG, JPG, JPEG, and TXT.",
        )

    if content_type and content_type not in ALLOWED_UPLOAD_CONTENT_TYPES:
        # Do not over-block octet-stream cases, but block clearly dangerous browser-reported types.
        if not content_type.startswith("application/octet-stream"):
            raise HTTPException(
                status_code=400,
                detail="Upload blocked. The uploaded file content type is not allowed.",
            )

    # Check file size without permanently consuming the stream.
    try:
        await file.seek(0)
        content = await file.read()
        size = len(content or b"")

        if size <= 0:
            raise HTTPException(
                status_code=400,
                detail="Upload blocked. The file appears to be empty.",
            )

        if size > MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Upload blocked. File size must be {MAX_UPLOAD_SIZE_MB}MB or less.",
            )

        await file.seek(0)
    except HTTPException:
        raise
    except Exception:
        try:
            await file.seek(0)
        except Exception:
            pass
        raise HTTPException(
            status_code=400,
            detail="Upload blocked. The file could not be validated safely.",
        )

    return filename



# LOSSQ_FILTER_CLAIM_MODEL_FIELDS_BEFORE_SAVE_V1
def lossq_filter_claim_model_fields(data: dict):
    """Keep only fields that exist on the Claim SQLAlchemy model before Claim(**data)."""
    if not isinstance(data, dict):
        return {}

    try:
        allowed_fields = set(Claim.__table__.columns.keys())
    except Exception:
        allowed_fields = {
            "id",
            "organization_id",
            "account_profile_id",
            "claim_number",
            "policy_number",
            "carrier_name",
            "line_of_business",
            "claim_type",
            "status",
            "date_of_loss",
            "date_reported",
            "date_closed",
            "paid_amount",
            "reserve_amount",
            "total_incurred",
            "description",
            "claimant_name",
            "litigation",
            "fraud_flag",
            "risk_flag",
            "created_at",
            "updated_at",
        }

    cleaned = {}
    removed = {}

    for key, value in data.items():
        if key in allowed_fields:
            cleaned[key] = value
        else:
            removed[key] = value

    if removed:
        print("LOSSQ_CLAIM_FIELD_FILTER_REMOVED:", sorted(list(removed.keys())))

    return cleaned


# LOSSQ_ROW_LEVEL_POLICY_SAVE_PRESERVATION_V1
def lossq_preserve_row_policy_before_save(normalized: dict, raw_claim: dict, fallback_policy_number: str = ""):
    """
    Preserve each claim row's own policy number and policy type/line before Claim(**normalized).
    This prevents account/main policy from overwriting every claim row.
    """
    if not isinstance(normalized, dict):
        normalized = {}

    if not isinstance(raw_claim, dict):
        raw_claim = {}

    def clean(value):
        return clean_profile_value(value)

    row_policy = (
        clean(raw_claim.get("policy_number"))
        or clean(raw_claim.get("Policy Number"))
        or clean(raw_claim.get("policy_no"))
        or clean(raw_claim.get("Policy No"))
        or clean(raw_claim.get("policy"))
        or clean(raw_claim.get("Policy"))
    )

    row_line = (
        clean(raw_claim.get("policy_type"))
        or clean(raw_claim.get("Policy Type"))
        or clean(raw_claim.get("line_of_business"))
        or clean(raw_claim.get("Line of Business"))
        or clean(raw_claim.get("claim_type"))
        or clean(raw_claim.get("Coverage"))
        or clean(raw_claim.get("coverage"))
        or clean(raw_claim.get("Line"))
        or clean(raw_claim.get("line"))
    )

    row_status = (
        clean(raw_claim.get("status"))
        or clean(raw_claim.get("Status"))
        or clean(raw_claim.get("claim_status"))
        or clean(raw_claim.get("Claim Status"))
    )

    if row_policy and not is_bad_policy_key_for_upload(row_policy):
        normalized["policy_number"] = row_policy
    elif not clean(normalized.get("policy_number")):
        fallback = clean(fallback_policy_number)
        if fallback and not is_bad_policy_key_for_upload(fallback):
            normalized["policy_number"] = fallback

    if row_line:
        normalized["line_of_business"] = row_line
        normalized["claim_type"] = row_line

    if row_status:
        normalized["status"] = row_status

    return normalized


# LOSSQ_CLEAN_STANDARD_CSV_ROW_POLICY_OVERRIDE_V1


# LOSSQ_AGENCY_HEADER_FIRST_EXTRACTION_V1
def lossq_header_agency_from_csv(file_path):
    """
    Extract Producing Agency / Agency / Producer / Broker from clean CSV column values.
    This prevents reading the next header cell such as Policy Number as the agency.
    """
    try:
        if not str(file_path or "").lower().endswith(".csv"):
            return ""

        import csv
        import re

        def clean(value):
            return re.sub(r"\s+", " ", str(value or "").strip())

        def key(value):
            return re.sub(r"[^a-z0-9]", "", str(value or "").lower())

        agency_keys = {
            "producingagency",
            "agency",
            "agencyname",
            "producer",
            "broker",
            "brokerage",
            "producingbroker",
            "brokeragency",
        }

        bad_values = {
            "policy number",
            "policy no",
            "policy type",
            "coverage",
            "line",
            "line of business",
            "effective date",
            "expiration date",
            "claim number",
            "claim no",
            "status",
            "paid",
            "reserve",
            "total incurred",
            "carrier",
            "writing carrier",
            "account name",
            "named insured",
            "insured",
        }

        with open(file_path, "r", encoding="utf-8-sig", errors="ignore", newline="") as handle:
            reader = csv.DictReader(handle)

            if not reader.fieldnames:
                return ""

            agency_fields = [
                field for field in reader.fieldnames
                if key(field) in agency_keys
            ]

            if not agency_fields:
                return ""

            for row in reader:
                for field in agency_fields:
                    value = clean((row or {}).get(field, ""))
                    if value and value.lower() not in bad_values and key(value) not in agency_keys:
                        return value

        return ""
    except Exception as exc:
        print("LOSSQ_AGENCY_HEADER_FIRST_EXTRACTION_ERROR:", str(exc)[:200])
        return ""


# LOSSQ_UNIVERSAL_PRODUCING_AGENCY_EXTRACTION_V1
def lossq_universal_agency_from_csv(file_path):
    """
    Extract producing agency/broker/producer from common CSV layouts:
    - Clean tabular columns: Producing Agency, Agency, Producer, Broker
    - Label-pair rows: Agency, Summit Table Risk Advisors
    - Messy section rows: Producing Agency / Broker / Brokerage
    """
    try:
        if not str(file_path or "").lower().endswith(".csv"):
            return ""

        import csv
        import re

        def clean(value):
            return re.sub(r"\s+", " ", str(value or "").strip())

        def key(value):
            return re.sub(r"[^a-z0-9]", "", str(value or "").lower())

        agency_keys = {
            "producingagency",
            "agency",
            "agencyname",
            "producer",
            "broker",
            "brokerage",
            "producingbroker",
            "brokeragency",
        }

        with open(file_path, "r", encoding="utf-8-sig", errors="ignore", newline="") as handle:
            rows = list(csv.reader(handle))

        for row in rows[:80]:
            cleaned_row = [clean(cell) for cell in row]

            for idx, cell in enumerate(cleaned_row):
                if key(cell) in agency_keys:
                    for value in cleaned_row[idx + 1:]:
                        value_key = key(value)
                        if value and value_key not in agency_keys:
                            return value

        # Header-style extraction.
        with open(file_path, "r", encoding="utf-8-sig", errors="ignore", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                for name, value in (row or {}).items():
                    if key(name) in agency_keys and clean(value):
                        return clean(value)

        return ""
    except Exception as exc:
        print("LOSSQ_UNIVERSAL_AGENCY_EXTRACTION_ERROR:", str(exc)[:200])
        return ""


def lossq_clean_standard_csv_override(file_path, parsed_claims=None, parsed_profile=None):
    """
    Universal clean-tabular CSV reader.
    If a CSV has claim-level headers like Claim Number, Policy Number, Policy Type, Status,
    use the row data directly so the main/account policy does not overwrite every claim.
    """
    parsed_claims = parsed_claims or []
    parsed_profile = parsed_profile or {}

    if not str(file_path or "").lower().endswith(".csv"):
        return parsed_claims, parsed_profile

    rows = []
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(file_path, "r", newline="", encoding=encoding) as f:
                rows = list(csv.DictReader(f))
            break
        except Exception:
            rows = []

    if not rows:
        return parsed_claims, parsed_profile

    # LOSSQ_CSV_RAW_ROW_EXPOSURE_CAPTURE_V1
    # Capture exposure/premium fields directly from raw CSV rows before claim normalization strips extra columns.
    raw_upload_exposure_inputs = extract_exposure_inputs_from_parsed_rows(rows) or {}
    if raw_upload_exposure_inputs:
        if not isinstance(parsed_profile, dict):
            parsed_profile = {}
        parsed_profile = dict(parsed_profile)
        parsed_profile.update({k: v for k, v in raw_upload_exposure_inputs.items() if v not in ("", None, [], {})})
        parsed_profile["exposure_inputs"] = raw_upload_exposure_inputs
        parsed_profile["exposures"] = raw_upload_exposure_inputs
        print("LOSSQ_CSV_RAW_ROW_EXPOSURE_CAPTURED:", raw_upload_exposure_inputs)

    def clean(value):
        return clean_profile_value(value)

    def get(row, *names):
        lower_map = {str(k or "").strip().lower(): v for k, v in row.items()}
        for name in names:
            key = str(name or "").strip().lower()
            if key in lower_map:
                value = clean(lower_map.get(key))
                if value:
                    return value
        return ""

    first = rows[0] or {}
    has_claim_number = any(str(k or "").strip().lower() == "claim number" for k in first.keys())
    has_policy_number = any(str(k or "").strip().lower() == "policy number" for k in first.keys())

    if not has_claim_number or not has_policy_number:
        return parsed_claims, parsed_profile

    clean_claims = []
    policies = []
    seen_policies = set()

    for row in rows:
        claim_number = get(row, "Claim Number", "Claim #", "Claim No", "claim_number")
        policy_number = get(row, "Policy Number", "Policy No", "policy_number", "policy")
        policy_type = get(row, "Policy Type", "Line of Business", "Coverage", "line_of_business", "claim_type")
        status = get(row, "Status", "Claim Status", "claim_status")

        if not claim_number or not policy_number:
            continue

        claim = {
            "business_name": get(row, "Account Name", "Named Insured", "Insured", "Business Name"),
            "named_insured": get(row, "Account Name", "Named Insured", "Insured", "Business Name"),
            "carrier_name": get(row, "Carrier", "Writing Carrier", "carrier_name"),
            "writing_carrier": get(row, "Carrier", "Writing Carrier", "carrier_name"),
            "producing_agency": get(row, "Producing Agency", "Agency", "Broker"),
            "policy_number": policy_number,
            "policy_type": policy_type,
            "line_of_business": policy_type,
            "claim_type": policy_type,
            "effective_date": get(row, "Effective Date", "Policy Effective Date"),
            "expiration_date": get(row, "Expiration Date", "Policy Expiration Date"),
            "evaluation_date": get(row, "Evaluation Date", "Valuation Date", "As Of Date"),
            "claim_number": claim_number,
            "date_of_loss": get(row, "Date of Loss", "Loss Date"),
            "date_reported": get(row, "Date Reported", "Reported Date"),
            "date_closed": get(row, "Date Closed", "Closed Date"),
            "status": status,
            "cause_of_loss": get(row, "Cause of Loss", "Loss Cause", "Description"),
            "description": get(row, "Description", "Loss Description", "Cause of Loss"),
            "claimant_name": get(row, "Claimant", "Claimant Name"),
            "paid_amount": get(row, "Paid", "Paid Amount", "Total Paid"),
            "reserve_amount": get(row, "Reserve", "Reserve Amount", "Outstanding Reserve"),
            "total_incurred": get(row, "Total Incurred", "Incurred", "Total"),
            "litigation": get(row, "Litigation", "Attorney Involvement", "Litigated"),
        }

        clean_claims.append(claim)

        if policy_number and policy_number.upper() not in seen_policies:
            seen_policies.add(policy_number.upper())
            policies.append({
                "policy_number": policy_number,
                "policy_type": policy_type,
                "line_of_business": policy_type,
                "effective_date": claim.get("effective_date"),
                "expiration_date": claim.get("expiration_date"),
                "carrier_name": claim.get("carrier_name"),
            })

    if len(clean_claims) < len(parsed_claims or []):
        return parsed_claims, parsed_profile

    profile = dict(parsed_profile or {})
    first_claim = clean_claims[0] if clean_claims else {}

    for key in [
        "business_name",
        "named_insured",
        "carrier_name",
        "writing_carrier",
        "producing_agency",
        "effective_date",
        "expiration_date",
        "evaluation_date",
    ]:
        if first_claim.get(key):
            profile[key] = first_claim.get(key)

    if policies:
        profile["policies"] = policies
        profile["policy_schedule"] = policies
        profile["policy_number"] = policies[0].get("policy_number")
        profile["account_number"] = policies[0].get("policy_number")
        profile["policy_count"] = len(policies)

    print(f"LOSSQ_CLEAN_STANDARD_CSV_OVERRIDE_APPLIED: claims={len(clean_claims)} policies={len(policies)}")

    return clean_claims, profile



# LOSSQ_FINAL_ROW_POLICY_SAVE_FIX_V1
def lossq_apply_row_values_at_final_save(normalized: dict, raw_claim: dict):
    """
    Final safety layer before Claim(**normalized).
    Row-level claim values must win over account/main-policy values.
    This prevents all claims from being saved under the first/main policy.
    """
    if not isinstance(normalized, dict):
        normalized = {}

    if not isinstance(raw_claim, dict):
        return normalized

    def clean(value):
        return clean_profile_value(value)

    def get_any(*names):
        lower_map = {str(k or "").strip().lower(): v for k, v in raw_claim.items()}
        for name in names:
            key = str(name or "").strip().lower()
            if key in lower_map:
                value = clean(lower_map.get(key))
                if value:
                    return value
        return ""

    row_policy_number = get_any(
        "policy_number",
        "policy number",
        "policy no",
        "policy_no",
        "policy",
        "main policy",
        "account number",
    )

    row_policy_type = get_any(
        "policy_type",
        "policy type",
        "line_of_business",
        "line of business",
        "coverage",
        "coverage line",
        "claim_type",
        "claim type",
        "line",
        "lob",
    )

    row_status = get_any(
        "status",
        "claim status",
        "claim_status",
    )

    row_claim_number = get_any(
        "claim_number",
        "claim number",
        "claim #",
        "claim no",
        "claim_no",
    )

    row_paid = get_any("paid_amount", "paid", "paid amount", "total paid")
    row_reserve = get_any("reserve_amount", "reserve", "reserve amount", "outstanding reserve")
    row_total = get_any("total_incurred", "total incurred", "incurred", "total")

    if row_policy_number and not is_bad_policy_key_for_upload(row_policy_number):
        normalized["policy_number"] = row_policy_number

    if row_policy_type:
        normalized["line_of_business"] = row_policy_type
        normalized["claim_type"] = row_policy_type

    if row_status:
        normalized["status"] = row_status

    if row_claim_number:
        normalized["claim_number"] = row_claim_number

    if row_paid:
        normalized["paid_amount"] = row_paid

    if row_reserve:
        normalized["reserve_amount"] = row_reserve

    if row_total:
        normalized["total_incurred"] = row_total

    return normalized


router = APIRouter(prefix="/upload", tags=["Upload"])

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()




# LOSSQ_EXTRACT_EXPOSURE_FROM_PARSED_ROWS_V1
def extract_exposure_inputs_from_parsed_rows(rows):
    """Extract exposure/premium fields from parsed CSV/XLSX/PDF row dictionaries."""
    import re

    profile = {}

    def clean(value):
        return str(value or "").replace("\ufeff", "").replace("", "").strip()

    def norm_key(value):
        return re.sub(r"[^a-z0-9]", "", clean(value).lower())

    def is_bad_value(value):
        v = clean(value)
        if not v:
            return True
        if re.fullmatch(r"(19|20)\d{2}", v):
            return True
        if re.fullmatch(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", v):
            return True
        if re.fullmatch(r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", v):
            return True
        return False

    def money_value(value):
        v = clean(value)
        if is_bad_value(v):
            return ""
        match = re.search(r"\$?\s*[0-9][0-9,]*(?:\.\d{2})?", v)
        if not match:
            return ""
        found = match.group(0).replace(" ", "")
        numeric = found.replace("$", "").replace(",", "")
        if is_bad_value(numeric):
            return ""
        return found

    def count_value(value):
        v = clean(value)
        if is_bad_value(v):
            return ""
        match = re.search(r"\b[0-9][0-9,]*\b", v)
        if not match:
            return ""
        found = match.group(0).replace(",", "")
        if is_bad_value(found):
            return ""
        return found

    field_map = {
        "currentpremium": "current_premium",
        "annualpremium": "current_premium",
        "writtenpremium": "current_premium",
        "totalpremium": "current_premium",
        "premium": "current_premium",

        "expiringpremium": "expiring_premium",
        "priorpremium": "expiring_premium",
        "previouspremium": "expiring_premium",

        "targetrenewalpremium": "target_renewal_premium",
        "renewalpremium": "target_renewal_premium",
        "estimatedrenewalpremium": "target_renewal_premium",

        "policylimits": "limits",
        "limits": "limits",
        "coveragelimit": "coverage_limit",
        "deductible": "deductible",
        "retention": "retention",
        "sir": "retention",

        "payroll": "payroll",
        "annualpayroll": "payroll",
        "estimatedpayroll": "payroll",

        "revenue": "revenue",
        "annualrevenue": "revenue",
        "revenuesales": "revenue",
        "sales": "sales",
        "grosssales": "sales",
        "receipts": "receipts",
        "grossreceipts": "receipts",

        "employeecount": "employee_count",
        "employees": "employee_count",
        "numberofemployees": "employee_count",

        "vehiclecount": "vehicle_count",
        "vehicles": "vehicle_count",
        "powerunits": "vehicle_count",

        "drivercount": "driver_count",
        "drivers": "driver_count",

        "propertytiv": "property_tiv",
        "totalinsuredvalue": "property_tiv",
        "tiv": "tiv",

        "buildingvalue": "building_value",
        "buildinglimit": "building_value",
        "contentsvalue": "contents_value",
        "businesspersonalproperty": "contents_value",
        "bpp": "contents_value",

        "squarefootage": "square_footage",
        "sqft": "square_footage",
        "locationcount": "location_count",
        "locations": "location_count",
        "unitcount": "unit_count",
        "units": "unit_count",

        "cargolimit": "cargo_limit",
        "umbrellalimit": "umbrella_limit",
        "excesslimit": "umbrella_limit",

        "experiencemod": "experience_mod",
        "mod": "mod",
        "exposurechangepercent": "exposure_change_percent",
        "cyberrevenue": "cyber_revenue",
        "professionalrevenue": "professional_revenue",
        "exposurebasis": "exposure_basis",
    }

    money_fields = {
        "current_premium",
        "expiring_premium",
        "target_renewal_premium",
        "limits",
        "coverage_limit",
        "deductible",
        "retention",
        "payroll",
        "revenue",
        "sales",
        "receipts",
        "property_tiv",
        "tiv",
        "building_value",
        "contents_value",
        "cargo_limit",
        "umbrella_limit",
        "cyber_revenue",
        "professional_revenue",
    }

    count_fields = {
        "employee_count",
        "vehicle_count",
        "driver_count",
        "square_footage",
        "location_count",
        "unit_count",
    }

    def set_field(field, value):
        if not field:
            return

        if field in money_fields:
            value = money_value(value)
        elif field in count_fields:
            value = count_value(value)
        else:
            value = clean(value)

        if value and not profile.get(field):
            profile[field] = value

    if not isinstance(rows, list):
        return {}

    for row in rows:
        if not isinstance(row, dict):
            continue

        for key, value in row.items():
            mapped = field_map.get(norm_key(key))
            if mapped:
                set_field(mapped, value)

        # Some parsers store label/value pairs instead of normal columns.
        label = (
            row.get("label")
            or row.get("field")
            or row.get("metric")
            or row.get("name")
            or row.get("exposure_label")
            or row.get("exposure_type")
        )
        value = (
            row.get("value")
            or row.get("amount")
            or row.get("exposure_value")
            or row.get("exposure")
            or row.get("current_value")
        )

        if label and value:
            mapped = field_map.get(norm_key(label))
            if mapped:
                set_field(mapped, value)

        # One fully populated row is enough because exposure columns repeat on every CSV claim row.
        if len(profile.keys()) >= 5:
            break

    basis_parts = []
    if profile.get("payroll"):
        basis_parts.append(f"Payroll: {profile['payroll']}")
    if profile.get("revenue"):
        basis_parts.append(f"Revenue: {profile['revenue']}")
    if profile.get("vehicle_count"):
        basis_parts.append(f"Vehicles: {profile['vehicle_count']}")
    if profile.get("driver_count"):
        basis_parts.append(f"Drivers: {profile['driver_count']}")
    if profile.get("employee_count"):
        basis_parts.append(f"Employees: {profile['employee_count']}")
    if profile.get("property_tiv"):
        basis_parts.append(f"Property TIV: {profile['property_tiv']}")

    if basis_parts and not profile.get("exposure_basis"):
        profile["exposure_basis"] = " | ".join(basis_parts)

    return profile


def extract_exposure_inputs_from_raw_text(raw_text: str):
    # LOSSQ_ENABLE_AUTO_EXPOSURE_EXTRACTION_V3
    # Universal exposure extractor for labeled CSV, XLSX text, PDF text, premium worksheets, and policy schedules.
    import csv
    import io
    import re

    text_value = str(raw_text or "")
    profile = {}

    def clean(value):
        return str(value or "").replace("\ufeff", "").replace("", "").strip()

    def norm_key(value):
        return re.sub(r"[^a-z0-9]", "", clean(value).lower())

    def is_bad_value(value):
        v = clean(value)
        if not v:
            return True
        # Do not treat policy years or dates as exposure values.
        if re.fullmatch(r"(19|20)\d{2}", v):
            return True
        if re.fullmatch(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", v):
            return True
        if re.fullmatch(r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", v):
            return True
        return False

    def money_value(value):
        v = clean(value)
        if is_bad_value(v):
            return ""
        match = re.search(r"\$?\s*[0-9][0-9,]*(?:\.\d{2})?", v)
        if not match:
            return ""
        found = match.group(0).replace(" ", "")
        if is_bad_value(found.replace("$", "").replace(",", "")):
            return ""
        return found

    def count_value(value):
        v = clean(value)
        if is_bad_value(v):
            return ""
        match = re.search(r"\b[0-9][0-9,]*\b", v)
        if not match:
            return ""
        found = match.group(0).replace(",", "")
        if is_bad_value(found):
            return ""
        return found

    field_map = {
        "currentpremium": "current_premium",
        "annualpremium": "current_premium",
        "writtenpremium": "current_premium",
        "totalpremium": "current_premium",
        "premium": "current_premium",

        "expiringpremium": "expiring_premium",
        "priorpremium": "expiring_premium",
        "previouspremium": "expiring_premium",

        "targetrenewalpremium": "target_renewal_premium",
        "renewalpremium": "target_renewal_premium",
        "estimatedrenewalpremium": "target_renewal_premium",

        "primarylineofbusiness": "line_of_business",
        "lineofbusiness": "line_of_business",
        "lob": "line_of_business",
        "policytype": "line_of_business",
        "coverage": "line_of_business",

        "state": "state",
        "primarystate": "state",
        "classcode": "class_code",
        "classcodes": "class_codes",

        "policylimits": "limits",
        "limits": "limits",
        "coveragelimit": "coverage_limit",
        "deductible": "deductible",
        "retention": "retention",
        "sir": "retention",

        "payroll": "payroll",
        "annualpayroll": "payroll",
        "estimatedpayroll": "payroll",

        "revenue": "revenue",
        "annualrevenue": "revenue",
        "sales": "sales",
        "grosssales": "sales",
        "revenuesales": "revenue",
        "receipts": "receipts",
        "grossreceipts": "receipts",

        "employeecount": "employee_count",
        "employees": "employee_count",
        "numberofemployees": "employee_count",

        "vehiclecount": "vehicle_count",
        "vehicles": "vehicle_count",
        "powerunits": "vehicle_count",

        "drivercount": "driver_count",
        "drivers": "driver_count",

        "propertytiv": "property_tiv",
        "totalinsuredvalue": "property_tiv",
        "tiv": "tiv",

        "buildingvalue": "building_value",
        "buildinglimit": "building_value",
        "contentsvalue": "contents_value",
        "businesspersonalproperty": "contents_value",
        "bpp": "contents_value",

        "squarefootage": "square_footage",
        "sqft": "square_footage",
        "locationcount": "location_count",
        "locations": "location_count",
        "unitcount": "unit_count",
        "units": "unit_count",

        "cargolimit": "cargo_limit",
        "umbrellalimit": "umbrella_limit",
        "excesslimit": "umbrella_limit",

        "experiencemod": "experience_mod",
        "mod": "mod",
        "exposurechangepercent": "exposure_change_percent",
        "cyberrevenue": "cyber_revenue",
        "professionalrevenue": "professional_revenue",
        "exposurebasis": "exposure_basis",
    }

    money_fields = {
        "current_premium",
        "expiring_premium",
        "target_renewal_premium",
        "limits",
        "coverage_limit",
        "deductible",
        "retention",
        "payroll",
        "revenue",
        "sales",
        "receipts",
        "property_tiv",
        "tiv",
        "building_value",
        "contents_value",
        "cargo_limit",
        "umbrella_limit",
        "cyber_revenue",
        "professional_revenue",
    }

    count_fields = {
        "employee_count",
        "vehicle_count",
        "driver_count",
        "square_footage",
        "location_count",
        "unit_count",
    }

    def set_field(field, value):
        if not field or field not in field_map.values():
            return

        if field in money_fields:
            value = money_value(value)
        elif field in count_fields:
            value = count_value(value)
        else:
            value = clean(value)

        if value and not profile.get(field):
            profile[field] = value

    def apply_pair(key, value):
        mapped = field_map.get(norm_key(key))
        if mapped:
            set_field(mapped, value)

    # CSV-style extraction: headers on first line, values on following rows.
    try:
        sample = text_value.strip()
        if "," in sample and "\n" in sample:
            reader = csv.DictReader(io.StringIO(sample))
            for row in reader:
                for key, value in dict(row or {}).items():
                    apply_pair(key, value)
                # One good row is enough because exposure columns repeat per claim row.
                if profile:
                    break
    except Exception:
        pass

    # Label/value extraction from text lines and worksheet-style rows.
    for line in text_value.splitlines():
        if not line.strip():
            continue

        if ":" in line:
            left, right = line.split(":", 1)
            apply_pair(left, right)

        if "," in line:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 2:
                for i in range(len(parts) - 1):
                    apply_pair(parts[i], parts[i + 1])

    # Regex fallback for labels embedded in text.
    label_aliases = {
        "current_premium": ["current premium", "annual premium", "written premium", "total premium"],
        "expiring_premium": ["expiring premium", "prior premium", "previous premium"],
        "target_renewal_premium": ["target renewal premium", "renewal premium", "estimated renewal premium"],
        "payroll": ["annual payroll", "estimated payroll", "payroll"],
        "revenue": ["annual revenue", "revenue"],
        "sales": ["gross sales", "sales"],
        "receipts": ["gross receipts", "receipts"],
        "employee_count": ["employee count", "number of employees", "employees"],
        "vehicle_count": ["vehicle count", "vehicles", "power units"],
        "driver_count": ["driver count", "drivers"],
        "property_tiv": ["property tiv", "total insured value"],
        "tiv": ["tiv"],
        "coverage_limit": ["coverage limit", "policy limit"],
        "limits": ["policy limits", "limits"],
        "deductible": ["deductible"],
        "umbrella_limit": ["umbrella limit", "excess limit"],
        "cyber_revenue": ["cyber revenue"],
        "professional_revenue": ["professional revenue"],
        "experience_mod": ["experience mod", "mod"],
    }

    for field, labels in label_aliases.items():
        if profile.get(field):
            continue
        for label in labels:
            pattern = re.compile(
                re.escape(label) + r"[^$0-9A-Za-z]{0,50}(\$?\s*[0-9][0-9,]*(?:\.\d{2})?|[A-Za-z][A-Za-z0-9 ./%-]{1,80})",
                re.IGNORECASE,
            )
            match = pattern.search(text_value)
            if match:
                set_field(field, match.group(1))
                if profile.get(field):
                    break

    basis_parts = []
    if profile.get("payroll"):
        basis_parts.append(f"Payroll: {profile['payroll']}")
    if profile.get("revenue"):
        basis_parts.append(f"Revenue: {profile['revenue']}")
    if profile.get("vehicle_count"):
        basis_parts.append(f"Vehicles: {profile['vehicle_count']}")
    if profile.get("driver_count"):
        basis_parts.append(f"Drivers: {profile['driver_count']}")
    if profile.get("employee_count"):
        basis_parts.append(f"Employees: {profile['employee_count']}")
    if profile.get("property_tiv"):
        basis_parts.append(f"Property TIV: {profile['property_tiv']}")

    if basis_parts and not profile.get("exposure_basis"):
        profile["exposure_basis"] = " | ".join(basis_parts)

    return profile


def _lossq_live_clean_cell(value):
    return re.sub(r"\s+", " ", str(value or "").strip())

def _lossq_live_money_to_float(value):
    raw = _lossq_live_clean_cell(value)
    if not raw:
        return 0.0
    raw = raw.replace("$", "").replace(",", "").replace("%", "").strip()
    try:
        return float(raw)
    except Exception:
        return 0.0

def _lossq_live_date_to_iso(value):
    raw = _lossq_live_clean_cell(value)
    if not raw:
        return ""

    raw = raw.replace("\\", "/").replace(".", "/").replace("-", "/")
    raw = re.sub(r"\s+", "", raw)

    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", raw)
    if m:
        month, day, year = m.groups()
        year = int(year)
        if year < 100:
            year += 2000 if year < 50 else 1900
        try:
            return f"{year:04d}-{int(month):02d}-{int(day):02d}"
        except Exception:
            return ""

    m = re.fullmatch(r"(\d{4})/(\d{1,2})/(\d{1,2})", raw)
    if m:
        year, month, day = m.groups()
        try:
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        except Exception:
            return ""

    return raw

def _lossq_live_is_policy_number(value):
    raw = _lossq_live_clean_cell(value).upper()
    if not raw:
        return False

    blocked = {
        "POLICY NUMBER", "POLICY", "ACCOUNT INFORMATION", "POLICY SCHEDULE",
        "CLAIM DETAIL", "LOSS SUMMARY", "UNDERWRITING NOTES", "N/A", "NONE", "UNKNOWN",
    }
    if raw in blocked:
        return False

    # LOSSQ_LIVE_UNIVERSAL_POLICY_ID_V1
    if re.search(r"[A-Z0-9]{2,}[-_][A-Z0-9]{2,}[-_](19|20)\d{2}[-_][A-Z0-9]{2,}", raw):
        return True

    if re.search(r"[A-Z]{2,10}[-_](19|20)\d{2}[-_][A-Z0-9]{2,}", raw):
        return True

    return False

def _lossq_live_is_claim_number(value):
    raw = _lossq_live_clean_cell(value).upper()
    if not raw:
        return False

    blocked = {
        "NOTE", "NOTES", "LOSS SUMMARY", "METRIC", "TOTAL CLAIMS", "OPEN CLAIMS",
        "CLOSED CLAIMS", "TOTAL PAID", "TOTAL RESERVE", "TOTAL INCURRED",
        "LARGEST LOSS", "LITIGATED CLAIMS", "CLAIMS WITH ATTORNEY INVOLVEMENT",
        "UNDERWRITING NOTES", "CLAIM NUMBER", "POLICY NUMBER", "DESCRIPTION",
    }
    if raw in blocked:
        return False

    if not re.search(r"\d", raw):
        return False

    # LOSSQ_LIVE_UNIVERSAL_CLAIM_ID_V1
    if re.search(r"[A-Z0-9]{2,}[-_][A-Z0-9]{2,}[-_]\d{4,8}", raw):
        return True

    if re.search(r"[A-Z0-9]{2,}[-_][A-Z0-9]{2,}[-_](19|20)\d{2}[-_][A-Z0-9]{2,}", raw):
        return True

    compact = re.sub(r"[^A-Z0-9]", "", raw)
    if len(compact) >= 6 and re.search(r"[A-Z]", compact) and re.search(r"\d", compact):
        return True

    return False

def _lossq_live_read_section_csv_rows(file_path):
    rows = []
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(file_path, "r", newline="", encoding=encoding) as f:
                rows = [row for row in csv.reader(f)]
            break
        except Exception:
            rows = []

    cleaned = []
    for row in rows:
        cleaned.append([_lossq_live_clean_cell(cell) for cell in row])

    return cleaned

def _lossq_live_extract_section_based_csv(file_path):
    rows = _lossq_live_read_section_csv_rows(file_path)
    print("LOSSQ_SECTION_CSV_ENTERED:", {"file_path": str(file_path), "rows": len(rows)})
    for idx, raw_debug_row in enumerate(rows[:25]):
        print("LOSSQ_SECTION_CSV_RAW_ROW:", {"idx": idx, "row": raw_debug_row})

    if not rows:
        return [], {}

    section_names = {
        "account information": "account",
        "policy schedule": "policies",
        "exposure inputs": "exposures",
        "claim detail": "claims",
        "loss summary": "summary",
        "underwriting notes": "notes",
    }

    current_section = ""
    account = {}
    exposures = {}
    loss_summary = {}
    policies = []
    claims = []

    policy_header_seen = False
    claim_header_seen = False
    exposure_header_seen = False
    summary_header_seen = False

    for row in rows:
        nonempty = [cell for cell in row if _lossq_live_clean_cell(cell)]
        if not nonempty:
            continue

        first = _lossq_live_clean_cell(nonempty[0])
        first_lower = first.lower()

        if first_lower in section_names:
            current_section = section_names[first_lower]
            policy_header_seen = False
            claim_header_seen = False
            exposure_header_seen = False
            summary_header_seen = False
            continue

        if current_section == "account":
            if len(nonempty) >= 2:
                key = _lossq_live_clean_cell(nonempty[0]).lower()
                value = _lossq_live_clean_cell(nonempty[1])

                if key in {"carrier"}:
                    account["carrier_name"] = value
                    account["carrier"] = value
                elif key in {"valuation date", "evaluation date"}:
                    account["evaluation_date"] = _lossq_live_date_to_iso(value)
                elif key in {"named insured", "insured", "business name"}:
                    account["business_name"] = value
                    account["insured_name"] = value
                    account["named_insured"] = value
                elif key in {"account"}:
                    # LOSSQ_ACCOUNT_LABEL_BUSINESS_NAME_V1
                    raw_account_value = str(value or "").strip()
                    upper_account_value = raw_account_value.upper()
                    looks_like_id = _lossq_live_is_policy_number(raw_account_value) or bool(re.search(r"\b[A-Z0-9]{2,}[-_][A-Z0-9]{2,}", upper_account_value))
                    if not looks_like_id:
                        account["business_name"] = raw_account_value
                        account["insured_name"] = raw_account_value
                        account["named_insured"] = raw_account_value
                    else:
                        account["account_number"] = raw_account_value
                        account["customer_number"] = raw_account_value
                elif key in {"account number"}:
                    account["account_number"] = value
                    account["customer_number"] = value
                elif key in {"producer / producing agency", "producer", "producing agency", "agency"}:
                    account["agency_name"] = value
                    account["producing_agency"] = value
                    account["producer"] = value
                elif key in {"producer number"}:
                    account["producer_number"] = value
                elif key in {"effective date", "effective", "policy effective", "policy effective date", "policy start", "policy start date", "period start", "period from", "term start", "inception date"}:
                    account["effective_date"] = _lossq_live_date_to_iso(value)
                    account["effective"] = account["effective_date"]
                elif key in {"expiration date", "expiration", "expiry date", "policy expiration", "policy expiration date", "policy expiry", "policy expiry date", "policy end", "policy end date", "period end", "period to", "term end"}:
                    account["expiration_date"] = _lossq_live_date_to_iso(value)
                    account["expiration"] = account["expiration_date"]
                elif key in {"main policy number", "main policy", "policy number"}:
                    account["policy_number"] = value
                elif key in {"writing carrier"}:
                    account["writing_carrier"] = value
                    account["carrier_name"] = value or account.get("carrier_name", "")
            continue

        if current_section == "policies":
            # LOSSQ_ACCOUNT_CARRIER_BAD_VALUE_CLEANUP_V1
            # Do not let table headers like Exposure Value become carrier values.
            bad_carrier_values = {"exposure value", "exposure basis", "premium", "annual premium", "policy number", "line of business"}
            for carrier_key in ["carrier_name", "writing_carrier", "carrier"]:
                if str(account.get(carrier_key) or "").strip().lower() in bad_carrier_values:
                    account[carrier_key] = ""

            # LOSSQ_UNIVERSAL_POLICY_SCHEDULE_HEADER_MAP_V1
            def _policy_header_key(v):
                return " ".join(_lossq_live_clean_cell(v).lower().replace("/", " ").replace("_", " ").replace("#", "number").split())

            lower_row = [_policy_header_key(cell) for cell in nonempty]

            policy_header_aliases = {"policy number", "policy no", "policy num", "policy id", "policy"}
            line_header_aliases = {"line of business", "line", "coverage line", "coverage", "policy type", "lob"}
            effective_header_aliases = {"effective date", "effective", "eff date", "eff", "policy effective", "policy effective date", "period start", "period from", "term start"}
            expiration_header_aliases = {"expiration date", "expiration", "exp date", "exp", "expiry date", "policy expiration", "policy expiration date", "period end", "period to", "term end"}
            policy_period_aliases = {"policy period", "policy term", "period", "coverage period", "policy dates", "date range"}
            carrier_header_aliases = {"carrier", "writing carrier", "insurer", "company"}
            premium_header_aliases = {"premium", "annual premium", "current premium", "written premium"}
            exposure_basis_aliases = {"exposure basis", "basis", "exposure"}
            expiring_premium_aliases = {"expiring premium", "prior premium", "current term premium"}
            target_renewal_aliases = {"target renewal premium", "target premium", "renewal premium"}

            if any(h in policy_header_aliases for h in lower_row) and any(h in line_header_aliases for h in lower_row):
                policy_header_seen = True
                policy_header_map = {h: idx for idx, h in enumerate(lower_row)}
                continue

            if not policy_header_seen:
                continue

            header_map = locals().get("policy_header_map", {})

            def _get_by_alias(row_values, aliases, fallback_index=None):
                for alias in aliases:
                    if alias in header_map:
                        idx = header_map[alias]
                        return _lossq_live_clean_cell(row_values[idx]) if idx < len(row_values) else ""
                if fallback_index is not None and fallback_index < len(row_values):
                    return _lossq_live_clean_cell(row_values[fallback_index])
                return ""

            # LOSSQ_POLICY_PERIOD_RANGE_SECTION_CSV_V2
            # Do not let fallback indexes shift Carrier into Effective Date.
            policy_number = _get_by_alias(row, policy_header_aliases, 0).upper()
            if not _lossq_live_is_policy_number(policy_number):
                continue

            lob = _get_by_alias(row, line_header_aliases, 1)
            carrier = _get_by_alias(row, carrier_header_aliases, 2) or account.get("writing_carrier") or account.get("carrier_name") or ""

            effective_raw = _get_by_alias(row, effective_header_aliases, None)
            expiration_raw = _get_by_alias(row, expiration_header_aliases, None)
            effective = _lossq_live_date_to_iso(effective_raw) if re.search(r"\d{1,4}[/-]\d{1,2}[/-]\d{1,4}", str(effective_raw or "")) else ""
            expiration = _lossq_live_date_to_iso(expiration_raw) if re.search(r"\d{1,4}[/-]\d{1,2}[/-]\d{1,4}", str(expiration_raw or "")) else ""

            if not effective or not expiration:
                period_value = _get_by_alias(row, policy_period_aliases, None)
                period_dates = re.findall(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}", str(period_value or ""))
                if len(period_dates) >= 2:
                    effective = effective or _lossq_live_date_to_iso(period_dates[0])
                    expiration = expiration or _lossq_live_date_to_iso(period_dates[1])

            current_premium = _get_by_alias(row, premium_header_aliases, 5)
            exposure_basis = _get_by_alias(row, exposure_basis_aliases, 6)
            expiring_premium = _get_by_alias(row, expiring_premium_aliases, None)
            target_renewal = _get_by_alias(row, target_renewal_aliases, None)

            policy = {
                "line_of_business": lob,
                "policy_type": lob,
                "coverage": lob,
                "policy_number": policy_number,
                "carrier": carrier,
                "carrier_name": carrier,
                "effective_date": effective,
                "effective": effective,
                "effectiveDate": effective,
                "expiration_date": expiration,
                "expiration": expiration,
                "expirationDate": expiration,
                "exposure_basis": exposure_basis,
                "current_premium": current_premium,
                "premium": current_premium,
                "expiring_premium": expiring_premium,
                "target_renewal_premium": target_renewal,
            }
            policies.append(policy)
            continue

        if current_section == "exposures":
            lower_row = [cell.lower() for cell in nonempty]
            if "field" in lower_row and "value" in lower_row:
                exposure_header_seen = True
                continue

            if not exposure_header_seen:
                continue

            if len(nonempty) >= 2:
                exposures[_lossq_live_clean_cell(nonempty[0])] = _lossq_live_clean_cell(nonempty[1])
            continue

        if current_section == "claims":
            lower_row = [_lossq_live_clean_cell(cell).lower() for cell in nonempty]

            # LOSSQ_SECTION_CSV_CLAIM_DETAIL_HEADER_MAP_V1
            # Universal section-based CSV claim parser. Do not rely on one fixed
            # column order because real loss runs may include Date Reported,
            # Date Closed, Litigation, Flag, Cause, etc.
            if "claim number" in lower_row and "policy number" in lower_row:
                claim_header_seen = True
                claim_headers = [_lossq_live_clean_cell(cell).lower() for cell in row]
                continue

            if not claim_header_seen:
                continue

            if not row or len(row) < 2:
                continue

            def claim_value(*names):
                for name in names:
                    key = str(name or "").strip().lower()
                    if key in claim_headers:
                        idx = claim_headers.index(key)
                        if idx < len(row):
                            return _lossq_live_clean_cell(row[idx])
                return ""

            claim_number = claim_value("claim number", "claim no", "claim #", "claim id", "claim")
            policy_number = claim_value("policy number", "policy no", "policy #", "policy")
            lob = claim_value("line of business", "coverage", "line", "claim type", "policy type")
            status = claim_value("status", "claim status")
            loss_date = claim_value("date of loss", "loss date", "dol")
            reported_date = claim_value("date reported", "reported date", "report date")
            closed_date = claim_value("date closed", "closed date")
            paid_raw = claim_value("paid", "paid amount", "total paid", "loss paid")
            reserve_raw = claim_value("reserve", "reserves", "reserve amount", "total reserve")
            total_raw = claim_value("total incurred", "incurred", "gross incurred", "net incurred", "total")
            description = claim_value("description", "loss description", "claim description", "cause of loss", "cause")
            litigation = claim_value("litigation", "litigated", "suit")
            flag = claim_value("flag", "risk flag", "severity flag")

            if _lossq_live_is_claim_number(claim_number) and _lossq_live_is_policy_number(policy_number):
                claim_number = _lossq_live_clean_cell(claim_number).upper()
                policy_number = _lossq_live_clean_cell(policy_number).upper()
                paid = _lossq_live_money_to_float(paid_raw)
                reserve = _lossq_live_money_to_float(reserve_raw)
                total = _lossq_live_money_to_float(total_raw)

                # If carrier file omits total incurred, calculate safe total.
                if not total and (paid or reserve):
                    total = paid + reserve

                claim = {
                    "claim_number": claim_number,
                    "policy_number": policy_number,
                    "policy": policy_number,
                    "line_of_business": lob,
                    "claim_type": lob,
                    "date_of_loss": _lossq_live_date_to_iso(loss_date),
                    "loss_date": _lossq_live_date_to_iso(loss_date),
                    "date_reported": _lossq_live_date_to_iso(reported_date),
                    "reported_date": _lossq_live_date_to_iso(reported_date),
                    "date_closed": _lossq_live_date_to_iso(closed_date),
                    "closed_date": _lossq_live_date_to_iso(closed_date),
                    "status": _lossq_live_clean_cell(status).title() or "Open",
                    "paid": paid,
                    "paid_amount": paid,
                    "reserve": reserve,
                    "reserve_amount": reserve,
                    "total_incurred": total,
                    "total_amount": total,
                    "total_net_loss": total,
                    "description": description,
                    "loss_description": description,
                    "litigation": litigation,
                    "flag": flag,
                }
                claims.append(claim)
            continue

        if current_section == "summary":
            lower_row = [cell.lower() for cell in nonempty]
            if "metric" in lower_row and "value" in lower_row:
                summary_header_seen = True
                continue

            if not summary_header_seen:
                continue

            if len(nonempty) >= 2:
                loss_summary[_lossq_live_clean_cell(nonempty[0])] = _lossq_live_clean_cell(nonempty[1])
            continue

    if policies:
        account["policies"] = policies
        account["policy_schedule"] = policies

        # Prefer explicit main policy; otherwise use first policy.
        if not _lossq_live_is_policy_number(account.get("policy_number")):
            account["policy_number"] = policies[0].get("policy_number", "")

        # Use matching policy dates for main policy.
        main_policy = account.get("policy_number", "")
        matched_main = next((p for p in policies if p.get("policy_number") == main_policy), policies[0])
        account["effective_date"] = account.get("effective_date") or matched_main.get("effective_date", "")
        account["expiration_date"] = account.get("expiration_date") or matched_main.get("expiration_date", "")
        account["effective"] = account["effective_date"]
        account["expiration"] = account["expiration_date"]

    if exposures:
        account["exposure_inputs"] = exposures
        account["exposures"] = exposures
        account["current_premium"] = exposures.get("Current Premium", "")
        account["payroll"] = exposures.get("Payroll", "")
        account["revenue"] = exposures.get("Revenue / Sales", "")
        account["employee_count"] = exposures.get("Employee Count", "")
        account["vehicle_count"] = exposures.get("Vehicle Count", "")
        account["driver_count"] = exposures.get("Driver Count", "")
        account["property_tiv"] = exposures.get("Property TIV", "")

    if loss_summary:
        account["loss_summary"] = loss_summary

    if claims or policies or exposures:
        account["lossq_section_based_csv_detected"] = True
        account["extraction_status"] = "passed" if claims and policies else "needs_attention"
        account["extraction_score"] = 95 if claims and policies else 75
        account["requires_review"] = False if claims and policies else True

    print("LOSSQ_SECTION_CSV_RETURN_COUNTS:", {"claims": len(claims), "policies": len(policies), "exposures": len(exposures)})
    # LOSSQ_FINAL_PRE_SECTION_ACCOUNT_PROFILE_FALLBACK_V1
    # Final universal fallback for carrier CSVs that place account fields before formal sections.
    if not account.get("business_name"):
        for raw_row in rows[:25]:
            cells = [_lossq_live_clean_cell(c) for c in raw_row if _lossq_live_clean_cell(c)]
            if len(cells) < 2:
                continue
            raw_key = cells[0].lower().replace(".", "").strip()
            raw_value = cells[1].strip()
            if raw_key in {"account", "account name", "insured", "named insured", "business name"}:
                account["business_name"] = raw_value
                account["insured_name"] = raw_value
                account["named_insured"] = raw_value
                print("LOSSQ_FINAL_ACCOUNT_NAME_FROM_PRE_SECTION:", raw_value)
                break

    return claims, account


# LOSSQ_SECTION_CSV_HEADER_FALLBACK_V1
def _lossq_header_fallback_parse_section_csv(file_path):
    rows = _lossq_live_read_section_csv_rows(file_path)
    claims = []
    policies = []

    def clean(v):
        return _lossq_live_clean_cell(v)

    def key(v):
        return clean(v).lower().replace("/", " ").replace("_", " ").strip()

    for idx, row in enumerate(rows):
        header = [key(c) for c in row]

        if "policy number" in header and ("coverage line" in header or "line of business" in header or "coverage" in header):
            for data in rows[idx + 1:]:
                if not data or not any(clean(c) for c in data):
                    break
                if len(data) < 2:
                    continue

                policy_number = clean(data[0]).upper()
                if not _lossq_live_is_policy_number(policy_number):
                    continue

                lob = clean(data[1]) if len(data) > 1 else ""
                carrier = clean(data[2]) if len(data) > 2 else ""
                effective = _lossq_live_date_to_iso(data[3]) if len(data) > 3 else ""
                expiration = _lossq_live_date_to_iso(data[4]) if len(data) > 4 else ""
                premium = clean(data[5]) if len(data) > 5 else ""

                policies.append({
                    "policy_number": policy_number,
                    "line_of_business": lob,
                    "policy_type": lob,
                    "coverage": lob,
                    "carrier": carrier,
                    "carrier_name": carrier,
                    "effective_date": effective,
                    "effective": effective,
                    "expiration_date": expiration,
                    "expiration": expiration,
                    "current_premium": premium,
                    "premium": premium,
                })

        if "claim number" in header and "policy number" in header:
            for data in rows[idx + 1:]:
                if not data or not any(clean(c) for c in data):
                    break

                row_map = {}
                for h_i, h in enumerate(header):
                    row_map[h] = clean(data[h_i]) if h_i < len(data) else ""

                claim_number = row_map.get("claim number", "").upper()
                policy_number = row_map.get("policy number", "").upper()

                if not _lossq_live_is_claim_number(claim_number) or not _lossq_live_is_policy_number(policy_number):
                    continue

                paid = _lossq_live_money_to_float(row_map.get("paid", ""))
                reserve = _lossq_live_money_to_float(row_map.get("reserve", ""))
                total = _lossq_live_money_to_float(row_map.get("total incurred", ""))
                if not total and (paid or reserve):
                    total = paid + reserve

                lob = row_map.get("line of business", "") or row_map.get("coverage", "")
                status = row_map.get("status", "") or "Open"
                loss_date = _lossq_live_date_to_iso(row_map.get("date of loss", ""))
                reported_date = _lossq_live_date_to_iso(row_map.get("date reported", ""))
                closed_date = _lossq_live_date_to_iso(row_map.get("date closed", ""))
                description = row_map.get("description", "")

                claims.append({
                    "claim_number": claim_number,
                    "policy_number": policy_number,
                    "policy": policy_number,
                    "line_of_business": lob,
                    "claim_type": lob,
                    "date_of_loss": loss_date,
                    "loss_date": loss_date,
                    "date_reported": reported_date,
                    "reported_date": reported_date,
                    "date_closed": closed_date,
                    "closed_date": closed_date,
                    "status": status.title(),
                    "paid": paid,
                    "paid_amount": paid,
                    "reserve": reserve,
                    "reserve_amount": reserve,
                    "total_incurred": total,
                    "total_amount": total,
                    "total_net_loss": total,
                    "description": description,
                    "loss_description": description,
                    "litigation": row_map.get("litigation", ""),
                    "flag": row_map.get("flag", ""),
                })

    profile = {}
    if policies:
        profile["policies"] = policies
        profile["policy_schedule"] = policies
        profile["policy_number"] = policies[0].get("policy_number", "")
        profile["effective_date"] = policies[0].get("effective_date", "")
        profile["expiration_date"] = policies[0].get("expiration_date", "")

    print("LOSSQ_SECTION_CSV_HEADER_FALLBACK_COUNTS:", {"claims": len(claims), "policies": len(policies)})
    return claims, profile

def lossq_live_repair_section_csv_upload(file_path, parsed_claims, parsed_profile):
    """
    If the uploaded file is a section-based CSV, override the old row parser
    so Notes, Loss Summary, Metric, and exposure rows do not become claims.
    """
    filename = str(file_path or "").lower()
    if not filename.endswith(".csv"):
        return parsed_claims, parsed_profile

    section_claims, section_profile = _lossq_live_extract_section_based_csv(file_path)
    # LOSSQ_SECTION_CSV_EMPTY_CLAIMS_FALLBACK_V1
    # If section extraction produced zero claims, use universal header fallback.
    if not section_claims:
        fallback_claims, fallback_profile = _lossq_header_fallback_parse_section_csv(file_path)
        if fallback_claims or fallback_profile:
            print("LOSSQ_SECTION_CSV_USING_HEADER_FALLBACK:", {"claims": len(fallback_claims), "profile_keys": list(fallback_profile.keys())})
            section_claims = fallback_claims or section_claims
            if fallback_profile:
                section_profile.update({k: v for k, v in fallback_profile.items() if v not in ("", None, [], {})})
        elif not section_profile:
            return parsed_claims, parsed_profile

    if not isinstance(parsed_profile, dict):
        parsed_profile = {}

    merged_profile = dict(parsed_profile)
    merged_profile.update({k: v for k, v in section_profile.items() if v not in ("", None, [], {})})

    if section_claims:
        parsed_claims = section_claims
        merged_profile["claims"] = section_claims
        merged_profile["parsed_claims"] = section_claims

    # LOSSQ_APPLY_EXPOSURE_INPUTS_TO_GENERIC_PARSE_RESULT_V1
    raw_text_for_exposure = str(
        merged_profile.get("raw_text_preview")
        or merged_profile.get("raw_text")
        or parsed_profile.get("raw_text_preview")
        or parsed_profile.get("raw_text")
        or ""
    )
    exposure_inputs = {}
    exposure_inputs.update(extract_exposure_inputs_from_raw_text(raw_text_for_exposure) or {})
    exposure_inputs.update(extract_exposure_inputs_from_parsed_rows(parsed_claims) or {})

    if exposure_inputs:
        merged_profile.update({k: v for k, v in exposure_inputs.items() if v not in ("", None, [], {})})
        merged_profile["exposure_inputs"] = exposure_inputs
        merged_profile["exposures"] = exposure_inputs

    return parsed_claims, merged_profile



# LOSSQ_PDF_CLAIM_DETAIL_NUMBER_REPAIR_V1
def lossq_pdf_clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def lossq_pdf_claim_number_is_policy_derived(claim_number, policy_number="", line_of_business=""):
    claim = lossq_beta_norm_key(claim_number)
    policy = lossq_beta_norm_key(policy_number)

    if not claim:
        return True

    if policy and claim == policy:
        return True

    claim_compact = re.sub(r"[^A-Z0-9]", "", claim)
    policy_compact = re.sub(r"[^A-Z0-9]", "", policy)

    if policy_compact and (claim_compact in policy_compact or policy_compact in claim_compact):
        return True

    line_tokens = (
        "GL", "WC", "AUTO", "AU", "PROP", "PR", "CP", "BOP", "CY", "CYBER",
        "UMB", "EXCESS", "EPLI", "EPL", "DO", "DNO", "EO", "PL", "IM",
        "CRIME", "FID", "FIDUCIARY", "CARGO", "MTC", "LIAB", "ABUSE",
        "MOLESTATION", "GAR", "GARAGE"
    )

    # Generated/policy-derived examples:
    # CP-2025, UMB-2025, GL-2025-4701-GENERAL, WC-2025-4703-WORKERS.
    generated_pattern = r"^(" + "|".join(line_tokens) + r")[-_ ]?(19|20)\d{2}([-_ ][A-Z0-9]+){0,4}$"
    if re.match(generated_pattern, claim):
        return True

    return False


def lossq_pdf_extract_claim_detail_rows_from_text(raw_text):
    text_value = str(raw_text or "")
    if not text_value.strip():
        return []

    upper_text = text_value.upper()
    start_index = upper_text.find("CLAIM DETAIL")
    if start_index >= 0:
        text_value = text_value[start_index:]

    end_index = text_value.upper().find("UNDERWRITING NOTES")
    if end_index >= 0:
        claim_section = text_value[:end_index]
    else:
        claim_section = text_value

    claim_id_pattern = r"[A-Z0-9]{2,}(?:[-_][A-Z0-9]{2,}){1,6}"
    policy_id_pattern = r"[A-Z0-9]{2,}(?:[-_][A-Z0-9]{2,}){2,8}"

    row_start_pattern = re.compile(
        rf"(?m)^\s*(?P<claim>{claim_id_pattern})\s+(?P<policy>{policy_id_pattern})\s+"
    )

    starts = list(row_start_pattern.finditer(claim_section))
    if not starts:
        return []

    money_pattern = r"\$?\(?\d[\d,]*(?:\.\d+)?\)?"
    date_pattern = r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"

    claims = []

    for index, match in enumerate(starts):
        next_start = starts[index + 1].start() if index + 1 < len(starts) else len(claim_section)

        claim_number = lossq_pdf_clean_text(match.group("claim"))
        policy_number = lossq_pdf_clean_text(match.group("policy"))
        rest = claim_section[match.end():next_start]
        rest = lossq_pdf_clean_text(rest)

        if not claim_number or not policy_number:
            continue

        status_match = re.search(
            rf"(?P<line>.*?)(?P<status>Open|Closed|Reopened|Pending|Denied|Reported)\s+(?P<loss>{date_pattern})\s+(?P<reported>{date_pattern})(?:\s+(?P<closed>{date_pattern}))?\s+(?P<paid>{money_pattern})\s+(?P<reserve>{money_pattern})\s+(?P<total>{money_pattern})\s*(?P<description>.*)$",
            rest,
            re.IGNORECASE | re.DOTALL,
        )

        if not status_match:
            continue

        line_of_business = lossq_pdf_clean_text(status_match.group("line"))
        status = lossq_pdf_clean_text(status_match.group("status")).title()
        loss_date = lossq_pdf_clean_text(status_match.group("loss"))
        reported_date = lossq_pdf_clean_text(status_match.group("reported"))
        closed_date = lossq_pdf_clean_text(status_match.group("closed"))

        paid = lossq_beta_money_to_float(status_match.group("paid"))
        reserve = lossq_beta_money_to_float(status_match.group("reserve"))
        total = lossq_beta_money_to_float(status_match.group("total"))

        if total <= 0 and (paid > 0 or reserve > 0):
            total = paid + reserve

        description = lossq_pdf_clean_text(status_match.group("description"))

        litigation = False
        litigation_match = re.search(r"\b(Yes|No)\b", description, re.IGNORECASE)
        if litigation_match:
            litigation = litigation_match.group(1).lower() == "yes"
            description = lossq_pdf_clean_text(description[:litigation_match.start()])

        if not line_of_business:
            continue

        if total <= 0 and paid <= 0 and reserve <= 0:
            continue

        claims.append({
            "claim_number": claim_number,
            "claim_id": claim_number,
            "policy_number": policy_number,
            "line_of_business": line_of_business,
            "claim_type": line_of_business,
            "policy_type": line_of_business,
            "status": status,
            "date_of_loss": loss_date,
            "loss_date": loss_date,
            "date_reported": reported_date,
            "reported_date": reported_date,
            "date_closed": closed_date,
            "closed_date": closed_date,
            "paid": paid,
            "paid_amount": paid,
            "reserve": reserve,
            "reserve_amount": reserve,
            "total_incurred": total,
            "total_amount": total,
            "description": description,
            "loss_description": description,
            "litigation": litigation,
        })

    return claims


def lossq_pdf_amounts_close(left, right):
    try:
        return abs(float(left or 0) - float(right or 0)) <= 2.0
    except Exception:
        return False


def lossq_repair_pdf_claims_from_raw_text(raw_text, parsed_claims):
    raw_claims = lossq_pdf_extract_claim_detail_rows_from_text(raw_text)
    if not raw_claims:
        return parsed_claims

    existing_claims = [dict(item) for item in (parsed_claims or []) if isinstance(item, dict)]
    repaired = []
    used_existing = set()

    for raw_claim in raw_claims:
        match_index = None

        raw_policy = lossq_beta_norm_key(raw_claim.get("policy_number"))
        raw_paid = lossq_beta_money_to_float(raw_claim.get("paid_amount"))
        raw_reserve = lossq_beta_money_to_float(raw_claim.get("reserve_amount"))
        raw_total = lossq_beta_money_to_float(raw_claim.get("total_incurred"))

        for idx, existing in enumerate(existing_claims):
            if idx in used_existing:
                continue

            existing_policy = lossq_beta_norm_key(existing.get("policy_number"))
            existing_paid = lossq_beta_money_to_float(existing.get("paid_amount"))
            existing_reserve = lossq_beta_money_to_float(existing.get("reserve_amount"))
            existing_total = lossq_beta_money_to_float(existing.get("total_incurred"))

            same_policy = bool(raw_policy and raw_policy == existing_policy)
            same_amounts = (
                lossq_pdf_amounts_close(raw_paid, existing_paid)
                and lossq_pdf_amounts_close(raw_reserve, existing_reserve)
                and lossq_pdf_amounts_close(raw_total, existing_total)
            )

            if same_policy and same_amounts:
                match_index = idx
                break

        if match_index is not None:
            used_existing.add(match_index)
            merged = dict(existing_claims[match_index])

            # Trust the actual row-start claim number from the PDF claim detail table.
            for key, value in raw_claim.items():
                if value not in ("", None, [], {}):
                    merged[key] = value

            repaired.append(merged)
        else:
            repaired.append(raw_claim)

    # Keep any unmatched existing claim only if it does not look generated/policy-derived.
    for idx, existing in enumerate(existing_claims):
        if idx in used_existing:
            continue

        if not lossq_pdf_claim_number_is_policy_derived(
            existing.get("claim_number"),
            existing.get("policy_number"),
            existing.get("line_of_business") or existing.get("claim_type"),
        ):
            repaired.append(existing)

    if repaired and len(repaired) >= len(existing_claims):
        print("LOSSQ_PDF_CLAIM_NUMBER_REPAIR_APPLIED:", {
            "before": len(existing_claims),
            "after": len(repaired),
            "claim_numbers": [claim.get("claim_number") for claim in repaired],
            "total_incurred": sum(lossq_beta_money_to_float(claim.get("total_incurred")) for claim in repaired),
        })
        return repaired

    return parsed_claims



# LOSSQ_DIRECT_FILE_EXPOSURE_CAPTURE_V1
def lossq_extract_exposure_inputs_directly_from_file(file_path: str):
    """
    Universal direct file exposure extractor.
    Reads CSV/XLSX rows before the claim parser strips non-claim exposure columns.
    """
    exposure_inputs = {}

    try:
        lower_path = str(file_path or "").lower()

        if lower_path.endswith(".csv"):
            rows = []
            for encoding in ("utf-8-sig", "utf-8", "latin-1"):
                try:
                    with open(file_path, "r", newline="", encoding=encoding, errors="ignore") as handle:
                        rows = list(csv.DictReader(handle))
                    break
                except Exception:
                    rows = []

            if rows:
                exposure_inputs.update(extract_exposure_inputs_from_parsed_rows(rows) or {})

        elif lower_path.endswith((".xlsx", ".xls")):
            try:
                from openpyxl import load_workbook

                workbook = load_workbook(file_path, data_only=True)
                rows = []

                for sheet in workbook.worksheets:
                    values = list(sheet.iter_rows(values_only=True))
                    if not values:
                        continue

                    # Header row format.
                    header = [str(cell or "").strip() for cell in values[0]]
                    if any(header):
                        for raw_row in values[1:]:
                            row = {}
                            for index, header_name in enumerate(header):
                                if not header_name:
                                    continue
                                row[header_name] = raw_row[index] if index < len(raw_row) else ""
                            if row:
                                rows.append(row)

                    # Label/value rows.
                    for raw_row in values:
                        clean_cells = [cell for cell in raw_row if cell not in ("", None)]
                        if len(clean_cells) >= 2:
                            rows.append({
                                "label": clean_cells[0],
                                "value": clean_cells[1],
                            })

                if rows:
                    exposure_inputs.update(extract_exposure_inputs_from_parsed_rows(rows) or {})
            except Exception as exc:
                print("LOSSQ_XLSX_DIRECT_EXPOSURE_CAPTURE_ERROR:", str(exc)[:200])

    except Exception as exc:
        print("LOSSQ_DIRECT_FILE_EXPOSURE_CAPTURE_ERROR:", str(exc)[:200])

    exposure_inputs = {
        k: v for k, v in (exposure_inputs or {}).items()
        if v not in ("", None, [], {})
    }

    if exposure_inputs:
        print("LOSSQ_DIRECT_FILE_EXPOSURE_CAPTURED:", exposure_inputs)

    return exposure_inputs


def parse_file(file_path: str, filename: str):
    lower_name = str(filename or "").lower()

    if lower_name.endswith(".pdf"):
        result = parse_loss_run_file(file_path, filename)

        profile = result.get("profile") or {}
        policies = result.get("policies") or []
        claims = result.get("claims") or []
        validation = result.get("validation") or {}

        raw_text_preview = result.get("raw_text_preview", "")[:50000]

        # LOSSQ_APPLY_EXPOSURE_INPUTS_TO_UPLOAD_PROFILE_V1
        exposure_inputs = {}
        exposure_inputs.update(extract_exposure_inputs_from_raw_text(raw_text_preview) or {})
        exposure_inputs.update(extract_exposure_inputs_from_parsed_rows(parsed_claims) or {})

        if exposure_inputs:
            profile.update({k: v for k, v in exposure_inputs.items() if v not in ("", None, [], {})})
            validation["exposure_inputs"] = exposure_inputs
            validation["exposures"] = exposure_inputs
        claims = lossq_repair_pdf_claims_from_raw_text(raw_text_preview, claims)
        result["claims"] = claims
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

        # LOSSQ_DISABLE_AUTO_EXPOSURE_PARSE_MERGE_V1
        # Exposure Inputs are now manual only. Do not auto-merge premium/exposure fields from uploads.
        return claims, profile

    # LOSSQ_DO_NOT_PARSE_XLSX_AS_CSV_V1
    # XLSX files are ZIP workbooks and must not be read by csv.reader.
    if lower_name.endswith(".csv"):
        # LOSSQ_SECTION_CSV_PRIORITY_V1
        section_claims, section_profile = _lossq_live_extract_section_based_csv(file_path)
        if section_claims or section_profile.get("account_number") or section_profile.get("business_name"):
            return section_claims, section_profile
        if parse_claims_from_excel:
            claims = parse_claims_from_excel(file_path)
            return claims, {}
        return [], {}


    if lower_name.endswith(".xlsx") or lower_name.endswith(".xls"):
        # LOSSQ_XLSX_EXCEL_PARSER_BRANCH_V1
        # Do not parse XLSX as CSV. Use the Excel parser only.
        if parse_claims_from_excel:
            claims = parse_claims_from_excel(file_path)
            return claims, {}
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




# LOSSQ_TABULAR_UPLOAD_POLICY_SCHEDULE_FROM_CLAIMS_V1
def build_policy_schedule_from_claims_for_upload(claims):
    """
    CSV/XLSX files often do not include a profile-level policy schedule.
    Build one from claim rows so the dashboard keeps all account claims after reload/back navigation.
    """
    schedule = {}

    for claim in claims or []:
        if not isinstance(claim, dict):
            continue

        policy_number = clean_profile_value(
            claim.get("policy_number")
            or claim.get("policyNumber")
            or claim.get("policy_no")
            or claim.get("policy")
        )

        if not policy_number or is_bad_policy_key_for_upload(policy_number):
            continue

        key = policy_number.strip().upper()

        line_of_business = clean_profile_value(
            claim.get("line_of_business")
            or claim.get("coverage")
            or claim.get("coverage_line")
            or claim.get("lob")
            or claim.get("policy_type")
        )

        if key not in schedule:
            schedule[key] = {
                "policy_number": policy_number,
                "line_of_business": line_of_business or "Unknown",
                "claim_count": 0,
                "total_incurred": 0,
            }

        schedule[key]["claim_count"] += 1

        try:
            incurred_raw = (
                claim.get("total_incurred")
                or claim.get("incurred")
                or claim.get("loss_amount")
                or claim.get("amount")
                or 0
            )
            incurred = float(str(incurred_raw).replace("$", "").replace(",", "").strip() or 0)
        except Exception:
            incurred = 0

        schedule[key]["total_incurred"] += incurred

        if line_of_business and schedule[key].get("line_of_business") in ("", "Unknown", None):
            schedule[key]["line_of_business"] = line_of_business

    return list(schedule.values())


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
        # LOSSQ_UPLOAD_ERROR_TRACE_V1
        print("LOSSQ_UPLOAD_ERROR_TRACE:", traceback.format_exc())
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
        print("LOSSQ_UPLOAD_ERROR_TRACE:", traceback.format_exc())
        db.rollback()
        print(f"Account profile column check failed: {e}")



def clean_cause_of_loss(value: Any):
    # LOSSQ_CLEAN_CAUSE_OF_LOSS_V1
    # Prevent parser/table headers from leaking into the Cause of Loss field.

    text_value = clean_profile_value(value)

    if not text_value:
        return ""

    stop_phrases = [
        "Total Claims",
        "Claims Total",
        "Claim Count",
        "Total Paid",
        "Paid Total",
        "Total Reserve",
        "Reserve Total",
        "Total Incurred",
        "Incurred Total",
        "Loss Summary",
        "Policy Schedule",
        "Claim #",
        "Claim Number",
        "Date of Loss",
        "Loss Date",
        "Reported Date",
        "Status Paid",
        "Status Reserve",
    ]

    for phrase in stop_phrases:
        index = text_value.lower().find(phrase.lower())
        if index > 0:
            text_value = text_value[:index].strip()

    text_value = re.sub(r"\s+", " ", text_value).strip(" .,-;:")

    # Keep it readable for claim detail cards.
    if len(text_value) > 140:
        text_value = text_value[:140].rsplit(" ", 1)[0].strip(" .,-;:")

    return text_value


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

    normalized = {
        "claim_number": pick(raw, ["claim_number", "claim_no", "claim_id"], "Unknown"),
        "policy_id": raw.get("policy_id"),
        "policy_number": final_policy_number,
        "line_of_business": pick(raw, ["line_of_business", "lob", "coverage_line"]),
        "claim_type": pick(raw, ["claim_type", "type"]),
        "cause_of_loss": clean_cause_of_loss(pick(raw, ["cause_of_loss", "cause"])),
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

    # LOSSQ_NORMALIZE_ROW_POLICY_PRESERVATION_V1
    return preserve_row_policy_fields(
        raw=raw,
        normalized=normalized,
        fallback_policy_number=fallback_policy_number,
    )


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




def strict_money_value_for_exposure(value):
    # LOSSQ_STRICT_EXPOSURE_MONEY_VALUES_V1
    # Exposure money fields must look like actual dollars.
    # This prevents policy/account numbers like PV-ACCT-572914 from becoming Property TIV.
    text_value = str(value or "")

    money_match = re.search(r"\$\s*[0-9][0-9,]*(?:\.\d{2})?", text_value)
    if money_match:
        return money_match.group(0).replace(" ", "")

    return ""


def derive_exposure_inputs_from_policy_schedule(profile_data: dict):
    # LOSSQ_POLICY_SCHEDULE_TO_EXPOSURE_INPUTS_V1
    # Copies exposure/premium values that were detected inside policy schedule rows
    # into top-level Exposure Inputs fields.

    profile_data = profile_data or {}
    policies = profile_data.get("policies") or []

    if not isinstance(policies, list):
        return profile_data

    money_values_for_premium = []

    def first_money(value):
        return strict_money_value_for_exposure(value)

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

    # LOSSQ_FINAL_CARRIER_BAD_VALUE_CLEANUP_V1
    bad_final_carrier_values = {"exposure value", "exposure basis", "premium", "annual premium", "policy number", "line of business"}
    for carrier_key in ["carrier_name", "writing_carrier", "carrier"]:
        if str(profile_data.get(carrier_key) or "").strip().lower() in bad_final_carrier_values:
            profile_data[carrier_key] = ""

    # Backfill carrier from first real policy carrier if profile carrier was cleared.
    if not profile_data.get("carrier_name") and isinstance(profile_data.get("policies"), list):
        for policy_item in profile_data.get("policies") or []:
            possible_carrier = str(
                policy_item.get("carrier_name") or policy_item.get("writing_carrier") or policy_item.get("carrier") or ""
            ).strip()
            if possible_carrier and possible_carrier.lower() not in bad_final_carrier_values:
                profile_data["carrier_name"] = possible_carrier
                profile_data["writing_carrier"] = possible_carrier
                break

    # LOSSQ_FINAL_RAW_TEXT_CARRIER_BACKFILL_V1
    # Universal fallback for PDFs/text exports where carrier is present in account text
    # but policy schedule carrier cells are blank.
    if not profile_data.get("carrier_name"):
        raw_text_for_carrier = str(profile_data.get("raw_text_preview") or "")
        carrier_patterns = [
            r"(?i)\bwriting\s+carrier\b\s*[:\-]?\s*([A-Z][A-Za-z0-9&.,'\- ]{3,80})",
            r"(?i)\binsurance\s+carrier\b\s*[:\-]?\s*([A-Z][A-Za-z0-9&.,'\- ]{3,80})",
            r"(?i)\bcarrier\b\s*[:\-]?\s*([A-Z][A-Za-z0-9&.,'\- ]{3,80})",
        ]

        for carrier_pattern in carrier_patterns:
            carrier_match = re.search(carrier_pattern, raw_text_for_carrier)
            if not carrier_match:
                continue

            possible_carrier = str(carrier_match.group(1) or "").strip()
            possible_carrier = re.split(
                r"\b(Named Insured|Account Number|Policy Number|Effective|Expiration|Evaluation|Producing Agency|Agency|Exposure Value|Exposure Basis|Policy Schedule|Claim Detail)\b",
                possible_carrier,
                flags=re.I,
            )[0].strip(" :-|")

            if possible_carrier and possible_carrier.lower() not in bad_final_carrier_values:
                profile_data["carrier_name"] = possible_carrier
                profile_data["writing_carrier"] = possible_carrier
                break

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
        evaluation_date=profile_data.get("evaluation_date") or "",
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
    # LOSSQ_UPLOAD_ROUTE_ERROR_REDACTED_V1
    try:
        await validate_upload_file_security(file)
        return await save_uploaded_files(
            files=[file],
            policy_number=policy_number,
            db=db,
            current_user=current_user,
        )
    except HTTPException:
        raise
    except Exception as e:
        print("LOSSQ_UPLOAD_ERROR_TRACE:", traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Internal server error",
                "error": "Upload processing failed.",
            },
        )


@router.post("/loss-runs")
async def upload_multiple_loss_runs(
    files: List[UploadFile] = File(...),
    policy_number: str = Form(default=""),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("upload")),
):
    try:
        # LOSSQ_UPLOAD_LOSS_RUN_VALIDATE_MULTIPLE_V1
        for upload_file in files:
            await validate_upload_file_security(upload_file)
        return await save_uploaded_files(
            files=files,
            policy_number=policy_number,
            db=db,
            current_user=current_user,
        )
    except HTTPException:
        raise
    except Exception as e:
        print("LOSSQ_UPLOAD_ERROR_TRACE:", traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Internal server error",
                "error": "Upload processing failed.",
            },
        )


@router.post("/debug-loss-run")
async def debug_loss_run_parser(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_permission("upload")),
):
    # LOSSQ_UPLOAD_DEBUG_VALIDATE_FILE_V1
    safe_upload_filename = await validate_upload_file_security(file)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    safe_filename = (safe_upload_filename or "debug_loss_run.pdf").replace(" ", "_")
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




# LOSSQ_BETA_UPLOAD_GUARDRAILS_V1
def lossq_beta_clean_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip())

def lossq_beta_norm_key(value):
    return lossq_beta_clean_text(value).upper()

def lossq_beta_valid_policy_key(value):
    key = lossq_beta_norm_key(value)
    if not key:
        return False
    bad = {
        "POLICY NOT SET",
        "NOT SET",
        "UNKNOWN",
        "N/A",
        "NONE",
        "LOSS SUMMARY",
        "METRIC",
        "TOTAL CLAIMS",
        "NOTE",
        "NOTES",
    }
    if key in bad:
        return False
    # LOSSQ_UNIVERSAL_MULTI_SEGMENT_POLICY_ID_V1
    # Accept universal carrier/account-prefixed policy IDs:
    # ABC-GL-2025-1234, ACCT-WC-2025-0001, ORG-LIAB-2025-55, etc.
    if bool(re.search(r"[A-Z0-9]{2,}[-_][A-Z0-9]{2,}[-_](19|20)\d{2}[-_][A-Z0-9]{2,}", key)):
        return True

    return bool(re.search(r"[A-Z]{2,10}[-_ ]?\d{4}[-_ ][A-Z0-9]+", key)) or bool(re.search(r"[A-Z]{2,10}-\d+", key))

def lossq_beta_valid_claim_number(value):
    key = lossq_beta_norm_key(value)
    if not key:
        return False

    blocked_exact = {
        "NOTE",
        "NOTES",
        "METRIC",
        "VALUE",
        "FIELD",
        "LOSS SUMMARY",
        "UNDERWRITING NOTES",
        "TOTAL CLAIMS",
        "OPEN CLAIMS",
        "CLOSED CLAIMS",
        "TOTAL PAID",
        "TOTAL RESERVE",
        "TOTAL INCURRED",
        "LARGEST LOSS",
        "LOSS RATIO",
        "CURRENT PREMIUM",
        "EXPIRING PREMIUM",
        "TARGET RENEWAL PREMIUM",
        "PAYROLL",
        "REVENUE / SALES",
        "EMPLOYEE COUNT",
        "VEHICLE COUNT",
        "DRIVER COUNT",
        "PROPERTY TIV",
    }
    if key in blocked_exact:
        return False

    blocked_contains = [
        "FICTIONAL TEST",
        "DESIGNED TO TEST",
        "NOT AFFILIATED",
        "LOSS SUMMARY",
        "UNDERWRITING NOTES",
        "EXPOSURE INPUTS",
        "POLICY SCHEDULE",
        "ACCOUNT INFORMATION",
    ]
    if any(item in key for item in blocked_contains):
        return False

    if not re.search(r"\d", key):
        return False

    # LOSSQ_REJECT_POLICY_FRAGMENT_AS_CLAIM_V2
    # Reject policy schedule fragments that look like line + year + policy suffix.
    # Rejected: GL-2025, CY-2025, BOP-2025, GL-2025-3101-GENERAL.
    # Accepted: carrier/account-prefixed commercial claim IDs with line and numeric claim segments.
    line_tokens = (
        "GL", "WC", "AUTO", "AU", "PROP", "PR", "CP", "BOP", "CY", "CYBER",
        "UMB", "EXCESS", "EPLI", "EPL", "DO", "DNO", "EO", "PL", "IM",
        "CRIME", "FID", "FIDUCIARY", "CARGO", "MTC", "LIAB", "ABUSE",
        "MOLESTATION", "GAR", "GARAGE"
    )

    policy_fragment_pattern = r"^(" + "|".join(line_tokens) + r")[-_ ]?(19|20)\d{2}([-_ ][A-Z0-9]+){0,3}$"
    if re.match(policy_fragment_pattern, key):
        return False

    # Real claim numbers usually include an account/carrier prefix before the line token.
    real_prefixed_claim_pattern = r"^[A-Z0-9]{2,}[-_](" + "|".join(line_tokens) + r")[-_]\d{2,4}[-_]\d{3,8}$"
    if re.match(real_prefixed_claim_pattern, key):
        return True

    # Accept explicit claim IDs.
    if re.search(r"\b(CLM|CLAIM)[-_ ]?[A-Z0-9]{3,}", key):
        return True

    # Accept structured alphanumeric claim IDs with at least 3 meaningful segments,
    # but only if they are not policy-fragment shaped.
    if re.search(r"^[A-Z0-9]{2,}[-_][A-Z0-9]{2,}[-_][A-Z0-9]{2,}([-_][A-Z0-9]{2,})?$", key):
        return True

    compact = re.sub(r"[^A-Z0-9]", "", key)
    if len(compact) >= 8 and re.search(r"\d", compact) and re.search(r"[A-Z]", compact):
        return True

    return False

# LOSSQ_UNIVERSAL_REAL_CLAIM_ROW_EVIDENCE_V1
def lossq_beta_money_to_float(value):
    try:
        raw = str(value or "").strip()
        if not raw:
            return 0.0

        raw = raw.replace("$", "").replace(",", "").replace(" ", "")
        negative = raw.startswith("(") and raw.endswith(")")
        raw = raw.strip("()")

        if raw in {"", "-", "--", "N/A", "NA", "NONE", "NULL"}:
            return 0.0

        number = float(raw)
        return -number if negative else number
    except Exception:
        return 0.0


def lossq_beta_extract_money_triplet_from_text(item):
    if not isinstance(item, dict):
        return {}

    text_parts = []
    for key in [
        "description",
        "loss_description",
        "claim_description",
        "cause_of_loss",
        "narrative",
        "notes",
        "raw_text",
    ]:
        value = item.get(key)
        if value not in ("", None):
            text_parts.append(str(value))

    text_value = " ".join(text_parts)
    if not text_value.strip():
        return {}

    # Remove dates so date numbers are not mistaken for claim dollars.
    scrubbed = re.sub(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", " ", text_value)
    scrubbed = re.sub(r"\b(19|20)\d{2}\b", " ", scrubbed)

    line_patterns = [
        r"general\s+liability",
        r"liquor\s+liability",
        r"workers?\s+comp(?:ensation)?",
        r"business\s*owners?\s+policy",
        r"\bbop\b",
        r"cyber\s+liability",
        r"commercial\s+auto",
        r"auto\s+liability",
        r"cargo",
        r"property",
        r"umbrella",
        r"excess",
        r"epli",
        r"employment\s+practices",
        r"directors?\s+and\s+officers?",
        r"\bd\s*&\s*o\b",
        r"professional\s+liability",
        r"errors?\s+and\s+omissions?",
        r"inland\s+marine",
        r"crime",
        r"abuse",
        r"molestation",
        r"garage",
    ]

    segments = []
    for pattern in line_patterns:
        match = re.search(pattern, scrubbed, re.IGNORECASE)
        if match:
            segments.append(scrubbed[match.end(): match.end() + 220])

    # Fallback to full text if no known commercial line label was found.
    if not segments:
        segments.append(scrubbed[:260])

    for segment in segments:
        tokens = re.findall(r"\$?\(?\d[\d,]*(?:\.\d+)?\)?", segment)
        numbers = [lossq_beta_money_to_float(token) for token in tokens]

        # Keep zeros because reserve can be 0. Require at least one positive value.
        clean_numbers = [n for n in numbers if n >= 0]
        if len(clean_numbers) >= 3 and any(n > 0 for n in clean_numbers[:3]):
            paid = clean_numbers[0]
            reserve = clean_numbers[1]
            total = clean_numbers[2]
            if total <= 0 and (paid > 0 or reserve > 0):
                total = paid + reserve
            return {
                "paid_amount": paid,
                "reserve_amount": reserve,
                "total_incurred": total,
            }

        if len(clean_numbers) >= 2 and any(n > 0 for n in clean_numbers[:2]):
            paid = clean_numbers[0]
            reserve = 0.0
            total = clean_numbers[1]
            if total <= 0 and paid > 0:
                total = paid
            return {
                "paid_amount": paid,
                "reserve_amount": reserve,
                "total_incurred": total,
            }

    return {}


def lossq_beta_get_claim_amounts(item):
    if not isinstance(item, dict):
        return {}

    paid = lossq_beta_money_to_float(
        item.get("paid_amount")
        or item.get("paid")
        or item.get("Paid")
        or item.get("Paid Amount")
        or item.get("Total Paid")
    )
    reserve = lossq_beta_money_to_float(
        item.get("reserve_amount")
        or item.get("reserve")
        or item.get("Reserve")
        or item.get("Reserve Amount")
        or item.get("Outstanding Reserve")
    )
    total = lossq_beta_money_to_float(
        item.get("total_incurred")
        or item.get("incurred")
        or item.get("Total Incurred")
        or item.get("Incurred")
        or item.get("Total")
        or item.get("total")
    )

    if total <= 0 and (paid > 0 or reserve > 0):
        total = paid + reserve

    amounts = {
        "paid_amount": paid,
        "reserve_amount": reserve,
        "total_incurred": total,
    }

    if not any(value > 0 for value in amounts.values()):
        recovered = lossq_beta_extract_money_triplet_from_text(item)
        if recovered:
            amounts.update(recovered)

    return amounts



def lossq_beta_apply_recovered_amounts(item):
    if not isinstance(item, dict):
        return item, {}

    def current_amount(key):
        return lossq_beta_money_to_float(item.get(key))

    current_paid = current_amount("paid_amount")
    current_reserve = current_amount("reserve_amount")
    current_total = current_amount("total_incurred")

    text_amounts = lossq_beta_extract_money_triplet_from_text(item)

    use_text_override = False
    override_reason = ""

    if text_amounts and any(lossq_beta_money_to_float(v) > 0 for v in text_amounts.values()):
        text_paid = lossq_beta_money_to_float(text_amounts.get("paid_amount"))
        text_reserve = lossq_beta_money_to_float(text_amounts.get("reserve_amount"))
        text_total = lossq_beta_money_to_float(text_amounts.get("total_incurred"))

        text_total_matches_parts = abs((text_paid + text_reserve) - text_total) <= max(2.0, text_total * 0.02)

        current_total_conflicts = (
            current_total > 0
            and text_total > 0
            and abs(current_total - text_total) > max(100.0, text_total * 0.10)
        )

        current_amounts_missing = (
            current_paid <= 0
            or ("reserve_amount" not in item and "reserve" not in item)
            or current_total <= 0
        )

        # LOSSQ_ROW_TEXT_AMOUNT_OVERRIDE_V1
        # Universal safeguard:
        # If the claim narrative/row text contains a clean paid + reserve = total triplet,
        # trust that row-level triplet over a conflicting summary/header amount.
        if text_total_matches_parts and (current_total_conflicts or current_amounts_missing):
            use_text_override = True
            override_reason = "row_text_triplet_conflict" if current_total_conflicts else "row_text_triplet_missing_amounts"

    if use_text_override:
        amounts = text_amounts
    else:
        amounts = lossq_beta_get_claim_amounts(item)

    if not amounts or not any(lossq_beta_money_to_float(value) > 0 for value in amounts.values()):
        return item, {}

    changed = {}

    for key in ["paid_amount", "reserve_amount", "total_incurred"]:
        current = lossq_beta_money_to_float(item.get(key))
        recovered = lossq_beta_money_to_float(amounts.get(key))

        should_replace = False

        if use_text_override:
            should_replace = True
        elif current <= 0 and recovered >= 0:
            should_replace = True

        if should_replace:
            before = item.get(key)
            item[key] = recovered
            if str(before) != str(recovered):
                changed[key] = recovered

    if changed:
        print("LOSSQ_BETA_AMOUNT_RECOVERY_APPLIED:", {
            "claim_number": lossq_beta_clean_text(
                item.get("claim_number") or item.get("claim_id") or item.get("Claim Number")
            ),
            "policy_number": lossq_beta_clean_text(
                item.get("policy_number") or item.get("Policy Number") or item.get("policy")
            ),
            "reason": override_reason or "missing_amount_recovery",
            **changed,
        })

    return item, changed



def lossq_beta_has_commercial_line_context(item):
    if not isinstance(item, dict):
        return False

    text_value = " ".join(
        str(value or "")
        for key, value in item.items()
        if key in {
            "line_of_business",
            "claim_type",
            "policy_type",
            "coverage",
            "Coverage",
            "Line of Business",
            "description",
            "loss_description",
            "claim_description",
            "cause_of_loss",
        }
    ).upper()

    line_terms = [
        "GENERAL LIABILITY",
        "LIQUOR LIABILITY",
        "WORKERS COMPENSATION",
        "WORKERS COMP",
        "BUSINESSOWNERS POLICY",
        "BUSINESS OWNERS POLICY",
        "BOP",
        "CYBER LIABILITY",
        "CYBER",
        "COMMERCIAL AUTO",
        "AUTO LIABILITY",
        "CARGO",
        "PROPERTY",
        "UMBRELLA",
        "EXCESS",
        "EPLI",
        "EMPLOYMENT PRACTICES",
        "DIRECTORS AND OFFICERS",
        "D&O",
        "PROFESSIONAL LIABILITY",
        "ERRORS AND OMISSIONS",
        "E&O",
        "INLAND MARINE",
        "CRIME",
        "ABUSE",
        "MOLESTATION",
        "GARAGE",
    ]

    return any(term in text_value for term in line_terms)


def lossq_beta_has_real_claim_row_evidence(item):
    if not isinstance(item, dict):
        return False

    description = lossq_beta_clean_text(
        item.get("description")
        or item.get("loss_description")
        or item.get("claim_description")
        or item.get("cause_of_loss")
        or ""
    )

    policy_number = (
        item.get("policy_number")
        or item.get("Policy Number")
        or item.get("policy_no")
        or item.get("policy")
        or ""
    )

    has_policy_context = bool(policy_number and lossq_beta_valid_policy_key(policy_number))
    has_line_context = lossq_beta_has_commercial_line_context(item)

    amounts = lossq_beta_get_claim_amounts(item)
    has_financial_context = bool(amounts and any(value > 0 for value in amounts.values()))

    has_loss_narrative = bool(len(description) >= 12 and re.search(r"[A-Za-z]", description))

    # Universal claim-row test:
    # A row can survive an imperfect/generated claim number only if the row still
    # looks like an actual claim: commercial line + financial values + policy or narrative context.
    return bool(
        has_line_context
        and has_financial_context
        and (has_policy_context or has_loss_narrative)
    )


def lossq_beta_filter_claim_rows(parsed_claims):
    clean_claims = []
    removed_rows = []

    for item in parsed_claims or []:
        if not isinstance(item, dict):
            removed_rows.append({"reason": "not_dict", "row": str(item)[:160]})
            continue

        item, recovered_amounts = lossq_beta_apply_recovered_amounts(item)

        claim_number = (
            item.get("claim_number")
            or item.get("Claim Number")
            or item.get("claim_id")
            or item.get("Claim ID")
            or item.get("claim_no")
            or ""
        )

        policy_number = (
            item.get("policy_number")
            or item.get("Policy Number")
            or item.get("policy_no")
            or item.get("Policy No")
            or item.get("policy")
            or ""
        )

        description = (
            item.get("description")
            or item.get("loss_description")
            or item.get("claim_description")
            or ""
        )

        valid_claim_number = lossq_beta_valid_claim_number(claim_number)
        real_claim_evidence = lossq_beta_has_real_claim_row_evidence(item)

        if not valid_claim_number and not real_claim_evidence:
            removed_rows.append({
                "reason": "invalid_claim_number",
                "claim_number": lossq_beta_clean_text(claim_number),
                "description": lossq_beta_clean_text(description)[:120],
            })
            continue

        # Keep claim if policy is valid or parser will fallback later.
        if policy_number and not lossq_beta_valid_policy_key(policy_number):
            removed_rows.append({
                "reason": "invalid_policy_number",
                "claim_number": lossq_beta_clean_text(claim_number),
                "policy_number": lossq_beta_clean_text(policy_number),
            })
            continue

        if real_claim_evidence and not valid_claim_number:
            print("LOSSQ_BETA_REAL_CLAIM_ROW_RESCUED:", {
                "claim_number": lossq_beta_clean_text(claim_number),
                "policy_number": lossq_beta_clean_text(policy_number),
                "line_of_business": lossq_beta_clean_text(
                    item.get("line_of_business") or item.get("claim_type") or item.get("policy_type")
                ),
                "paid_amount": item.get("paid_amount"),
                "reserve_amount": item.get("reserve_amount"),
                "total_incurred": item.get("total_incurred"),
            })

        clean_claims.append(item)

    return clean_claims, removed_rows



def lossq_beta_collect_upload_policy_keys(parsed_profile, parsed_claims, fallback_policy_number=""):
    keys = set()

    def add(value):
        value = lossq_beta_norm_key(value)
        if lossq_beta_valid_policy_key(value):
            keys.add(value)

    if isinstance(parsed_profile, dict):
        for name in ["policy_number", "account_number", "customer_number", "main_policy_number"]:
            add(parsed_profile.get(name))

        policies = parsed_profile.get("policies") or parsed_profile.get("policy_schedule") or []
        if isinstance(policies, list):
            for policy in policies:
                if isinstance(policy, dict):
                    add(policy.get("policy_number") or policy.get("policy") or policy.get("policy_no"))

    for claim in parsed_claims or []:
        if isinstance(claim, dict):
            add(claim.get("policy_number") or claim.get("policy") or claim.get("policy_no"))

    add(fallback_policy_number)

    return sorted(keys)

def lossq_beta_purge_prior_upload_data(db, current_user, policy_keys):
    result = {
        "policy_keys": policy_keys or [],
        "deleted_claims": 0,
        "deleted_upload_history": 0,
    }

    if not db or not current_user or not policy_keys:
        return result

    org_id = current_user.get("organization_id") if isinstance(current_user, dict) else None
    if not org_id:
        return result

    upper_keys = [lossq_beta_norm_key(key) for key in policy_keys if lossq_beta_valid_policy_key(key)]
    if not upper_keys:
        return result

    try:
        deleted_claims = (
            db.query(Claim)
            .filter(Claim.organization_id == org_id)
            .filter(func.upper(func.trim(Claim.policy_number)).in_(upper_keys))
            .delete(synchronize_session=False)
        )
        result["deleted_claims"] = int(deleted_claims or 0)
    except Exception as exc:
        result["claim_purge_warning"] = str(exc)[:200]

    try:
        if "UploadHistory" in globals():
            deleted_uploads = (
                db.query(UploadHistory)
                .filter(UploadHistory.organization_id == org_id)
                .filter(func.upper(func.trim(UploadHistory.policy_number)).in_(upper_keys))
                .delete(synchronize_session=False)
            )
            result["deleted_upload_history"] = int(deleted_uploads or 0)
    except Exception as exc:
        result["upload_history_purge_warning"] = str(exc)[:200]

    return result




# LOSSQ_SECTION_CSV_PROFILE_DATE_REPAIR_V1
# LOSSQ_PRODUCING_AGENCY_EXTRACTION_V1
def lossq_section_csv_clean(value):
    return re.sub(r"\s+", " ", str(value or "").strip())

def lossq_section_csv_key(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

def lossq_section_csv_date(value):
    raw = lossq_section_csv_clean(value)
    if not raw:
        return ""

    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$", raw)
    if m:
        month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if year < 100:
            year += 2000 if year < 50 else 1900
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{month:02d}/{day:02d}/{year}"

    m = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$", raw)
    if m:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{month:02d}/{day:02d}/{year}"

    return raw

def lossq_section_csv_valid_carrier(value):
    text_value = lossq_section_csv_clean(value)
    low = text_value.lower()

    if not text_value:
        return False

    bad_exact = {
        "carrier",
        "writing carrier",
        "effective date",
        "expiration date",
        "valuation date",
        "evaluation date",
        "as of date",
        "policy number",
        "main policy",
        "account number",
        "producer",
        "named insured",
    }

    if low in bad_exact:
        return False

    if re.match(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$", text_value):
        return False

    return True

def lossq_section_csv_apply_profile_date_repair(file_path, parsed_profile):
    """
    Universal repair for section-based CSV loss runs.

    It reads Account Information and Policy Schedule sections directly from the CSV,
    then merges dates/carrier/account/policies into parsed_profile before saving.
    """
    parsed_profile = parsed_profile or {}

    try:
        import csv as _csv

        with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
            rows = [row for row in _csv.reader(f)]
    except Exception:
        return parsed_profile

    account_info = {}
    policies = []
    current_header = []

    for raw_row in rows:
        row = [lossq_section_csv_clean(cell) for cell in raw_row]
        if not any(row):
            continue

        first = row[0].strip()
        first_key = lossq_section_csv_key(first)

        # Three-column Account Information rows:
        # Section, Field, Value
        if first_key == "accountinformation" and len(row) >= 3:
            field = lossq_section_csv_key(row[1])
            value = row[2]

            if field in {"carrier", "carriercarriername"} and lossq_section_csv_valid_carrier(value):
                lossq_set_once(account_info, "carrier_name", value)
            elif field in {"writingcarrier"} and lossq_section_csv_valid_carrier(value):
                lossq_set_once(account_info, "writing_carrier", value)
            elif field in {"namedinsured", "insured", "businessname"}:
                account_info["business_name"] = value
                account_info["named_insured"] = value
            elif field in {"producer", "producingagency", "agency", "agencyname", "broker", "brokerage"}:
                account_info["agency_name"] = value
                account_info["producer"] = value
                account_info["producing_agency"] = value
            elif field in {"accountnumber", "customernumber"}:
                account_info["account_number"] = value
                account_info["customer_number"] = value
            elif field in {"mainpolicy", "mainpolicynumber", "policynumber"}:
                lossq_set_once(account_info, "policy_number", value)
            elif field in {"effectivedate", "policyeffectivedate", "effective"}:
                account_info["effective_date"] = lossq_section_csv_date(value)
                account_info["policy_effective_date"] = lossq_section_csv_date(value)
            elif field in {"expirationdate", "expirydate", "policyexpirationdate", "expiration"}:
                account_info["expiration_date"] = lossq_section_csv_date(value)
                account_info["policy_expiration_date"] = lossq_section_csv_date(value)
            elif field in {"valuationdate", "evaluationdate", "asofdate", "reportdate"}:
                fixed_date = lossq_section_csv_date(value)
                account_info["valuation_date"] = fixed_date
                account_info["evaluation_date"] = fixed_date
                account_info["loss_run_valuation_date"] = fixed_date

            continue

        # Header rows.
        if first_key == "section" and len(row) > 1:
            current_header = row
            continue

        # Policy Schedule rows that follow:
        # Section, Policy Number, Line of Business, Carrier, Effective Date, Expiration Date...
        if first_key == "policyschedule" and current_header:
            mapped = {}
            for idx, header_name in enumerate(current_header):
                if idx >= len(row):
                    continue
                key = lossq_section_csv_key(header_name)
                value = row[idx]

                if key == "policynumber":
                    mapped["policy_number"] = value
                elif key in {"lineofbusiness", "policytype", "coverage", "linecoverage"}:
                    mapped["line_of_business"] = value
                    mapped["policy_type"] = value
                    mapped["coverage"] = value
                elif key in {"carrier", "carriername", "writingcarrier"} and lossq_section_csv_valid_carrier(value):
                    mapped["carrier"] = value
                    mapped["carrier_name"] = value
                elif key in {"effectivedate", "policyeffectivedate", "effective"}:
                    mapped["effective_date"] = lossq_section_csv_date(value)
                    mapped["policy_effective_date"] = lossq_section_csv_date(value)
                elif key in {"expirationdate", "expirydate", "policyexpirationdate", "expiration"}:
                    mapped["expiration_date"] = lossq_section_csv_date(value)
                    mapped["policy_expiration_date"] = lossq_section_csv_date(value)
                elif key in {"currentpremium", "premium"}:
                    mapped["current_premium"] = value
                elif key in {"exposurebasis"}:
                    mapped["exposure_basis"] = value
                elif key in {"exposurevalue"}:
                    mapped["exposure_value"] = value
                elif key == "state":
                    mapped["state"] = value

            if mapped.get("policy_number"):
                policies.append(mapped)

    for key, value in account_info.items():
        if value:
            parsed_profile[key] = value

    if policies:
        parsed_profile["policies"] = policies
        parsed_profile["policy_schedule"] = policies

        if not parsed_profile.get("policy_number"):
            parsed_profile["policy_number"] = policies[0].get("policy_number", "")

        if not parsed_profile.get("effective_date"):
            parsed_profile["effective_date"] = policies[0].get("effective_date", "")
            parsed_profile["policy_effective_date"] = policies[0].get("effective_date", "")

        if not parsed_profile.get("expiration_date"):
            parsed_profile["expiration_date"] = policies[0].get("expiration_date", "")
            parsed_profile["policy_expiration_date"] = policies[0].get("expiration_date", "")

        if not parsed_profile.get("carrier_name"):
            for policy in policies:
                if lossq_section_csv_valid_carrier(policy.get("carrier_name")):
                    parsed_profile["carrier_name"] = policy.get("carrier_name")
                    break

        if not parsed_profile.get("writing_carrier"):
            parsed_profile["writing_carrier"] = parsed_profile.get("carrier_name", "")

    return parsed_profile










# LOSSQ_PROFILE_FIRST_VALID_VALUE_WINS_V1
def lossq_set_once(target, key, value):
    value = lossq_section_csv_clean(value)
    if not value:
        return

    current = lossq_section_csv_clean(target.get(key))
    if not current:
        target[key] = value


# LOSSQ_MESSY_CSV_LABEL_VALUE_VALIDATION_V1
def lossq_csv_is_header_or_label_value(value):
    clean = lossq_section_csv_clean(value)
    key = lossq_section_csv_key(clean)

    if not clean:
        return True

    label_keys = {
        "section",
        "field",
        "value",
        "policy",
        "policynumber",
        "policytype",
        "policytypecoverage",
        "lineofbusiness",
        "coverage",
        "carrier",
        "carriername",
        "writingcarrier",
        "effective",
        "effectivedate",
        "policyeffectivedate",
        "expiration",
        "expirationdate",
        "policyexpirationdate",
        "expiry",
        "expirydate",
        "annualpremium",
        "currentpremium",
        "premium",
        "exposure",
        "exposurebasis",
        "exposurevalue",
        "claims",
        "claimcount",
        "totalincurred",
        "claimdetail",
        "losssummary",
        "accountprofile",
        "policy schedule",
        "policyschedule",
        "producer",
        "producingagency",
        "agency",
        "agencyname",
        "broker",
        "brokerage",
        "adjuster",
        "claimhandler",
        "examiner",
        "downloadedby",
        "createdby",
    }

    return key in {lossq_section_csv_key(item) for item in label_keys}


def lossq_csv_valid_profile_date_value(value):
    clean = lossq_section_csv_clean(value)
    if lossq_csv_is_header_or_label_value(clean):
        return False

    if re.match(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$", clean):
        return True

    if re.match(r"^\d{4}[/-]\d{1,2}[/-]\d{1,2}$", clean):
        return True

    return False


def lossq_csv_valid_profile_text_value(value):
    clean = lossq_section_csv_clean(value)
    if lossq_csv_is_header_or_label_value(clean):
        return False

    if re.match(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$", clean):
        return False

    if re.match(r"^\d{4}[/-]\d{1,2}[/-]\d{1,2}$", clean):
        return False

    return True


def lossq_profile_date_or_blank(value):
    clean = lossq_section_csv_clean(value)

    if re.match(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$", clean):
        return lossq_section_csv_date(clean)

    if re.match(r"^\d{4}[/-]\d{1,2}[/-]\d{1,2}$", clean):
        return lossq_section_csv_date(clean)

    return ""


# LOSSQ_MESSY_CSV_LABEL_PAIR_PROFILE_REPAIR_V1

# LOSSQ_POLICY_PERIOD_RANGE_SPLIT_V1
def lossq_policy_period_range_dates(value):
    """
    Universal parser for combined policy period values like:
    03/01/2025 - 03/01/2026
    03/01/2025 to 03/01/2026
    Effective 03/01/2025 Expiration 03/01/2026
    """
    try:
        import re

        clean = lossq_section_csv_clean(value)
        if not clean:
            return "", ""

        date_matches = re.findall(
            r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b",
            clean,
        )

        if len(date_matches) >= 2:
            effective = lossq_profile_date_or_blank(date_matches[0])
            expiration = lossq_profile_date_or_blank(date_matches[1])
            return effective, expiration

        return "", ""
    except Exception as exc:
        print("LOSSQ_POLICY_PERIOD_RANGE_SPLIT_ERROR:", str(exc)[:200])
        return "", ""


def lossq_csv_label_pair_profile_repair(file_path, parsed_profile):
    """
    Universal repair for messy CSV exports where account profile fields are stored
    as label/value pairs across rows instead of Section, Field, Value format.

    Example:
    Policy Effective Date, 01/01/2025, Policy Expiration Date, 01/01/2026
    Evaluation Date, 06/30/2025
    """
    parsed_profile = parsed_profile or {}

    filename = str(file_path or "").lower()
    if not filename.endswith(".csv"):
        return parsed_profile

    try:
        import csv as _csv

        with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
            rows = [row for row in _csv.reader(f)]
    except Exception:
        return parsed_profile

    account_info = {}
    policies = []

    def put_profile(label, value):
        field = lossq_section_csv_key(label)
        value = lossq_section_csv_clean(value)

        if not value:
            return

        if field in {"namedinsured", "insured", "businessname", "accountname"} and lossq_csv_valid_profile_text_value(value):
            lossq_set_once(account_info, "business_name", value)
            lossq_set_once(account_info, "named_insured", value)
            lossq_set_once(account_info, "insured", value)

        elif field in {"dba"} and lossq_csv_valid_profile_text_value(value):
            lossq_set_once(account_info, "dba", value)

        elif field in {"carrier", "carriername", "insurancecarrier"} and lossq_section_csv_valid_carrier(value) and lossq_csv_valid_profile_text_value(value):
            lossq_set_once(account_info, "carrier_name", value)

        elif field in {"writingcarrier", "underwritingcarrier"} and lossq_section_csv_valid_carrier(value) and lossq_csv_valid_profile_text_value(value):
            lossq_set_once(account_info, "writing_carrier", value)

        elif field in {"producingagency", "producer", "agency", "agencyname", "broker", "brokerage"} and lossq_csv_valid_profile_text_value(value):
            lossq_set_once(account_info, "agency_name", value)
            lossq_set_once(account_info, "producer", value)
            lossq_set_once(account_info, "producing_agency", value)

        elif field in {"accountnumber", "customernumber", "accountid"} and lossq_csv_valid_profile_text_value(value):
            lossq_set_once(account_info, "account_number", value)
            lossq_set_once(account_info, "customer_number", value)

        elif field in {"mainpolicy", "mainpolicynumber", "policynumber"} and lossq_csv_valid_profile_text_value(value):
            lossq_set_once(account_info, "policy_number", value)

        elif field in {"policyeffectivedate", "effectivedate", "effective"} and lossq_csv_valid_profile_date_value(value):
            fixed = lossq_section_csv_date(value)
            account_info["effective_date"] = fixed
            account_info["policy_effective_date"] = fixed

        elif field in {"policyexpirationdate", "expirationdate", "expirydate", "expiration", "expiry"} and lossq_csv_valid_profile_date_value(value):
            fixed = lossq_section_csv_date(value)
            account_info["expiration_date"] = fixed
            account_info["policy_expiration_date"] = fixed

        elif field in {"policyperiod", "policyterm", "period", "coverageperiod", "policydates", "daterange"}:
            effective, expiration = lossq_policy_period_range_dates(value)
            if effective and not account_info.get("effective_date"):
                account_info["effective_date"] = effective
                account_info["policy_effective_date"] = effective
            if expiration and not account_info.get("expiration_date"):
                account_info["expiration_date"] = expiration
                account_info["policy_expiration_date"] = expiration
            if effective or expiration:
                print("LOSSQ_POLICY_PERIOD_RANGE_PROFILE_DATES:", {
                    "effective_date": account_info.get("effective_date"),
                    "expiration_date": account_info.get("expiration_date"),
                })

        elif field in {"evaluationdate", "valuationdate", "valuedasof", "asofdate", "reportdate", "lossrunvaluationdate"} and lossq_csv_valid_profile_date_value(value):
            fixed = lossq_section_csv_date(value)
            account_info["evaluation_date"] = fixed
            account_info["valuation_date"] = fixed
            account_info["loss_run_valuation_date"] = fixed

    # LOSSQ_MESSY_CSV_PROFILE_SCAN_STOPS_BEFORE_CLAIMS_V1
    # Read label/value pairs only from account/profile area. Claim detail rows may include
    # producers, adjusters, examiners, or claim handlers that are not the producing agency.
    for row in rows[:80]:
        clean_row = [lossq_section_csv_clean(cell) for cell in row]
        row_key_text = " ".join(lossq_section_csv_key(cell) for cell in clean_row)

        if any(stop_key in row_key_text for stop_key in [
            "claimdetail",
            "claimnumber",
            "dateofloss",
            "losssummary",
            "trailingexportnoise",
            "underwritingnotes",
        ]):
            break

        for idx in range(0, len(clean_row) - 1):
            label = clean_row[idx]
            value = clean_row[idx + 1]

            if not label or not value:
                continue

            put_profile(label, value)


    # LOSSQ_PROFILE_DATES_FROM_POLICY_SCHEDULE_V1
    # If the account-level dates were not captured from label/value rows,
    # use the first valid policy schedule effective/expiration dates.
    try:
        schedule_rows = account_info.get("policies") or account_info.get("policy_schedule") or []
        if isinstance(schedule_rows, list):
            for policy_row in schedule_rows:
                if not isinstance(policy_row, dict):
                    continue

                effective = (
                    policy_row.get("effective_date")
                    or policy_row.get("policy_effective_date")
                    or policy_row.get("effective")
                )
                expiration = (
                    policy_row.get("expiration_date")
                    or policy_row.get("policy_expiration_date")
                    or policy_row.get("expiration")
                    or policy_row.get("expiry_date")
                )

                if effective and not account_info.get("effective_date"):
                    fixed_effective = lossq_section_csv_date(effective)
                    account_info["effective_date"] = fixed_effective
                    account_info["policy_effective_date"] = fixed_effective

                if expiration and not account_info.get("expiration_date"):
                    fixed_expiration = lossq_section_csv_date(expiration)
                    account_info["expiration_date"] = fixed_expiration
                    account_info["policy_expiration_date"] = fixed_expiration

                if account_info.get("effective_date") and account_info.get("expiration_date"):
                    break
    except Exception as exc:
        print("LOSSQ_PROFILE_DATES_FROM_POLICY_SCHEDULE_ERROR:", str(exc)[:200])


    # Parse policy schedule tables with columns like:
    # Policy Type / Coverage, Policy Number, Carrier, Effective, Expiration...
    for idx, raw_row in enumerate(rows):
        header = [lossq_section_csv_clean(cell) for cell in raw_row]
        header_keys = [lossq_section_csv_key(cell) for cell in header]

        if "policynumber" not in header_keys:
            continue

        if not any(key in header_keys for key in ["policytypecoverage", "lineofbusiness", "coverage", "policytype", "coverageline", "linecoverage"]):
            continue

        # Found a policy schedule header.
        for data_row in rows[idx + 1:]:
            row = [lossq_section_csv_clean(cell) for cell in data_row]

            if not any(row):
                break

            first_key = lossq_section_csv_key(row[0] if row else "")
            if first_key in {"claimdetail", "losssummary", "trailingexportnoise", "underwritingnotes"}:
                break

            mapped = {}

            for col_index, header_key in enumerate(header_keys):
                if col_index >= len(row):
                    continue

                value = row[col_index]

                if header_key in {"policytypecoverage", "lineofbusiness", "coverage", "policytype", "coverageline", "linecoverage"}:
                    mapped["line_of_business"] = value
                    mapped["policy_type"] = value
                    mapped["coverage"] = value

                elif header_key in {"policynumber", "policy", "policyno", "policynum"}:
                    mapped["policy_number"] = value

                elif header_key in {"carrier", "carriername", "writingcarrier"} and lossq_section_csv_valid_carrier(value):
                    mapped["carrier"] = value
                    mapped["carrier_name"] = value
                    mapped["writing_carrier"] = value

                elif header_key in {"effective", "effectivedate", "policyeffectivedate"}:
                    fixed = lossq_section_csv_date(value)
                    mapped["effective_date"] = fixed
                    mapped["policy_effective_date"] = fixed

                elif header_key in {"expiration", "expirationdate", "expiry", "expirydate", "policyexpirationdate"}:
                    fixed = lossq_section_csv_date(value)
                    mapped["expiration_date"] = fixed
                    mapped["policy_expiration_date"] = fixed

                # LOSSQ_POLICY_PERIOD_RANGE_SCHEDULE_DATES_V1
                elif header_key in {"policyperiod", "policyterm", "period", "coverageperiod", "policydates", "daterange"}:
                    effective, expiration = lossq_policy_period_range_dates(value)

                    if effective:
                        mapped["effective_date"] = effective
                        mapped["policy_effective_date"] = effective

                    if expiration:
                        mapped["expiration_date"] = expiration
                        mapped["policy_expiration_date"] = expiration

                    if effective or expiration:
                        print("LOSSQ_POLICY_PERIOD_RANGE_SCHEDULE_DATES:", {
                            "policy_number": mapped.get("policy_number"),
                            "effective_date": mapped.get("effective_date"),
                            "expiration_date": mapped.get("expiration_date"),
                        })

                elif header_key in {"annualpremium", "currentpremium", "premium"}:
                    mapped["current_premium"] = value

                elif header_key in {"exposurebasis", "exposure"}:
                    mapped["exposure_basis"] = value

                elif header_key in {"claims", "claimcount"}:
                    mapped["claim_count"] = value

                elif header_key in {"totalincurred", "incurred"}:
                    mapped["total_incurred"] = value

            if mapped.get("policy_number"):
                policies.append(mapped)

        break

    # LOSSQ_DATES_AFTER_POLICY_SCHEDULE_PARSE_V1
    # Policy schedule rows are parsed above. Now copy the first valid policy
    # effective/expiration dates back to the account profile if missing.
    try:
        if policies:
            for policy_row in policies:
                if not isinstance(policy_row, dict):
                    continue

                effective = (
                    policy_row.get("effective_date")
                    or policy_row.get("policy_effective_date")
                    or policy_row.get("effective")
                )
                expiration = (
                    policy_row.get("expiration_date")
                    or policy_row.get("policy_expiration_date")
                    or policy_row.get("expiration")
                    or policy_row.get("expiry_date")
                )

                fixed_effective = lossq_profile_date_or_blank(effective)
                fixed_expiration = lossq_profile_date_or_blank(expiration)

                if fixed_effective and not account_info.get("effective_date"):
                    account_info["effective_date"] = fixed_effective
                    account_info["policy_effective_date"] = fixed_effective

                if fixed_expiration and not account_info.get("expiration_date"):
                    account_info["expiration_date"] = fixed_expiration
                    account_info["policy_expiration_date"] = fixed_expiration

                if account_info.get("effective_date") and account_info.get("expiration_date"):
                    print("LOSSQ_DATES_AFTER_POLICY_SCHEDULE_PARSE:", {
                        "effective_date": account_info.get("effective_date"),
                        "expiration_date": account_info.get("expiration_date"),
                    })
                    break
    except Exception as exc:
        print("LOSSQ_DATES_AFTER_POLICY_SCHEDULE_PARSE_ERROR:", str(exc)[:200])


    # LOSSQ_FINAL_CSV_ACCOUNT_DATES_AFTER_POLICY_PARSE_V2
    # Policy schedule rows have already been parsed into `policies`.
    # If account-level effective/expiration dates are blank, copy the first valid
    # policy schedule dates back onto the account profile before final merge/save.
    try:
        if policies:
            for policy_row in policies:
                if not isinstance(policy_row, dict):
                    continue

                effective = (
                    policy_row.get("effective_date")
                    or policy_row.get("policy_effective_date")
                    or policy_row.get("effective")
                    or policy_row.get("Effective Date")
                    or policy_row.get("Policy Effective Date")
                )

                expiration = (
                    policy_row.get("expiration_date")
                    or policy_row.get("policy_expiration_date")
                    or policy_row.get("expiration")
                    or policy_row.get("expiry_date")
                    or policy_row.get("Expiration Date")
                    or policy_row.get("Policy Expiration Date")
                )

                fixed_effective = lossq_profile_date_or_blank(effective)
                fixed_expiration = lossq_profile_date_or_blank(expiration)

                if fixed_effective and not account_info.get("effective_date"):
                    account_info["effective_date"] = fixed_effective
                    account_info["policy_effective_date"] = fixed_effective

                if fixed_expiration and not account_info.get("expiration_date"):
                    account_info["expiration_date"] = fixed_expiration
                    account_info["policy_expiration_date"] = fixed_expiration

                if account_info.get("effective_date") and account_info.get("expiration_date"):
                    print("LOSSQ_FINAL_CSV_ACCOUNT_DATES_AFTER_POLICY_PARSE:", {
                        "effective_date": account_info.get("effective_date"),
                        "expiration_date": account_info.get("expiration_date"),
                    })
                    break
    except Exception as exc:
        print("LOSSQ_FINAL_CSV_ACCOUNT_DATES_AFTER_POLICY_PARSE_ERROR:", str(exc)[:200])


    for key, value in account_info.items():
        if value:
            parsed_profile[key] = value

    if policies:
        parsed_profile["policies"] = policies
        parsed_profile["policy_schedule"] = policies

        if not parsed_profile.get("policy_number"):
            parsed_profile["policy_number"] = policies[0].get("policy_number", "")

        if not parsed_profile.get("effective_date"):
            parsed_profile["effective_date"] = policies[0].get("effective_date", "")
            parsed_profile["policy_effective_date"] = policies[0].get("effective_date", "")

        if not parsed_profile.get("expiration_date"):
            parsed_profile["expiration_date"] = policies[0].get("expiration_date", "")
            parsed_profile["policy_expiration_date"] = policies[0].get("expiration_date", "")

        if not parsed_profile.get("carrier_name"):
            for policy in policies:
                if lossq_section_csv_valid_carrier(policy.get("carrier_name")):
                    parsed_profile["carrier_name"] = policy.get("carrier_name")
                    break

        if not parsed_profile.get("writing_carrier"):
            parsed_profile["writing_carrier"] = parsed_profile.get("carrier_name", "")

    return parsed_profile


# LOSSQ_PDF_PROFILE_CLEANUP_V1
def lossq_pdf_profile_bad_value(value):
    clean = lossq_section_csv_clean(value)
    low = clean.lower()

    if not clean:
        return True

    bad = {
        "effective",
        "effective date",
        "expiration",
        "expiration date",
        "expiry",
        "expiry date",
        "policy",
        "policy number",
        "carrier",
        "writing carrier",
        "insured",
        "named insured",
        "producer",
        "agency",
        "not set",
        "-",
    }

    if low in bad:
        return True

    if re.match(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$", clean):
        return True

    if re.match(r"^\d{4}[/-]\d{1,2}[/-]\d{1,2}$", clean):
        return True

    return False


def lossq_pdf_profile_extract_date_after_label(raw_text, labels):
    text_value = str(raw_text or "")
    if not text_value:
        return ""

    for label in labels:
        pattern = rf"{label}\s*[:#-]?\s*(\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{2,4}}|\d{{4}}[/-]\d{{1,2}}[/-]\d{{1,2}})"
        match = re.search(pattern, text_value, flags=re.IGNORECASE)
        if match:
            return lossq_section_csv_date(match.group(1))

    return ""


def lossq_pdf_profile_extract_policy_period(raw_text):
    text_value = str(raw_text or "")
    if not text_value:
        return "", ""

    compact = re.sub(r"[ \t]+", " ", text_value)
    compact = re.sub(r"\r\n|\r", "\n", compact)

    # LOSSQ_UNIVERSAL_PDF_POLICY_PERIOD_EXTRACTION_V2
    # Universal policy period patterns commonly found in carrier loss runs.
    patterns = [
        r"policy\s*period\s*[:#-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\s*(?:-|to|through|thru|until)\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})",
        r"policy\s*term\s*[:#-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\s*(?:-|to|through|thru|until)\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})",
        r"coverage\s*period\s*[:#-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\s*(?:-|to|through|thru|until)\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})",
        r"effective\s*(?:date)?\s*[:#-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}).{0,160}?expir(?:ation|y)?\s*(?:date)?\s*[:#-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})",
        r"\beff\.?\s*[:#-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}).{0,160}?\bexp\.?\s*[:#-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})",
        r"\bfrom\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\s*(?:-|to|through|thru|until)\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})",
    ]

    for pattern in patterns:
        match = re.search(pattern, compact, flags=re.IGNORECASE | re.DOTALL)
        if match:
            first = lossq_section_csv_date(match.group(1))
            second = lossq_section_csv_date(match.group(2))
            if first and second and first != second:
                return first, second

    # Fallback: find two dates near policy/term/effective/expiration wording.
    lines = [line.strip() for line in compact.split("\n") if line.strip()]
    date_pattern = r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})"

    for idx, line in enumerate(lines):
        window = " ".join(lines[max(0, idx - 3): min(len(lines), idx + 4)])
        low = window.lower()

        if not any(term in low for term in ["policy", "period", "effective", "expiration", "expiry", "coverage", "term", "eff", "exp"]):
            continue

        dates = re.findall(date_pattern, window)
        cleaned_dates = []
        for d in dates:
            fixed = lossq_section_csv_date(d)
            if fixed and fixed not in cleaned_dates:
                cleaned_dates.append(fixed)

        if len(cleaned_dates) >= 2:
            return cleaned_dates[0], cleaned_dates[1]

    effective = lossq_pdf_profile_extract_date_after_label(
        compact,
        [
            r"effective\s*date",
            r"policy\s*effective\s*date",
            r"coverage\s*effective\s*date",
            r"\beff\.?",
            r"effective",
        ],
    )

    expiration = lossq_pdf_profile_extract_date_after_label(
        compact,
        [
            r"expiration\s*date",
            r"expiry\s*date",
            r"policy\s*expiration\s*date",
            r"coverage\s*expiration\s*date",
            r"\bexp\.?",
            r"expiration",
            r"expiry",
        ],
    )

    return effective, expiration


def lossq_pdf_profile_extract_evaluation_date(raw_text):
    text_value = str(raw_text or "")

    return lossq_pdf_profile_extract_date_after_label(
        text_value,
        [
            r"valuation\s*date",
            r"evaluation\s*date",
            r"loss\s*run\s*valuation\s*date",
            r"loss\s*run\s*date",
            r"as\s*of\s*date",
            r"report\s*date",
        ],
    )


def lossq_pdf_profile_repair(file_path, parsed_profile):
    parsed_profile = parsed_profile or {}

    raw_text = (
        parsed_profile.get("raw_text")
        or parsed_profile.get("raw_text_preview")
        or parsed_profile.get("text")
        or parsed_profile.get("ocr_text")
        or ""
    )

    # LOSSQ_PDF_RAW_TEXT_REPAIR_RUNS_ON_RAW_TEXT_V1
    # Run this repair whenever extracted raw text exists. Temp upload paths may not preserve .pdf extension.
    if not raw_text:
        return parsed_profile

    # Clean fake carrier values.
    for key in ["carrier_name", "writing_carrier", "carrier"]:
        if lossq_pdf_profile_bad_value(parsed_profile.get(key)):
            parsed_profile[key] = ""

    # Never use today's date as evaluation date unless the document actually supplied it.
    extracted_eval = lossq_pdf_profile_extract_evaluation_date(raw_text)
    if extracted_eval:
        parsed_profile["evaluation_date"] = extracted_eval
        parsed_profile["valuation_date"] = extracted_eval
        parsed_profile["loss_run_valuation_date"] = extracted_eval
    else:
        # If a parser supplied today's date as a fallback, remove it so frontend can warn accurately.
        parsed_profile["evaluation_date"] = parsed_profile.get("evaluation_date") or ""
        parsed_profile["valuation_date"] = parsed_profile.get("valuation_date") or ""
        parsed_profile["loss_run_valuation_date"] = parsed_profile.get("loss_run_valuation_date") or ""

    effective, expiration = lossq_pdf_profile_extract_policy_period(raw_text)

    if effective and not parsed_profile.get("effective_date"):
        parsed_profile["effective_date"] = effective
        parsed_profile["policy_effective_date"] = effective

    if expiration and not parsed_profile.get("expiration_date"):
        parsed_profile["expiration_date"] = expiration
        parsed_profile["policy_expiration_date"] = expiration

    # If profile dates exist but policy schedule rows are missing dates/carrier, fill the schedule rows.
    policies = parsed_profile.get("policies") or parsed_profile.get("policy_schedule") or []
    if isinstance(policies, list):
        cleaned_policies = []
        for policy in policies:
            if not isinstance(policy, dict):
                continue

            next_policy = dict(policy)

            if lossq_pdf_profile_bad_value(next_policy.get("carrier")):
                next_policy["carrier"] = parsed_profile.get("carrier_name") or parsed_profile.get("writing_carrier") or ""
            if lossq_pdf_profile_bad_value(next_policy.get("carrier_name")):
                next_policy["carrier_name"] = parsed_profile.get("carrier_name") or parsed_profile.get("writing_carrier") or ""

            if not next_policy.get("effective_date") and parsed_profile.get("effective_date"):
                next_policy["effective_date"] = parsed_profile.get("effective_date")
                next_policy["policy_effective_date"] = parsed_profile.get("effective_date")

            if not next_policy.get("expiration_date") and parsed_profile.get("expiration_date"):
                next_policy["expiration_date"] = parsed_profile.get("expiration_date")
                next_policy["policy_expiration_date"] = parsed_profile.get("expiration_date")

            cleaned_policies.append(next_policy)

        parsed_profile["policies"] = cleaned_policies
        parsed_profile["policy_schedule"] = cleaned_policies

    return parsed_profile







# LOSSQ_LINE_OF_BUSINESS_FROM_POLICY_PREFIX_V1
def lossq_line_of_business_from_policy_prefix(value):
    """
    Universal line-of-business correction from policy/claim prefixes.
    Prevents CARGO, BOP, and UMB rows from being displayed as generic Commercial Auto or GL.
    """
    try:
        import re

        token = str(value or "").upper().strip()
        if not token:
            return ""

        # Match full tokens only, not random letters inside company names.
        parts = set(re.split(r"[^A-Z0-9]+", token))

        if "CARGO" in parts or "MTC" in parts or "TRUCKCARGO" in parts:
            return "Motor Truck Cargo"

        if "BOP" in parts or "BP" in parts:
            return "Businessowners Policy"

        if "UMB" in parts or "UMBRELLA" in parts or "EXCESS" in parts:
            return "Umbrella / Excess"

        if "WC" in parts or "WORKERS" in parts or "COMP" in parts:
            return "Workers Compensation"

        if "GL" in parts or "GENERAL" in parts:
            return "General Liability"

        if "AUTO" in parts or "CA" in parts or "AL" in parts:
            return "Commercial Auto"

        if "CY" in parts or "CYBER" in parts:
            return "Cyber Liability"

        if "LIAB" in parts or "LL" in parts or "LIQUOR" in parts:
            return "Liquor Liability"

        if "PL" in parts or "PROF" in parts or "PROFESSIONAL" in parts:
            return "Professional Liability"

        if "CP" in parts or "PROPERTY" in parts:
            return "Commercial Property"

        if "EPLI" in parts:
            return "Employment Practices Liability"

        if "DO" in parts or "DNO" in parts:
            return "Directors & Officers"

        return ""
    except Exception as exc:
        print("LOSSQ_LINE_OF_BUSINESS_FROM_POLICY_PREFIX_ERROR:", str(exc)[:200])
        return ""


# LOSSQ_APPLY_LINE_OF_BUSINESS_FROM_POLICY_PREFIX_V1
def lossq_apply_line_of_business_from_policy_prefix(parsed_claims, parsed_profile=None):
    """
    Correct parsed claim and policy schedule line names using policy/claim prefixes.
    """
    try:
        parsed_claims = parsed_claims or []
        parsed_profile = parsed_profile or {}

        for claim in parsed_claims:
            if not isinstance(claim, dict):
                continue

            policy_number = (
                claim.get("policy_number")
                or claim.get("Policy Number")
                or claim.get("policy_no")
                or ""
            )

            claim_number = (
                claim.get("claim_number")
                or claim.get("Claim Number")
                or claim.get("claim_no")
                or ""
            )

            detected_line = (
                lossq_line_of_business_from_policy_prefix(policy_number)
                or lossq_line_of_business_from_policy_prefix(claim_number)
            )

            if detected_line:
                claim["line_of_business"] = detected_line
                claim["claim_type"] = detected_line
                claim["coverage"] = detected_line
                claim["policy_type"] = detected_line

        policies = parsed_profile.get("policies") or parsed_profile.get("policy_schedule") or []
        if isinstance(policies, list):
            for policy in policies:
                if not isinstance(policy, dict):
                    continue

                policy_number = (
                    policy.get("policy_number")
                    or policy.get("Policy Number")
                    or policy.get("policy_no")
                    or ""
                )

                detected_line = lossq_line_of_business_from_policy_prefix(policy_number)

                if detected_line:
                    policy["line_of_business"] = detected_line
                    policy["policy_type"] = detected_line
                    policy["coverage"] = detected_line
                    policy["line"] = detected_line

            parsed_profile["policies"] = policies
            parsed_profile["policy_schedule"] = policies

        return parsed_claims, parsed_profile
    except Exception as exc:
        print("LOSSQ_APPLY_LINE_OF_BUSINESS_FROM_POLICY_PREFIX_ERROR:", str(exc)[:200])
        return parsed_claims, parsed_profile



# LOSSQ_CLEAN_PROFILE_POLICY_SCHEDULE_ROWS_V1
def lossq_clean_profile_policy_schedule_rows(parsed_profile, parsed_claims=None):
    """
    Remove fake policy schedule rows created from claim-table text.
    Keeps real policy numbers like FPS-GL-2025-8801, but removes claim-looking
    or partial rows like GL-250012, GL-2025, WC-2025-8802, CARGO-250052.
    """
    try:
        import re

        parsed_profile = parsed_profile or {}
        parsed_claims = parsed_claims or []

        policies = parsed_profile.get("policies") or parsed_profile.get("policy_schedule") or []
        if not isinstance(policies, list):
            return parsed_profile

        claim_numbers = set()
        claim_policy_numbers = set()

        for claim in parsed_claims:
            if not isinstance(claim, dict):
                continue

            claim_number = str(
                claim.get("claim_number")
                or claim.get("Claim Number")
                or claim.get("claim_no")
                or ""
            ).strip().upper()

            policy_number = str(
                claim.get("policy_number")
                or claim.get("Policy Number")
                or claim.get("policy_no")
                or ""
            ).strip().upper()

            if claim_number:
                claim_numbers.add(claim_number)
            if policy_number:
                claim_policy_numbers.add(policy_number)

        def clean(value):
            return str(value or "").strip().upper()

        def looks_like_claim_number(value):
            value = clean(value)
            if not value:
                return True

            if value in claim_numbers:
                return True

            # Examples: GL-250012, WC-250026, BOP-250039, CARGO-250052, UMB-250067
            if re.match(r"^(GL|WC|BOP|AUTO|AU|CARGO|MTC|UMB|CY|CP|PROP|EPLI|DO|DNO)-\d{5,7}$", value):
                return True

            # Examples: GL-2025, WC-2025, BOP-2025, UMB-2025
            if re.match(r"^(GL|WC|BOP|AUTO|AU|CARGO|MTC|UMB|CY|CP|PROP|EPLI|DO|DNO)-20\d{2}$", value):
                return True

            # Examples: GL-2025-8801 or WC-2025-8802 can be claim/table fragments when
            # the same upload already has stronger real policies like FPS-GL-2025-8801.
            has_prefixed_real_policy = any(
                real_policy.endswith("-" + value) or real_policy.endswith(value)
                for real_policy in claim_policy_numbers
                if real_policy and real_policy != value
            )
            if has_prefixed_real_policy:
                return True

            return False

        cleaned_policies = []
        removed_policies = []

        for policy in policies:
            if not isinstance(policy, dict):
                continue

            policy_number = clean(
                policy.get("policy_number")
                or policy.get("Policy Number")
                or policy.get("policy")
                or policy.get("policy_no")
            )

            if looks_like_claim_number(policy_number):
                removed_policies.append(policy_number)
                continue

            cleaned_policies.append(policy)

        parsed_profile["policies"] = cleaned_policies
        parsed_profile["policy_schedule"] = cleaned_policies

        if removed_policies:
            print("LOSSQ_CLEAN_PROFILE_POLICY_SCHEDULE_REMOVED:", removed_policies[:25])

        return parsed_profile
    except Exception as exc:
        print("LOSSQ_CLEAN_PROFILE_POLICY_SCHEDULE_ERROR:", str(exc)[:200])
        return parsed_profile



# LOSSQ_FINAL_PROFILE_DATES_FROM_POLICIES_V1
def lossq_final_profile_dates_from_policies(parsed_profile):
    """
    Final universal profile repair:
    If account-level effective/expiration dates are missing, use the first valid
    effective/expiration dates from parsed policy schedule rows.
    """
    parsed_profile = parsed_profile or {}

    try:
        policy_rows = (
            parsed_profile.get("policies")
            or parsed_profile.get("policy_schedule")
            or parsed_profile.get("policySchedule")
            or []
        )

        if not isinstance(policy_rows, list):
            return parsed_profile

        for policy in policy_rows:
            if not isinstance(policy, dict):
                continue

            effective = (
                policy.get("effective_date")
                or policy.get("policy_effective_date")
                or policy.get("effective")
                or policy.get("policyEffectiveDate")
            )

            expiration = (
                policy.get("expiration_date")
                or policy.get("policy_expiration_date")
                or policy.get("expiration")
                or policy.get("expiry_date")
                or policy.get("policyExpirationDate")
            )

            fixed_effective = lossq_profile_date_or_blank(effective)
            fixed_expiration = lossq_profile_date_or_blank(expiration)

            if fixed_effective and not parsed_profile.get("effective_date"):
                parsed_profile["effective_date"] = fixed_effective
                parsed_profile["policy_effective_date"] = fixed_effective

            if fixed_expiration and not parsed_profile.get("expiration_date"):
                parsed_profile["expiration_date"] = fixed_expiration
                parsed_profile["policy_expiration_date"] = fixed_expiration

            if parsed_profile.get("effective_date") and parsed_profile.get("expiration_date"):
                break

        return parsed_profile
    except Exception as exc:
        print("LOSSQ_FINAL_PROFILE_DATES_FROM_POLICIES_ERROR:", str(exc)[:200])
        return parsed_profile



# LOSSQ_GLOBAL_PROFILE_CLEANUP_V1
def lossq_global_profile_bad_text(value):
    clean = lossq_section_csv_clean(value)
    low = clean.lower()

    if not clean:
        return True

    bad_values = {
        "effective",
        "effective date",
        "expiration",
        "expiration date",
        "expiry",
        "expiry date",
        "policy",
        "policy number",
        "carrier",
        "writing carrier",
        "insured",
        "named insured",
        "producer",
        "agency",
        "not set",
        "none",
        "null",
        "-",
    }

    if low in bad_values:
        return True

    if re.match(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$", clean):
        return True

    if re.match(r"^\d{4}[/-]\d{1,2}[/-]\d{1,2}$", clean):
        return True

    return False


def lossq_profile_has_policy_dates(profile):
    profile = profile or {}

    if profile.get("effective_date") and profile.get("expiration_date"):
        return True

    policies = profile.get("policies") or profile.get("policy_schedule") or []
    if isinstance(policies, list):
        for policy in policies:
            if not isinstance(policy, dict):
                continue
            if (
                policy.get("effective_date")
                or policy.get("policy_effective_date")
                or policy.get("Effective Date")
            ) and (
                policy.get("expiration_date")
                or policy.get("policy_expiration_date")
                or policy.get("Expiration Date")
            ):
                return True

    return False


def lossq_global_profile_cleanup(parsed_profile):
    parsed_profile = parsed_profile or {}

    # Clean impossible carrier values.
    for key in ["carrier_name", "writing_carrier", "carrier"]:
        if lossq_global_profile_bad_text(parsed_profile.get(key)):
            parsed_profile[key] = ""

    # Backfill carrier from writing carrier if one is real.
    if not parsed_profile.get("carrier_name") and not lossq_global_profile_bad_text(parsed_profile.get("writing_carrier")):
        parsed_profile["carrier_name"] = parsed_profile.get("writing_carrier")

    if not parsed_profile.get("writing_carrier") and not lossq_global_profile_bad_text(parsed_profile.get("carrier_name")):
        parsed_profile["writing_carrier"] = parsed_profile.get("carrier_name")

    policies = parsed_profile.get("policies") or parsed_profile.get("policy_schedule") or []
    cleaned_policies = []

    if isinstance(policies, list):
        for policy in policies:
            if not isinstance(policy, dict):
                continue

            item = dict(policy)

            for key in ["carrier", "carrier_name", "writing_carrier"]:
                if lossq_global_profile_bad_text(item.get(key)):
                    item[key] = ""

            if not item.get("carrier") and parsed_profile.get("carrier_name"):
                item["carrier"] = parsed_profile.get("carrier_name")

            if not item.get("carrier_name") and parsed_profile.get("carrier_name"):
                item["carrier_name"] = parsed_profile.get("carrier_name")

            if not item.get("writing_carrier") and parsed_profile.get("writing_carrier"):
                item["writing_carrier"] = parsed_profile.get("writing_carrier")

            cleaned_policies.append(item)

        parsed_profile["policies"] = cleaned_policies
        parsed_profile["policy_schedule"] = cleaned_policies

    # LOSSQ_GLOBAL_PROFILE_DATE_VALUE_CLEANUP_V1
    parsed_profile["effective_date"] = lossq_profile_date_or_blank(parsed_profile.get("effective_date"))
    parsed_profile["policy_effective_date"] = lossq_profile_date_or_blank(parsed_profile.get("policy_effective_date") or parsed_profile.get("effective_date"))
    parsed_profile["expiration_date"] = lossq_profile_date_or_blank(parsed_profile.get("expiration_date"))
    parsed_profile["policy_expiration_date"] = lossq_profile_date_or_blank(parsed_profile.get("policy_expiration_date") or parsed_profile.get("expiration_date"))

    # If the file has no policy dates, do not let a fallback "today" evaluation date make it appear current.
    if not lossq_profile_has_policy_dates(parsed_profile):
        parsed_profile["evaluation_date"] = ""
        parsed_profile["valuation_date"] = ""
        parsed_profile["loss_run_valuation_date"] = ""

    return parsed_profile


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
        # LOSSQ_SAFE_UPLOAD_FILENAME_IN_SAVE_LOOP_V1
        safe_upload_filename = await validate_upload_file_security(file)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        safe_filename = (safe_upload_filename or "loss_run.pdf").replace(" ", "_")
        file_path = os.path.join(UPLOAD_DIR, f"{timestamp}_{safe_filename}")

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        try:
            parsed_claims, parsed_profile = parse_file(file_path, safe_upload_filename or safe_filename)

            # LOSSQ_DIRECT_FILE_EXPOSURE_CAPTURE_V1
            direct_exposure_inputs = lossq_extract_exposure_inputs_directly_from_file(file_path)
            if direct_exposure_inputs:
                if not isinstance(parsed_profile, dict):
                    parsed_profile = {}
                parsed_profile.update({k: v for k, v in direct_exposure_inputs.items() if v not in ("", None, [], {})})
                parsed_profile["exposure_inputs"] = direct_exposure_inputs
                parsed_profile["exposures"] = direct_exposure_inputs
            parsed_profile = lossq_section_csv_apply_profile_date_repair(file_path, parsed_profile)
            parsed_profile = lossq_csv_label_pair_profile_repair(file_path, parsed_profile)
            parsed_profile = lossq_pdf_profile_repair(file_path, parsed_profile)
            parsed_profile = lossq_global_profile_cleanup(parsed_profile)
            parsed_profile = lossq_global_profile_cleanup(parsed_profile)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Loss run could not be parsed cleanly. Please upload a valid PDF, Excel, or CSV loss run.",
                    "error": str(exc)[:300],
                    "stage": "parse_file",
                },
            )

        # LOSSQ_APPLY_LIVE_SECTION_BASED_CSV_REPAIR_V1
        parsed_claims, parsed_profile = lossq_live_repair_section_csv_upload(
            file_path,
            parsed_claims,
            parsed_profile,
        )

        # LOSSQ_CLEAN_STANDARD_CSV_ROW_POLICY_OVERRIDE_V1
        parsed_claims, parsed_profile = lossq_clean_standard_csv_override(
            file_path,
            parsed_claims,
            parsed_profile,
        )

        # LOSSQ_UNIVERSAL_PRODUCING_AGENCY_EXTRACTION_V1
        upload_agency_name = lossq_header_agency_from_csv(file_path) or lossq_universal_agency_from_csv(file_path)
        if upload_agency_name:
            print("LOSSQ_AGENCY_SELECTED_FROM_UPLOAD:", upload_agency_name)

        # LOSSQ_CLEAN_PROFILE_POLICY_SCHEDULE_ROWS_V1
        parsed_profile = lossq_clean_profile_policy_schedule_rows(parsed_profile, parsed_claims)

        # LOSSQ_APPLY_LINE_OF_BUSINESS_FROM_POLICY_PREFIX_V1
        parsed_claims, parsed_profile = lossq_apply_line_of_business_from_policy_prefix(parsed_claims, parsed_profile)

        # LOSSQ_FINAL_PROFILE_DATES_FROM_POLICIES_V1
        parsed_profile = lossq_final_profile_dates_from_policies(parsed_profile)
        if upload_agency_name:
            parsed_profile = parsed_profile or {}
            parsed_profile["agency_name"] = upload_agency_name
            parsed_profile["producing_agency"] = upload_agency_name
            parsed_profile["producer"] = upload_agency_name

        file_policy_number = clean_input_policy
        file_account_key_for_claims = ""

        claim_policy_number = ""
        # LOSSQ_BETA_FILTER_AND_PURGE_BEFORE_SAVE_V1
        parsed_claims, lossq_beta_removed_rows = lossq_beta_filter_claim_rows(parsed_claims)


    # LOSSQ_UNIVERSAL_CLAIM_NUMBER_FILTER_V1
        if lossq_beta_removed_rows:
            print("LOSSQ_BETA_FILTER_REMOVED_ROWS:", lossq_beta_removed_rows[:10])

        lossq_beta_policy_keys = lossq_beta_collect_upload_policy_keys(
            parsed_profile,
            parsed_claims,
            file_policy_number,
        )
        lossq_beta_cleanup = lossq_beta_purge_prior_upload_data(
            db,
            current_user,
            lossq_beta_policy_keys,
        )

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

        # LOSSQ_CANONICAL_UPLOAD_CLAIM_PURGE_V1
        # Before saving this upload, remove stale rows tied to the same uploaded claim numbers
        # or policy numbers. This prevents old bad rows from surviving after parser repairs.
        upload_claim_numbers = []
        upload_policy_keys = []

        for purge_claim in parsed_claims or []:
            if not isinstance(purge_claim, dict):
                continue

            purge_claim_number = str(
                purge_claim.get("claim_number")
                or purge_claim.get("Claim Number")
                or purge_claim.get("claim_no")
                or purge_claim.get("Claim No")
                or ""
            ).strip().upper()

            purge_policy_number = str(
                purge_claim.get("policy_number")
                or purge_claim.get("Policy Number")
                or purge_claim.get("policy_no")
                or purge_claim.get("Policy No")
                or purge_claim.get("policy")
                or ""
            ).strip().upper()

            if purge_claim_number and purge_claim_number != "UNKNOWN":
                upload_claim_numbers.append(purge_claim_number)

            if purge_policy_number and not is_bad_policy_key_for_upload(purge_policy_number):
                upload_policy_keys.append(purge_policy_number)

        upload_claim_numbers = sorted(set(upload_claim_numbers))
        upload_policy_keys = sorted(set(upload_policy_keys))

        purged_by_claim_number = 0
        purged_by_policy_number = 0

        if upload_claim_numbers:
            purged_by_claim_number = (
                db.query(Claim)
                .filter(Claim.organization_id == current_user["organization_id"])
                .filter(func.upper(func.trim(Claim.claim_number)).in_(upload_claim_numbers))
                .delete(synchronize_session=False)
            )

        if upload_policy_keys:
            purged_by_policy_number = (
                db.query(Claim)
                .filter(Claim.organization_id == current_user["organization_id"])
                .filter(func.upper(func.trim(Claim.policy_number)).in_(upload_policy_keys))
                .delete(synchronize_session=False)
            )

        if purged_by_claim_number or purged_by_policy_number:
            db.flush()
            print(
                "LOSSQ_CANONICAL_UPLOAD_CLAIM_PURGE:",
                {
                    "claim_numbers": len(upload_claim_numbers),
                    "policy_keys": len(upload_policy_keys),
                    "deleted_by_claim_number": int(purged_by_claim_number or 0),
                    "deleted_by_policy_number": int(purged_by_policy_number or 0),
                },
            )

        file_saved = 0
        file_duplicates = 0

        # LOSSQ_CANONICAL_INSERT_ONLY_SAVE_LOOP_V1
        for claim_data in parsed_claims:
            normalized = normalize_claim_data(
                raw=claim_data,
                fallback_policy_number=file_policy_number,
                current_user=current_user,
            )

            normalized = lossq_preserve_row_policy_before_save(
                normalized=normalized,
                raw_claim=claim_data,
                fallback_policy_number=file_policy_number,
            )

            normalized = lossq_apply_row_values_at_final_save(
                normalized=normalized,
                raw_claim=claim_data,
            )

            claim_number = str(normalized.get("claim_number") or "").strip().upper()
            policy_value = str(normalized.get("policy_number") or file_policy_number or "").strip().upper()

            normalized["claim_number"] = claim_number
            normalized["policy_number"] = policy_value

            if not claim_number or claim_number == "UNKNOWN":
                print("LOSSQ_CANONICAL_SAVE_SKIPPED_NO_CLAIM_NUMBER:", claim_data)
                continue

            if not policy_value or is_bad_policy_key_for_upload(policy_value):
                print("LOSSQ_CANONICAL_SAVE_SKIPPED_BAD_POLICY:", {"claim_number": claim_number, "policy": policy_value})
                continue

            # Normalize fallback line fields so the frontend does not show all rows as one line.
            if not normalized.get("line_of_business") and normalized.get("claim_type"):
                normalized["line_of_business"] = normalized.get("claim_type")

            if not normalized.get("claim_type") and normalized.get("line_of_business"):
                normalized["claim_type"] = normalized.get("line_of_business")

            # Safe total fallback: if total is blank/zero but paid/reserve exist, use paid + reserve.
            try:
                paid_value = float(normalized.get("paid_amount") or 0)
            except Exception:
                paid_value = 0.0

            try:
                reserve_value = float(normalized.get("reserve_amount") or 0)
            except Exception:
                reserve_value = 0.0

            try:
                total_value = float(normalized.get("total_incurred") or 0)
            except Exception:
                total_value = 0.0

            if total_value <= 0 and (paid_value or reserve_value):
                normalized["total_incurred"] = paid_value + reserve_value

            clean_claim_payload = lossq_filter_claim_model_fields(normalized)

            db.add(Claim(**clean_claim_payload))
            file_saved += 1
            total_saved += 1

            print(
                "LOSSQ_CANONICAL_CLAIM_SAVED:",
                {
                    "claim_number": clean_claim_payload.get("claim_number"),
                    "policy_number": clean_claim_payload.get("policy_number"),
                    "line_of_business": clean_claim_payload.get("line_of_business"),
                    "status": clean_claim_payload.get("status"),
                    "paid": clean_claim_payload.get("paid_amount"),
                    "reserve": clean_claim_payload.get("reserve_amount"),
                    "total": clean_claim_payload.get("total_incurred"),
                },
            )

        upload_record = UploadHistory(
            filename=safe_upload_filename,
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
                "filename": safe_upload_filename,
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

    # LOSSQ_TABULAR_UPLOAD_POLICY_SCHEDULE_SAVE_V1
    claim_policy_schedule = build_policy_schedule_from_claims_for_upload(all_parsed_claims)
    existing_policy_schedule = profile_data.get("policies") if isinstance(profile_data.get("policies"), list) else []
    profile_data["policies"] = merge_policy_lists_for_upload(
        existing_policy_schedule,
        claim_policy_schedule,
    )

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
            print("LOSSQ_UPLOAD_ERROR_TRACE:", traceback.format_exc())
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

# LOSSQ_DEPLOY_TRIGGER_20260614152009
