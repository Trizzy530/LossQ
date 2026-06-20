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




# LOSSQ_BETA_UPLOAD_LIMIT_ENFORCEMENT_V1
def lossq_beta_upload_usage_guard(db: Session, current_user: dict, incoming_file_count: int = 1):
    org_id = None
    if isinstance(current_user, dict):
        org_id = current_user.get("organization_id")

    if not org_id:
        return

    try:
        org_row = db.execute(
            text(
                """
                SELECT plan, subscription_status, upload_limit
                FROM organizations
                WHERE id = :org_id
                """
            ),
            {"org_id": org_id},
        ).mappings().first()
    except Exception:
        return

    if not org_row:
        return

    plan = str(org_row.get("plan") or "").strip().lower()
    subscription_status = str(org_row.get("subscription_status") or "").strip().lower()

    is_beta = plan in {"beta", "beta_access", "early_access"} or subscription_status.startswith("beta")

    if not is_beta:
        return

    try:
        upload_limit = int(org_row.get("upload_limit") or 10)
    except Exception:
        upload_limit = 10

    if upload_limit <= 0:
        upload_limit = 10

    try:
        uploads_used = (
            db.query(UploadHistory)
            .filter(UploadHistory.organization_id == org_id)
            .count()
        )
    except Exception:
        uploads_used = 0

    incoming_file_count = max(int(incoming_file_count or 1), 1)
    projected_uploads = uploads_used + incoming_file_count

    if projected_uploads > upload_limit:
        remaining = max(upload_limit - uploads_used, 0)
        raise HTTPException(
            status_code=403,
            detail=(
                f"Beta upload limit reached. This beta account has used "
                f"{uploads_used} of {upload_limit} uploads. "
                f"{remaining} upload(s) remaining."
            ),
        )

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
        "exposure information": "exposures",
        "exposure / policy information": "policies",
        "exposure and policy information": "policies",
        "premium worksheet": "policies",
        "policy information": "policies",
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
            exposure_value_aliases = {"exposure value", "exposure amount", "value", "basis value"}
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
            exposure_value = _get_by_alias(row, exposure_value_aliases, None)
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
                "exposure_value": exposure_value,
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

    # LOSSQ_SECTION_CSV_EXPOSURE_POLICY_INFO_ROLLUP_V1
    # Universal rollup for CSV sections such as EXPOSURE / POLICY INFORMATION,
    # POLICY INFORMATION, PREMIUM WORKSHEET, or POLICY SCHEDULE.
    def _lossq_section_money(value):
        try:
            raw = str(value or "").replace("$", "").replace(",", "").strip()
            if raw in {"", "-", "None", "none", "null"}:
                return 0.0
            return float(raw)
        except Exception:
            return 0.0

    def _lossq_section_fmt_money(value):
        try:
            amount = float(value or 0)
        except Exception:
            amount = 0.0
        if amount <= 0:
            return ""
        if amount.is_integer():
            return str(int(amount))
        return f"{amount:.2f}"

    if policies:
        current_total = sum(_lossq_section_money(p.get("current_premium") or p.get("premium")) for p in policies)
        expiring_total = sum(_lossq_section_money(p.get("expiring_premium")) for p in policies)
        target_total = sum(_lossq_section_money(p.get("target_renewal_premium")) for p in policies)

        if current_total and not exposures.get("Current Premium"):
            exposures["Current Premium"] = _lossq_section_fmt_money(current_total)
        if expiring_total and not exposures.get("Expiring Premium"):
            exposures["Expiring Premium"] = _lossq_section_fmt_money(expiring_total)
        if target_total and not exposures.get("Target Renewal Premium"):
            exposures["Target Renewal Premium"] = _lossq_section_fmt_money(target_total)

        for policy in policies:
            basis = str(policy.get("exposure_basis") or "").strip()
            value = str(policy.get("exposure_value") or "").strip()
            basis_key = basis.lower()

            if not value:
                continue

            if "payroll" in basis_key and not exposures.get("Payroll"):
                exposures["Payroll"] = value
            elif ("revenue" in basis_key or "sales" in basis_key or "receipts" in basis_key) and not exposures.get("Revenue / Sales"):
                exposures["Revenue / Sales"] = value
            elif "employee" in basis_key and not exposures.get("Employee Count"):
                exposures["Employee Count"] = value
            elif "vehicle" in basis_key and not exposures.get("Vehicle Count"):
                exposures["Vehicle Count"] = value
            elif "driver" in basis_key and not exposures.get("Driver Count"):
                exposures["Driver Count"] = value
            elif ("tiv" in basis_key or "insured value" in basis_key or "property" in basis_key) and not exposures.get("Property TIV"):
                exposures["Property TIV"] = value

    # LOSSQ_SECTION_CSV_MISSING_EXPOSURE_FIELD_FALLBACK_V1
    # Final universal pass across raw CSV cells for count/property fields that may appear
    # outside the formal Field/Value exposure section or inside policy/exposure schedules.
    def _lossq_section_label_key(value):
        return re.sub(r"[^a-z0-9]", "", str(value or "").strip().lower())

    def _lossq_section_clean_exposure_value(value):
        raw = str(value or "").replace("$", "").replace(",", "").strip()
        if raw in {"", "-", "None", "none", "null"}:
            return ""
        return raw

    exposure_label_map = {
        "employeecount": "Employee Count",
        "employees": "Employee Count",
        "numberofemployees": "Employee Count",
        "fte": "Employee Count",
        "fulltimeemployees": "Employee Count",

        "vehiclecount": "Vehicle Count",
        "vehicles": "Vehicle Count",
        "numberofvehicles": "Vehicle Count",
        "powerunits": "Vehicle Count",

        "drivercount": "Driver Count",
        "drivers": "Driver Count",
        "numberofdrivers": "Driver Count",

        "propertytiv": "Property TIV",
        "tiv": "Property TIV",
        "totalinsuredvalue": "Property TIV",
        "totalinsurablevalue": "Property TIV",
        "propertyvalue": "Property TIV",
        "buildingvalue": "Building Value",
        "buildinglimit": "Building Value",
        "contentsvalue": "Contents Value",
        "bpp": "Contents Value",
        "businesspersonalproperty": "Contents Value",
    }

    for raw_row in rows:
        cells = [_lossq_live_clean_cell(cell) for cell in raw_row]
        for idx, cell in enumerate(cells):
            key = _lossq_section_label_key(cell)
            mapped_label = exposure_label_map.get(key)
            if not mapped_label:
                continue

            value = ""
            if idx + 1 < len(cells):
                value = _lossq_section_clean_exposure_value(cells[idx + 1])

            # Support rows like: Line, Policy, Carrier, Period, State, Premium, Exposure Basis, Exposure Value
            if not value and idx + 2 < len(cells):
                value = _lossq_section_clean_exposure_value(cells[idx + 2])

            if value and not exposures.get(mapped_label):
                exposures[mapped_label] = value

    # Also infer property/employee values from policy rows where exposure_basis/exposure_value were captured.
    for policy in policies:
        basis = str(policy.get("exposure_basis") or "").strip().lower()
        value = _lossq_section_clean_exposure_value(policy.get("exposure_value"))

        if not value:
            continue

        if ("employee" in basis or basis in {"fte", "staff", "headcount"}) and not exposures.get("Employee Count"):
            exposures["Employee Count"] = value
        elif ("vehicle" in basis or "power unit" in basis) and not exposures.get("Vehicle Count"):
            exposures["Vehicle Count"] = value
        elif "driver" in basis and not exposures.get("Driver Count"):
            exposures["Driver Count"] = value
        elif ("tiv" in basis or "insured value" in basis or "property value" in basis or basis == "property") and not exposures.get("Property TIV"):
            exposures["Property TIV"] = value
        elif "building" in basis and not exposures.get("Building Value"):
            exposures["Building Value"] = value
        elif ("contents" in basis or "bpp" in basis or "business personal property" in basis) and not exposures.get("Contents Value"):
            exposures["Contents Value"] = value

    # LOSSQ_SECTION_CSV_EXPOSURE_VALUE_SANITIZER_V1
    # Do not allow label/header words to be saved as exposure values.
    # Example bad shift: Employee Count = "Vehicle Count", Property TIV = "Current Premium".
    exposure_value_label_words = {
        "current premium",
        "expiring premium",
        "target renewal premium",
        "payroll",
        "revenue",
        "revenue / sales",
        "receipts",
        "employee count",
        "employees",
        "vehicle count",
        "vehicles",
        "driver count",
        "drivers",
        "property tiv",
        "tiv",
        "building value",
        "contents value",
        "exposure basis",
        "exposure value",
        "policy number",
        "line of business",
        "carrier",
        "state",
    }

    def _lossq_exposure_value_is_bad(value):
        raw = str(value or "").strip()
        key = re.sub(r"[^a-z0-9/ ]", "", raw.lower()).strip()
        compact = re.sub(r"[^a-z0-9]", "", raw.lower())

        if not raw:
            return True

        if key in exposure_value_label_words:
            return True

        if compact in {re.sub(r"[^a-z0-9]", "", item) for item in exposure_value_label_words}:
            return True

        # Count and money exposure values should contain at least one digit.
        if not re.search(r"\d", raw):
            return True

        return False

    for label in [
        "Employee Count",
        "Vehicle Count",
        "Driver Count",
        "Property TIV",
        "Building Value",
        "Contents Value",
        "Current Premium",
        "Expiring Premium",
        "Target Renewal Premium",
        "Payroll",
        "Revenue / Sales",
    ]:
        if _lossq_exposure_value_is_bad(exposures.get(label)):
            exposures.pop(label, None)

    # Refill from policy schedule rows where Exposure Basis and Exposure Value are correctly paired.
    for policy in policies:
        basis = str(policy.get("exposure_basis") or "").strip().lower()
        value = _lossq_section_clean_exposure_value(policy.get("exposure_value"))

        if _lossq_exposure_value_is_bad(value):
            continue

        if ("payroll" in basis) and not exposures.get("Payroll"):
            exposures["Payroll"] = value
        elif ("revenue" in basis or "sales" in basis or "receipt" in basis) and not exposures.get("Revenue / Sales"):
            exposures["Revenue / Sales"] = value
        elif ("employee" in basis or basis in {"fte", "staff", "headcount"}) and not exposures.get("Employee Count"):
            exposures["Employee Count"] = value
        elif ("vehicle" in basis or "power unit" in basis) and not exposures.get("Vehicle Count"):
            exposures["Vehicle Count"] = value
        elif "driver" in basis and not exposures.get("Driver Count"):
            exposures["Driver Count"] = value
        elif ("tiv" in basis or "insured value" in basis or "property value" in basis or basis == "property") and not exposures.get("Property TIV"):
            exposures["Property TIV"] = value
        elif "building" in basis and not exposures.get("Building Value"):
            exposures["Building Value"] = value
        elif ("contents" in basis or "bpp" in basis or "business personal property" in basis) and not exposures.get("Contents Value"):
            exposures["Contents Value"] = value

    if exposures:
        account["exposure_inputs"] = exposures
        account["exposures"] = exposures
        account["current_premium"] = exposures.get("Current Premium", "")
        account["expiring_premium"] = exposures.get("Expiring Premium", "")
        account["target_renewal_premium"] = exposures.get("Target Renewal Premium", "")
        account["payroll"] = exposures.get("Payroll", "")
        account["revenue"] = exposures.get("Revenue / Sales", "")
        account["sales"] = exposures.get("Revenue / Sales", "")
        account["receipts"] = exposures.get("Revenue / Sales", "")
        account["employee_count"] = exposures.get("Employee Count", "")
        account["vehicle_count"] = exposures.get("Vehicle Count", "")
        account["driver_count"] = exposures.get("Driver Count", "")
        account["property_tiv"] = exposures.get("Property TIV", "")
        account["building_value"] = exposures.get("Building Value", "")
        account["contents_value"] = exposures.get("Contents Value", "")

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

    # LOSSQ_DO_NOT_USE_POLICY_SCHEDULE_AS_ACCOUNT_KEY_V1
    # Policies identify coverage. They are not account/customer numbers.
    # Never use policy schedule rows to populate account_number.
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



# LOSSQ_CLAIMANT_FROM_UPLOAD_ROW_V1
def lossq_clean_claimant_value(value):
    clean = re.sub(r"\s+", " ", str(value or "").replace("\ufeff", "").strip())
    if not clean:
        return ""

    key = re.sub(r"[^a-z0-9]+", "", clean.lower())
    blocked = {
        "",
        "claimant",
        "claimantname",
        "name",
        "na",
        "n/a",
        "none",
        "null",
        "unknown",
        "unavailable",
        "claim",
        "claimnumber",
        "policynumber",
        "policy",
        "status",
        "description",
        "totalincurred",
        "paid",
        "reserve",
        "dateofloss",
        "datereported",
    }

    if key in blocked:
        return ""

    if re.fullmatch(r"[$,\d.\s]+", clean):
        return ""

    if re.fullmatch(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", clean):
        return ""

    return clean


def lossq_extract_claimant_from_raw_claim(raw_claim):
    if not isinstance(raw_claim, dict):
        return ""

    keys = [
        "claimant",
        "Claimant",
        "claimant_name",
        "Claimant Name",
        "claimantName",
        "injured_worker",
        "Injured Worker",
        "injured_party",
        "Injured Party",
        "injured_person",
        "Injured Person",
        "employee_name",
        "Employee Name",
        "worker_name",
        "Worker Name",
        "plaintiff",
        "Plaintiff",
        "party_name",
        "Party Name",
        "driver_name",
        "Driver Name",
        "customer_name",
        "Customer Name",
        "third_party_name",
        "Third Party Name",
    ]

    for key in keys:
        value = lossq_clean_claimant_value(raw_claim.get(key))
        if value:
            return value

    for key, value in raw_claim.items():
        key_clean = re.sub(r"[^a-z0-9]+", "", str(key or "").lower())
        if any(token in key_clean for token in [
            "claimant",
            "injuredworker",
            "injuredparty",
            "injuredperson",
            "employee",
            "plaintiff",
            "thirdparty",
        ]):
            cleaned = lossq_clean_claimant_value(value)
            if cleaned:
                return cleaned

    return ""


def lossq_apply_claimant_to_normalized_claim(normalized_claim, raw_claim):
    if not isinstance(normalized_claim, dict):
        return normalized_claim

    current = lossq_clean_claimant_value(normalized_claim.get("claimant"))
    if current:
        return normalized_claim

    claimant = lossq_extract_claimant_from_raw_claim(raw_claim)
    if claimant:
        normalized_claim["claimant"] = claimant
        normalized_claim["claimant_name"] = claimant
        print("LOSSQ_CLAIMANT_EXTRACTED_FROM_UPLOAD", {
            "claim_number": str(normalized_claim.get("claim_number") or raw_claim.get("claim_number") or raw_claim.get("Claim #") or "")[:80],
            "claimant": claimant[:120],
        })

    return normalized_claim


# LOSSQ_CLAIMANT_COLUMN_ENSURE_V1
def ensure_claimant_column(db):
    try:
        rows = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'claims'")).fetchall()
        existing = {str(row[0]).lower() for row in rows}
        if "claimant" not in existing:
            db.execute(text("ALTER TABLE claims ADD COLUMN claimant VARCHAR"))
            db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        try:
            db.execute(text("ALTER TABLE claims ADD COLUMN claimant VARCHAR"))
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass



# LOSSQ_CLAIM_DETAIL_COLUMNS_ENSURE_V1
def ensure_claim_detail_columns(db):
    columns = {
        "claimant": "VARCHAR",
        "jurisdiction_state": "VARCHAR",
        "adjuster": "VARCHAR",
        "examiner": "VARCHAR",
    }

    for column_name, column_type in columns.items():
        try:
            db.execute(text(f"ALTER TABLE claims ADD COLUMN IF NOT EXISTS {column_name} {column_type}"))
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass



# LOSSQ_FINAL_SAVE_CSV_FIELD_REPAIR_V3
def lossq_final_clean_v3(value):
    return re.sub(r"\s+", " ", str(value or "").replace("\ufeff", "").strip())


def lossq_final_key_v3(value):
    return re.sub(r"[^a-z0-9]+", "", lossq_final_clean_v3(value).lower())


def lossq_final_good_v3(value):
    raw = lossq_final_clean_v3(value)
    return bool(raw and raw.lower() not in {"-", "na", "n/a", "none", "null", "unknown"})


def lossq_final_account_like_v3(value):
    raw = lossq_final_clean_v3(value).upper()
    return bool("ACCT" in raw or "ACCOUNT" in raw or "CUSTOMER" in raw or "CLIENT" in raw or "CUST" in raw)


def lossq_final_policy_like_v3(value):
    raw = lossq_final_clean_v3(value).upper()
    if not raw or lossq_final_account_like_v3(raw):
        return False
    if not re.search(r"\d", raw):
        return False
    if re.search(r"\b(GL|BOP|WC|AUTO|CA|AL|LIQ|LIQUOR|PROP|CP|UMB|UM|IM|CARGO|GAR|DOL|CY|EPL|DO|PL)\b", raw):
        return True
    return bool("-" in raw and len(raw) >= 6)


def lossq_final_first_v3(source, *labels):
    if not isinstance(source, dict):
        return ""

    wanted = {lossq_final_key_v3(label) for label in labels}

    for key, value in source.items():
        if lossq_final_key_v3(key) in wanted:
            clean = lossq_final_clean_v3(value)
            if lossq_final_good_v3(clean):
                return clean

    return ""


def lossq_final_fix_claim_detail_v3(normalized_claim, raw_claim):
    if not isinstance(normalized_claim, dict):
        return normalized_claim

    claimant = (
        lossq_final_first_v3(normalized_claim, "claimant", "claimant name")
        or lossq_final_first_v3(raw_claim, "claimant", "claimant name", "injured worker", "injured party", "employee name", "plaintiff", "customer name", "third party name")
    )

    jurisdiction_state = (
        lossq_final_first_v3(normalized_claim, "jurisdiction_state", "jurisdiction/state", "jurisdiction", "state", "venue_state", "venue state", "loss state")
        or lossq_final_first_v3(raw_claim, "jurisdiction_state", "jurisdiction/state", "jurisdiction", "state", "venue_state", "venue state", "loss state")
    )

    adjuster = (
        lossq_final_first_v3(normalized_claim, "adjuster", "examiner", "adjuster/examiner", "claim adjuster", "claim examiner", "file handler")
        or lossq_final_first_v3(raw_claim, "adjuster", "examiner", "adjuster/examiner", "claim adjuster", "claim examiner", "file handler")
    )

    if claimant:
        normalized_claim["claimant"] = claimant

    if jurisdiction_state:
        normalized_claim["jurisdiction_state"] = jurisdiction_state
        normalized_claim["venue_state"] = normalized_claim.get("venue_state") or jurisdiction_state

    if adjuster:
        normalized_claim["adjuster"] = adjuster
        normalized_claim["examiner"] = normalized_claim.get("examiner") or adjuster

    # Remove frontend/API aliases that are not DB model columns.
    normalized_claim.pop("claimant_name", None)
    normalized_claim.pop("jurisdiction", None)
    normalized_claim.pop("state", None)
    normalized_claim.pop("adjuster_examiner", None)

    return normalized_claim


def lossq_final_repair_profile_account_and_exposures_v3(parsed_profile):
    if not isinstance(parsed_profile, dict):
        return parsed_profile

    account_number = (
        parsed_profile.get("account_number")
        or parsed_profile.get("customer_number")
        or parsed_profile.get("accountNumber")
        or parsed_profile.get("customerNumber")
    )

    if account_number and lossq_final_account_like_v3(account_number):
        parsed_profile["account_number"] = lossq_final_clean_v3(account_number)
        parsed_profile["customer_number"] = parsed_profile.get("customer_number") or parsed_profile["account_number"]

    # Never allow account number to become main policy.
    for field in ["policy_number", "main_policy"]:
        if parsed_profile.get(field) and lossq_final_account_like_v3(parsed_profile.get(field)):
            parsed_profile[field] = ""

    policies = parsed_profile.get("policies") if isinstance(parsed_profile.get("policies"), list) else []
    first_policy = ""
    for policy in policies:
        if isinstance(policy, dict):
            candidate = policy.get("policy_number") or policy.get("Policy Number")
            if lossq_final_policy_like_v3(candidate):
                first_policy = candidate
                break

    if first_policy:
        parsed_profile["policy_number"] = parsed_profile.get("policy_number") or first_policy
        parsed_profile["main_policy"] = parsed_profile.get("main_policy") or first_policy

    # Build exposure inputs from exposure rows / policies when direct fields are blank.
    exposure_rows = parsed_profile.get("exposures") if isinstance(parsed_profile.get("exposures"), list) else []
    if not exposure_rows:
        exposure_rows = [p for p in policies if isinstance(p, dict)]

    exposure_inputs = parsed_profile.get("exposure_inputs") if isinstance(parsed_profile.get("exposure_inputs"), dict) else {}
    if exposure_rows:
        exposure_inputs["exposure_rows"] = exposure_rows

        def nums(*keys):
            values = []
            for row in exposure_rows:
                if not isinstance(row, dict):
                    continue
                for key in keys:
                    value = row.get(key)
                    if value in ("", None):
                        continue
                    try:
                        values.append(float(str(value).replace("$", "").replace(",", "")))
                        break
                    except Exception:
                        pass
            return values

        sum_fields = [
            ("current_premium", ["current_premium", "Current Premium"]),
            ("expiring_premium", ["expiring_premium", "Expiring Premium"]),
            ("target_renewal_premium", ["target_renewal_premium", "Target Renewal Premium"]),
        ]

        max_fields = [
            ("payroll", ["payroll", "Payroll"]),
            ("revenue", ["revenue", "Revenue", "Sales", "Gross Sales"]),
            ("employee_count", ["employee_count", "Employee Count", "employees"]),
            ("vehicle_count", ["vehicle_count", "Vehicle Count", "vehicles"]),
            ("driver_count", ["driver_count", "Driver Count", "drivers"]),
            ("property_tiv", ["property_tiv", "Property TIV", "TIV"]),
        ]

        for target, keys in sum_fields:
            values = nums(*keys)
            if values:
                exposure_inputs[target] = sum(values)
                parsed_profile[target] = parsed_profile.get(target) or sum(values)

        for target, keys in max_fields:
            values = nums(*keys)
            if values:
                exposure_inputs[target] = max(values)
                parsed_profile[target] = parsed_profile.get(target) or max(values)

        parsed_profile["exposure_inputs"] = exposure_inputs
        parsed_profile["exposures"] = exposure_rows
        parsed_profile["exposure_inputs_used"] = True

    return parsed_profile




# LOSSQ_FINAL_CSV_ACCOUNT_AND_MISSING_CLAIMS_V4
def lossq_v4_clean(value):
    return re.sub(r"\s+", " ", str(value or "").replace("\ufeff", "").strip())


def lossq_v4_key(value):
    return re.sub(r"[^a-z0-9]+", "", lossq_v4_clean(value).lower())


def lossq_v4_good(value):
    raw = lossq_v4_clean(value)
    return bool(raw and raw.lower() not in {"-", "na", "n/a", "none", "null", "unknown"})


def lossq_v4_money(value):
    raw = lossq_v4_clean(value)
    if not raw:
        return ""
    cleaned = raw.replace("$", "").replace(",", "").replace("(", "-").replace(")", "")
    try:
        return float(cleaned)
    except Exception:
        return raw


def lossq_v4_bool(value):
    raw = lossq_v4_clean(value).lower()
    if raw in {"yes", "y", "true", "1", "litigated", "suit", "attorney"}:
        return True
    if raw in {"no", "n", "false", "0", "none", "-", "na", "n/a", ""}:
        return False
    return bool(raw)


def lossq_v4_account_like(value):
    raw = lossq_v4_clean(value).upper()
    return bool("ACCT" in raw or "ACCOUNT" in raw or "CUSTOMER" in raw or "CLIENT" in raw or "CUST" in raw)


def lossq_v4_policy_like(value):
    raw = lossq_v4_clean(value).upper()
    if not raw or lossq_v4_account_like(raw):
        return False
    if not re.search(r"\d", raw):
        return False
    if re.search(r"\b(GL|BOP|WC|AUTO|CA|AL|LIQ|LIQUOR|PROP|CP|UMB|UM|IM|CARGO|GAR|DOL|CY|EPL|DO|PL)\b", raw):
        return True
    return bool("-" in raw and len(raw) >= 6)


def lossq_v4_first(row_map, *labels):
    for label in labels:
        value = row_map.get(lossq_v4_key(label), "")
        if lossq_v4_good(value):
            return lossq_v4_clean(value)
    return ""


def lossq_v4_row_map(headers, row):
    mapped = {}
    for idx, header in enumerate(headers):
        header_key = lossq_v4_key(header)
        if header_key:
            mapped[header_key] = lossq_v4_clean(row[idx]) if idx < len(row) else ""
    return mapped


def lossq_v4_parse_csv_sections(file_path):
    import csv

    result = {
        "account_number": "",
        "customer_number": "",
        "exposure_rows": [],
        "claims": [],
    }

    if not str(file_path or "").lower().endswith(".csv"):
        return result

    try:
        with open(file_path, "r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            rows = list(csv.reader(handle))
    except Exception:
        return result

    # True account/customer number from label-value rows.
    account_keys = {
        "accountnumber",
        "accountno",
        "accountid",
        "customernumber",
        "customerno",
        "customerid",
        "clientnumber",
        "clientno",
        "clientid",
    }

    for row in rows[:200]:
        if len(row) < 2:
            continue

        label_key = lossq_v4_key(row[0])
        value = lossq_v4_clean(row[1])

        if label_key in account_keys and lossq_v4_good(value):
            result["account_number"] = value
            result["customer_number"] = value
            break

    def find_header(required_groups, section_words):
        section_seen = not section_words

        for idx, row in enumerate(rows):
            row_text = " ".join(lossq_v4_clean(cell).lower() for cell in row if lossq_v4_clean(cell))
            row_keys = {lossq_v4_key(cell) for cell in row if lossq_v4_clean(cell)}

            if section_words and any(word in row_text for word in section_words):
                section_seen = True
                continue

            if not section_seen:
                continue

            if all(any(option in row_keys for option in group) for group in required_groups):
                return idx, row

        return None, []

    # Exposure / policy table.
    exposure_idx, exposure_headers = find_header(
        [
            {"policynumber", "policyno", "policy"},
            {"lineofbusiness", "coverage", "policytype", "lob", "currentpremium", "exposurebasis"},
        ],
        ["exposure", "policy information", "policy schedule"],
    )

    if exposure_idx is not None:
        for row in rows[exposure_idx + 1:]:
            row_text = " ".join(lossq_v4_clean(cell).lower() for cell in row if lossq_v4_clean(cell))

            if not any(lossq_v4_clean(cell) for cell in row):
                break

            if any(stop in row_text for stop in ["claims detail", "claim detail", "loss summary", "underwriting notes"]):
                break

            row_map = lossq_v4_row_map(exposure_headers, row)
            policy_number = lossq_v4_first(row_map, "Policy Number", "Policy No", "Policy")
            line = lossq_v4_first(row_map, "Line of Business", "Coverage", "Policy Type", "LOB")

            if not lossq_v4_policy_like(policy_number) and not line:
                continue

            result["exposure_rows"].append({
                "policy_number": policy_number,
                "policy_type": line,
                "line_of_business": line,
                "carrier": lossq_v4_first(row_map, "Carrier", "Writing Carrier"),
                "effective_date": lossq_v4_first(row_map, "Effective Date", "Policy Effective Date"),
                "expiration_date": lossq_v4_first(row_map, "Expiration Date", "Policy Expiration Date"),
                "exposure_basis": lossq_v4_first(row_map, "Exposure Basis", "Basis"),
                "exposure_value": lossq_v4_first(row_map, "Exposure Value", "Exposure"),
                "payroll": lossq_v4_money(lossq_v4_first(row_map, "Payroll")),
                "revenue": lossq_v4_money(lossq_v4_first(row_map, "Revenue", "Sales", "Gross Sales")),
                "employee_count": lossq_v4_money(lossq_v4_first(row_map, "Employee Count", "Employees")),
                "vehicle_count": lossq_v4_money(lossq_v4_first(row_map, "Vehicle Count", "Vehicles", "Autos")),
                "driver_count": lossq_v4_money(lossq_v4_first(row_map, "Driver Count", "Drivers")),
                "property_tiv": lossq_v4_money(lossq_v4_first(row_map, "Property TIV", "TIV", "Total Insured Value")),
                "current_premium": lossq_v4_money(lossq_v4_first(row_map, "Current Premium")),
                "expiring_premium": lossq_v4_money(lossq_v4_first(row_map, "Expiring Premium")),
                "target_renewal_premium": lossq_v4_money(lossq_v4_first(row_map, "Target Renewal Premium")),
            })

    # Claims detail table. This is intentionally broad so LIQ, DOL, CYBER, IM, etc. are not dropped.
    claim_idx, claim_headers = find_header(
        [
            {"claimnumber", "claimno", "claim", "claimid"},
            {"policynumber", "policyno", "policy", "paid", "reserve", "totalincurred"},
        ],
        ["claims detail", "claim detail", "claims"],
    )

    if claim_idx is not None:
        for row in rows[claim_idx + 1:]:
            row_text = " ".join(lossq_v4_clean(cell).lower() for cell in row if lossq_v4_clean(cell))

            if not any(lossq_v4_clean(cell) for cell in row):
                break

            if any(stop in row_text for stop in ["underwriting notes", "loss summary", "exposure / policy", "account information"]):
                break

            row_map = lossq_v4_row_map(claim_headers, row)

            claim_number = lossq_v4_first(row_map, "Claim Number", "Claim #", "Claim No", "Claim ID", "Claim")
            policy_number = lossq_v4_first(row_map, "Policy Number", "Policy No", "Policy")

            if not lossq_v4_good(claim_number):
                continue

            if lossq_v4_key(claim_number) in {"claimnumber", "claimno", "claimid", "claim"}:
                continue

            result["claims"].append({
                "claim_number": claim_number,
                "policy_number": policy_number,
                "line_of_business": lossq_v4_first(row_map, "Line of Business", "Coverage", "Policy Type", "LOB"),
                "claim_type": lossq_v4_first(row_map, "Line of Business", "Coverage", "Policy Type", "LOB"),
                "claimant": lossq_v4_first(row_map, "Claimant", "Claimant Name", "Injured Worker", "Injured Party", "Employee Name", "Plaintiff", "Customer Name", "Third Party Name"),
                "jurisdiction_state": lossq_v4_first(row_map, "Jurisdiction/State", "Jurisdiction", "State", "Venue State", "Loss State"),
                "venue_state": lossq_v4_first(row_map, "Jurisdiction/State", "Jurisdiction", "State", "Venue State", "Loss State"),
                "adjuster": lossq_v4_first(row_map, "Adjuster", "Adjuster/Examiner", "Examiner", "Claim Adjuster", "Claim Examiner", "File Handler"),
                "examiner": lossq_v4_first(row_map, "Examiner", "Adjuster/Examiner", "Adjuster", "Claim Examiner", "File Handler"),
                "date_of_loss": lossq_v4_first(row_map, "Date of Loss", "Loss Date"),
                "date_reported": lossq_v4_first(row_map, "Date Reported", "Reported Date"),
                "date_closed": lossq_v4_first(row_map, "Date Closed", "Closed Date"),
                "status": lossq_v4_first(row_map, "Status", "Claim Status"),
                "cause_of_loss": lossq_v4_first(row_map, "Cause of Loss", "Loss Cause", "Cause"),
                "description": lossq_v4_first(row_map, "Description", "Loss Description", "Narrative"),
                "paid_amount": lossq_v4_money(lossq_v4_first(row_map, "Paid", "Paid Amount", "Total Paid")),
                "reserve_amount": lossq_v4_money(lossq_v4_first(row_map, "Reserve", "Reserve Amount", "Outstanding Reserve")),
                "total_incurred": lossq_v4_money(lossq_v4_first(row_map, "Total Incurred", "Incurred", "Gross Incurred", "Net Incurred")),
                "litigation": lossq_v4_bool(lossq_v4_first(row_map, "Litigation", "Litigated")),
                "attorney_assigned": lossq_v4_bool(lossq_v4_first(row_map, "Attorney Assigned", "Attorney", "Counsel")),
            })

    return result


def lossq_v4_merge_csv_sections_before_save(file_path, parsed_claims, parsed_profile):
    parsed_claims = parsed_claims if isinstance(parsed_claims, list) else []
    parsed_profile = parsed_profile if isinstance(parsed_profile, dict) else {}

    context = lossq_v4_parse_csv_sections(file_path)

    account_number = lossq_v4_clean(context.get("account_number"))
    if account_number:
        parsed_profile["account_number"] = account_number
        parsed_profile["customer_number"] = parsed_profile.get("customer_number") or account_number

    exposure_rows = context.get("exposure_rows") or []
    if exposure_rows:
        parsed_profile["exposures"] = exposure_rows

        exposure_inputs = parsed_profile.get("exposure_inputs") if isinstance(parsed_profile.get("exposure_inputs"), dict) else {}
        exposure_inputs["exposure_rows"] = exposure_rows

        def numbers(field):
            values = []
            for row in exposure_rows:
                try:
                    value = row.get(field)
                    if value not in ("", None):
                        values.append(float(value))
                except Exception:
                    pass
            return values

        for field in ["current_premium", "expiring_premium", "target_renewal_premium"]:
            values = numbers(field)
            if values:
                parsed_profile[field] = sum(values)
                exposure_inputs[field] = sum(values)

        for field in ["payroll", "revenue", "employee_count", "vehicle_count", "driver_count", "property_tiv"]:
            values = numbers(field)
            if values:
                parsed_profile[field] = max(values)
                exposure_inputs[field] = max(values)

        parsed_profile["exposure_inputs"] = exposure_inputs
        parsed_profile["exposure_inputs_used"] = True

    merged = []
    by_key = {}

    def claim_merge_key(claim):
        claim_number = lossq_v4_clean(claim.get("claim_number") or claim.get("Claim Number")).upper()
        policy_number = lossq_v4_clean(claim.get("policy_number") or claim.get("Policy Number")).upper()
        return f"{claim_number}|{policy_number}"

    for claim in parsed_claims:
        if not isinstance(claim, dict):
            continue

        copy_claim = dict(claim)
        merged.append(copy_claim)
        by_key[claim_merge_key(copy_claim)] = copy_claim

    overlay_fields = [
        "policy_number",
        "line_of_business",
        "claim_type",
        "claimant",
        "jurisdiction_state",
        "venue_state",
        "adjuster",
        "examiner",
        "date_of_loss",
        "date_reported",
        "date_closed",
        "status",
        "cause_of_loss",
        "description",
        "paid_amount",
        "reserve_amount",
        "total_incurred",
        "litigation",
        "attorney_assigned",
    ]

    added_claims = 0
    updated_claims = 0

    for csv_claim in context.get("claims") or []:
        mk = claim_merge_key(csv_claim)

        if mk in by_key:
            target = by_key[mk]
            for field in overlay_fields:
                value = csv_claim.get(field)
                if value not in ("", None):
                    if field in {"claimant", "jurisdiction_state", "venue_state", "adjuster", "examiner"} or not target.get(field):
                        target[field] = value
            updated_claims += 1
        else:
            merged.append(dict(csv_claim))
            by_key[mk] = merged[-1]
            added_claims += 1

    parsed_claims = merged

    # Rebuild policy schedule from exposures and all claims.
    claim_counts = {}
    claim_totals = {}
    claim_lines = {}

    for claim in parsed_claims:
        policy_number = lossq_v4_clean(claim.get("policy_number")).upper()
        if not lossq_v4_policy_like(policy_number):
            continue

        claim_counts[policy_number] = claim_counts.get(policy_number, 0) + 1

        try:
            claim_totals[policy_number] = claim_totals.get(policy_number, 0.0) + float(claim.get("total_incurred") or 0)
        except Exception:
            pass

        line = lossq_v4_clean(claim.get("line_of_business") or claim.get("claim_type"))
        if line:
            claim_lines[policy_number] = line

    policies_by_number = {}

    for exposure in exposure_rows:
        policy_number = lossq_v4_clean(exposure.get("policy_number")).upper()
        if not lossq_v4_policy_like(policy_number):
            continue

        policies_by_number[policy_number] = {
            "policy_number": exposure.get("policy_number"),
            "policy_type": exposure.get("policy_type") or exposure.get("line_of_business") or claim_lines.get(policy_number),
            "line_of_business": exposure.get("line_of_business") or exposure.get("policy_type") or claim_lines.get(policy_number),
            "carrier": exposure.get("carrier") or parsed_profile.get("carrier_name") or parsed_profile.get("writing_carrier"),
            "effective_date": exposure.get("effective_date") or parsed_profile.get("effective_date"),
            "expiration_date": exposure.get("expiration_date") or parsed_profile.get("expiration_date"),
            "claim_count": claim_counts.get(policy_number, 0),
            "total_incurred": claim_totals.get(policy_number, 0),
            "current_premium": exposure.get("current_premium"),
            "expiring_premium": exposure.get("expiring_premium"),
            "target_renewal_premium": exposure.get("target_renewal_premium"),
        }

    for policy_number, count in claim_counts.items():
        if policy_number not in policies_by_number:
            policies_by_number[policy_number] = {
                "policy_number": policy_number,
                "policy_type": claim_lines.get(policy_number, ""),
                "line_of_business": claim_lines.get(policy_number, ""),
                "carrier": parsed_profile.get("carrier_name") or parsed_profile.get("writing_carrier"),
                "effective_date": parsed_profile.get("effective_date"),
                "expiration_date": parsed_profile.get("expiration_date"),
                "claim_count": count,
                "total_incurred": claim_totals.get(policy_number, 0),
            }

    if policies_by_number:
        parsed_profile["policies"] = list(policies_by_number.values())
        parsed_profile["policy_schedule"] = parsed_profile["policies"]

        current_policy = parsed_profile.get("policy_number") or parsed_profile.get("main_policy")
        if not lossq_v4_policy_like(current_policy):
            first_policy = parsed_profile["policies"][0].get("policy_number")
            parsed_profile["policy_number"] = first_policy
            parsed_profile["main_policy"] = first_policy

    print("LOSSQ_FINAL_CSV_ACCOUNT_AND_MISSING_CLAIMS_V4", {
        "account_number": str(parsed_profile.get("account_number") or "")[:80],
        "csv_claims": len(context.get("claims") or []),
        "added_claims": added_claims,
        "updated_claims": updated_claims,
        "final_claims": len(parsed_claims),
        "exposure_rows": len(exposure_rows),
    })

    return parsed_claims, parsed_profile




# LOSSQ_TRUE_ACCOUNT_NUMBER_FROM_UPLOAD_CSV_V1
def lossq_true_account_number_value(value):
    raw = re.sub(r"\s+", " ", str(value or "").replace("\ufeff", "").strip())
    if not raw:
        return ""

    compact = re.sub(r"[^A-Z0-9]+", "", raw.upper())

    true_account_signal = any(token in compact for token in [
        "ACCT",
        "ACCOUNT",
        "CUSTOMER",
        "CLIENT",
        "CUST",
    ])

    if true_account_signal:
        return raw

    return ""


def lossq_extract_true_account_number_from_upload_csv(file_path):
    import csv

    if not str(file_path or "").lower().endswith(".csv"):
        return ""

    try:
        with open(file_path, "r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            rows = list(csv.reader(handle))
    except Exception:
        return ""

    def key(value):
        return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())

    account_labels = {
        "accountnumber",
        "accountno",
        "accountid",
        "customernumber",
        "customerno",
        "customerid",
        "clientnumber",
        "clientno",
        "clientid",
    }

    for row in rows[:200]:
        if len(row) < 2:
            continue

        if key(row[0]) in account_labels:
            account_number = lossq_true_account_number_value(row[1])
            if account_number:
                return account_number

    return ""



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



# LOSSQ_CLEAN_EXPOSURE_LIMITS_FIELD_V1
def lossq_clean_exposure_limits_field(profile_data: dict):
    """
    Keep exposure_basis separate from policy limits.
    If limits contains a full exposure sentence, replace it with coverage_limit when available.
    """
    profile_data = dict(profile_data or {})

    raw_limits = str(profile_data.get("limits") or "").strip()
    lower_limits = raw_limits.lower()

    looks_like_exposure_basis = any(token in lower_limits for token in [
        "payroll",
        "revenue",
        "employees",
        "vehicles",
        "drivers",
        "umbrella",
        "gl limit",
        "exposure basis",
    ])

    if looks_like_exposure_basis:
        coverage_limit = profile_data.get("coverage_limit") or profile_data.get("policy_limit") or ""
        profile_data["limits"] = coverage_limit or ""

    return profile_data


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

    # LOSSQ_UPSERT_ACCOUNT_PROFILE_EXPOSURE_FIELDS_V1
    # Ensure captured CSV/PDF/XLSX exposure inputs are saved on newly-created profiles.
    for exposure_field in [
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
        exposure_value = profile_data.get(exposure_field)
        if exposure_value not in ("", None, [], {}) and hasattr(new_profile, exposure_field):
            setattr(new_profile, exposure_field, exposure_value)

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




# LOSSQ_UNIVERSAL_PROFILE_IDENTITY_POLICY_CLEANUP_V1
def lossq_universal_profile_identity_policy_cleanup(profile):
    """
    Universal cleanup for section-style, carrier-style, CSV, XLSX, and PDF profiles.
    Does not hardcode any customer, carrier, file, or demo case.
    """
    if not isinstance(profile, dict):
        return profile

    profile = dict(profile)

    def clean(value):
        return re.sub(r"\s+", " ", str(value or "").strip())

    def norm_key(value):
        return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")

    def first_value(*keys):
        normalized = {norm_key(k): v for k, v in profile.items()}
        for key in keys:
            value = profile.get(key)
            if clean(value):
                return clean(value)

            value = normalized.get(norm_key(key))
            if clean(value):
                return clean(value)

        return ""

    def looks_like_policy(value):
        value = clean(value).upper()
        if not value:
            return False
        # LOSSQ_TRUE_ACCOUNT_NUMBER_FROM_UPLOAD_CSV_V1
        if lossq_true_account_number_value(value):
            return False
        return lossq_looks_like_policy_but_not_account(value)

    def split_policy_values(value):
        value = clean(value)
        if not value:
            return []

        pieces = re.split(r"\s*(?:/|,|;|\||\band\b|\+)\s*", value, flags=re.IGNORECASE)
        results = []

        for piece in pieces:
            piece = clean(piece)
            if not piece:
                continue

            matches = re.findall(r"\b[A-Z]{1,8}[- ]?\d{2,6}[- ]?[A-Z0-9]{2,12}\b", piece.upper())

            if matches:
                for match in matches:
                    match = clean(match).replace(" ", "-")
                    if match and match not in results:
                        results.append(match)
            elif looks_like_policy(piece):
                piece = piece.upper().replace(" ", "-")
                if piece not in results:
                    results.append(piece)

        return results

    # 1) Business name / insured name universal mapping.
    business_name = first_value(
        "business_name",
        "insured_name",
        "insured",
        "named_insured",
        "named insured",
        "applicant",
        "account_name",
        "account name",
        "company_name",
        "company",
    )

    if business_name:
        profile["business_name"] = business_name
        profile["insured_name"] = profile.get("insured_name") or business_name
        profile["named_insured"] = profile.get("named_insured") or business_name

    # 2) Policy values may appear in policy_number, account_number, main_policy, or raw headings.
    raw_policy_value = first_value(
        "policy_number",
        "policy number",
        "policy_numbers",
        "policy numbers",
        "main_policy",
        "main policy",
        "account_number",
        "account number",
    )

    policies = split_policy_values(raw_policy_value)

    existing_policies = profile.get("policies")
    if isinstance(existing_policies, list):
        for item in existing_policies:
            if isinstance(item, dict):
                policies.extend(split_policy_values(item.get("policy_number") or item.get("policy") or item.get("number")))
            else:
                policies.extend(split_policy_values(item))

    # De-dupe while preserving order.
    deduped_policies = []
    for policy in policies:
        policy = clean(policy).upper()
        if policy and policy not in deduped_policies:
            deduped_policies.append(policy)

    if deduped_policies:
        profile["policy_number"] = deduped_policies[0]
        profile["main_policy"] = deduped_policies[0]
        profile["policy_numbers"] = deduped_policies

        existing_policy_rows = profile.get("policies") if isinstance(profile.get("policies"), list) else []
        rebuilt = []

        seen = set()
        for policy in deduped_policies:
            rebuilt.append({"policy_number": policy})
            seen.add(policy)

        for item in existing_policy_rows:
            if isinstance(item, dict):
                policy = clean(item.get("policy_number") or item.get("policy") or item.get("number")).upper()
                if policy and policy not in seen:
                    rebuilt.append(item)
                    seen.add(policy)

        profile["policies"] = rebuilt

    # 3) Account number should not be a policy-number bundle.
    account_number = first_value("account_number", "account number", "customer_number", "customer number")
    true_account_number = first_value(
        "account_id",
        "account id",
        "customer_id",
        "customer id",
        "insured_id",
        "insured id",
        "client_id",
        "client id",
    )

    if account_number and looks_like_policy(account_number):
        if true_account_number and not looks_like_policy(true_account_number):
            profile["account_number"] = true_account_number
        else:
            profile["account_number"] = ""

    return profile




# LOSSQ_UNIVERSAL_SECTION_CSV_CLAIMS_PROFILE_REPAIR_V1
def lossq_universal_section_csv_claims_profile_repair(file_path, parsed_claims=None, parsed_profile=None):
    """
    Universal section-based CSV parser for loss runs that contain profile sections,
    claims sections, and summary sections in one file.

    Supports generic layouts such as:
    - EXPOSURE / POLICY INFORMATION
    - POLICY INFORMATION
    - ACCOUNT INFORMATION
    - CLAIMS DETAIL
    - CLAIM DETAIL
    - CLAIMS
    - LOSS SUMMARY

    No customer, carrier, or demo-file hardcoding.
    """
    parsed_claims = parsed_claims if isinstance(parsed_claims, list) else []
    parsed_profile = parsed_profile if isinstance(parsed_profile, dict) else {}

    # LOSSQ_PROFILE_AGENCY_FIELD_NORMALIZE_V1
    # Normalize any file-parsed producer/agency value into agency_name so the
    # account profile save and dashboard display use the uploaded file as source.
    def _lossq_profile_agency_clean(value):
        return re.sub(r"\s+", " ", str(value or "").replace("\ufeff", "").strip())

    profile_agency_value = _lossq_profile_agency_clean(
        parsed_profile.get("agency_name")
        or parsed_profile.get("producing_agency")
        or parsed_profile.get("producingAgency")
        or parsed_profile.get("producer")
        or parsed_profile.get("producer_name")
        or parsed_profile.get("agency")
        or parsed_profile.get("agencyName")
        or parsed_profile.get("broker")
        or parsed_profile.get("brokerage")
        or parsed_profile.get("agent")
        or parsed_profile.get("agent_name")
        or parsed_profile.get("prepared_by")
        or parsed_profile.get("contact_name")
    )

    if profile_agency_value:
        parsed_profile["agency_name"] = profile_agency_value
        parsed_profile["producing_agency"] = profile_agency_value


    if not str(file_path or "").lower().endswith(".csv"):
        return parsed_claims, parsed_profile

    try:
        with open(file_path, "r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            rows = list(csv.reader(handle))
    except Exception:
        return parsed_claims, parsed_profile

    if not rows:
        return parsed_claims, parsed_profile

    def clean(value):
        return re.sub(r"\s+", " ", str(value or "").replace("\ufeff", "").strip())

    def norm(value):
        return re.sub(r"[^a-z0-9]+", "_", clean(value).lower()).strip("_")

    def money(value):
        raw = clean(value)
        if not raw:
            return 0.0
        neg = raw.startswith("(") and raw.endswith(")")
        raw = raw.replace("$", "").replace(",", "").replace("(", "").replace(")", "")
        raw = re.sub(r"[^0-9.\-]", "", raw)
        if raw in {"", "-", ".", "-."}:
            return 0.0
        try:
            amount = float(raw)
            return -amount if neg else amount
        except Exception:
            return 0.0

    def looks_like_policy(value):
        value = clean(value).upper()
        if not value:
            return False
        return lossq_looks_like_policy_but_not_account(value)

    def split_policies(value):
        value = clean(value)
        if not value:
            return []

        pieces = re.split(r"\s*(?:/|,|;|\||\band\b|\+)\s*", value, flags=re.IGNORECASE)
        found = []

        for piece in pieces:
            piece = clean(piece).upper()
            matches = re.findall(r"\b[A-Z]{1,8}[- ]?\d{2,6}[- ]?[A-Z0-9]{2,12}\b", piece)
            for match in matches:
                match = clean(match).upper().replace(" ", "-")
                if match and match not in found:
                    found.append(match)

        return found

    def infer_line_from_policy(policy_number, fallback=""):
        value = clean(policy_number).upper()
        fallback = clean(fallback)

        if value.startswith("WC"):
            return "Workers Compensation"
        if value.startswith(("GL", "CGL")):
            return "General Liability"
        if value.startswith(("PL", "PROD")):
            return "Products Liability"
        if value.startswith(("AL", "AUTO", "CA")):
            return "Commercial Auto"
        if value.startswith(("BOP", "CP", "PROP")):
            return "Property / BOP"
        if value.startswith(("UMB", "UM")):
            return "Umbrella"
        if value.startswith(("CY", "CYBER")):
            return "Cyber Liability"

        return fallback or "Unknown"

    def header_index(headers, candidates):
        normalized = [norm(header) for header in headers]
        wanted = {norm(candidate) for candidate in candidates}

        for index, header in enumerate(normalized):
            if header in wanted:
                return index

        for index, header in enumerate(normalized):
            for candidate in wanted:
                if candidate and candidate in header:
                    return index

        return None

    def value_at(row, index):
        if index is None:
            return ""
        if index < 0 or index >= len(row):
            return ""
        return clean(row[index])

    profile_labels = {}

    claims_header_index = None

    for index, row in enumerate(rows):
        first = norm(row[0] if row else "")

        if first in {
            "claims_detail",
            "claim_detail",
            "claim_details",
            "claims",
            "loss_detail",
            "loss_details",
            "claim_listing",
            "claim_list",
        }:
            claims_header_index = index + 1
            break

        if len(row) >= 2:
            label = norm(row[0])
            value = clean(row[1])
            if label and value:
                profile_labels[label] = value

    if profile_labels:
        label_map = {
            "insured_name": ["insured_name", "named_insured", "insured", "applicant", "account_name", "company_name", "company"],
            "policy_number": ["policy_number", "policy_numbers", "policy_no", "policy"],
            "policy_period": ["policy_period", "policy_term", "effective_expiration", "coverage_period"],
            "line_of_business": ["line_of_business", "lines_of_business", "coverage", "coverage_line"],
            "carrier": ["carrier", "insurance_carrier", "writing_carrier", "company"],
            "annual_revenue": ["annual_revenue", "revenue", "sales", "gross_sales"],
            "payroll": ["total_payroll_annual", "payroll", "annual_payroll"],
            "employee_count": ["full_time_employees", "employees", "employee_count"],
            "operations": ["operations", "business_operations", "description_of_operations"],
            "account_number": ["account_number", "account_no", "customer_number", "client_number"],
            "evaluation_date": ["evaluation_date", "valuation_date", "as_of_date", "loss_run_date"],
        }

        def first_label(keys):
            for key in keys:
                if key in profile_labels and clean(profile_labels[key]):
                    return clean(profile_labels[key])
            return ""

        insured_name = first_label(label_map["insured_name"])
        if insured_name:
            parsed_profile["business_name"] = insured_name
            parsed_profile["insured_name"] = insured_name
            parsed_profile["named_insured"] = insured_name

        carrier = first_label(label_map["carrier"])
        if carrier:
            parsed_profile["carrier"] = carrier
            parsed_profile["carrier_name"] = carrier
            parsed_profile["writing_carrier"] = carrier

        policy_value = first_label(label_map["policy_number"])
        policy_numbers = split_policies(policy_value)

        line_value = first_label(label_map["line_of_business"])
        line_parts = [
            clean(part)
            for part in re.split(r"\s*(?:/|,|;|\||\band\b|\+)\s*", line_value, flags=re.IGNORECASE)
            if clean(part)
        ]

        if policy_numbers:
            parsed_profile["policy_number"] = policy_numbers[0]
            parsed_profile["main_policy"] = policy_numbers[0]
            parsed_profile["policy_numbers"] = policy_numbers
            parsed_profile["policies"] = [
                {
                    "policy_number": policy_number,
                    "line_of_business": infer_line_from_policy(
                        policy_number,
                        line_parts[min(i, len(line_parts) - 1)] if line_parts else "",
                    ),
                    "carrier": carrier or parsed_profile.get("carrier") or "",
                }
                for i, policy_number in enumerate(policy_numbers)
            ]

        policy_period = first_label(label_map["policy_period"])
        dates = re.findall(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", policy_period)

        if len(dates) >= 1:
            parsed_profile["effective_date"] = parsed_profile.get("effective_date") or dates[0]
        if len(dates) >= 2:
            parsed_profile["expiration_date"] = parsed_profile.get("expiration_date") or dates[1]

        account_number = first_label(label_map["account_number"])
        if account_number and not looks_like_policy(account_number):
            parsed_profile["account_number"] = account_number
        elif looks_like_policy(parsed_profile.get("account_number", "")):
            parsed_profile["account_number"] = ""

        for target, keys in [
            ("annual_revenue", label_map["annual_revenue"]),
            ("payroll", label_map["payroll"]),
            ("employee_count", label_map["employee_count"]),
            ("operations", label_map["operations"]),
            ("evaluation_date", label_map["evaluation_date"]),
        ]:
            value = first_label(keys)
            if value:
                parsed_profile[target] = value

    repaired_claims = []

    if claims_header_index is not None and claims_header_index < len(rows):
        headers = [clean(value) for value in rows[claims_header_index]]

        claim_number_i = header_index(headers, ["claim #", "claim no", "claim number", "claim_number", "claim"])
        dol_i = header_index(headers, ["date of loss", "loss date", "date_of_loss"])
        reported_i = header_index(headers, ["date reported", "reported date", "date_reported"])
        claimant_i = header_index(headers, ["claimant", "claimant name", "injured worker", "party"])
        line_i = header_index(headers, ["line", "line of business", "coverage", "lob"])
        desc_i = header_index(headers, ["description", "loss description", "cause", "claim description"])
        status_i = header_index(headers, ["status", "claim status", "open closed"])
        incurred_i = header_index(headers, ["total incurred", "incurred", "total"])
        paid_i = header_index(headers, ["paid", "total paid"])
        reserve_i = header_index(headers, ["reserve", "total reserve", "outstanding reserve"])
        subro_i = header_index(headers, ["subrogation", "subro"])

        for row in rows[claims_header_index + 1:]:
            first = norm(row[0] if row else "")

            if first in {
                "loss_summary",
                "summary",
                "totals",
                "exposure_summary",
                "premium_summary",
                "policy_year",
            }:
                break

            if not any(clean(cell) for cell in row):
                continue

            claim_number = value_at(row, claim_number_i)
            if not claim_number:
                continue

            line = value_at(row, line_i)
            status = value_at(row, status_i)
            paid = money(value_at(row, paid_i))
            reserve = money(value_at(row, reserve_i))
            incurred = money(value_at(row, incurred_i))

            if incurred <= 0 and (paid or reserve):
                incurred = paid + reserve

            claim = {
                "claim_number": claim_number,
                "date_of_loss": value_at(row, dol_i),
                "date_reported": value_at(row, reported_i),
                "claimant": value_at(row, claimant_i),
                "line_of_business": line,
                "description": value_at(row, desc_i),
                "claim_status": status,
                "status": status,
                "total_incurred": incurred,
                "paid": paid,
                "reserve": reserve,
                "subrogation": value_at(row, subro_i),
            }

            policy_numbers = parsed_profile.get("policy_numbers") if isinstance(parsed_profile.get("policy_numbers"), list) else []
            line_upper = line.upper()

            if policy_numbers:
                if "WC" in line_upper:
                    claim["policy_number"] = next((p for p in policy_numbers if str(p).upper().startswith("WC")), policy_numbers[0])
                elif "GL" in line_upper or "LIAB" in line_upper:
                    claim["policy_number"] = next((p for p in policy_numbers if str(p).upper().startswith(("GL", "CGL", "PL"))), policy_numbers[0])
                else:
                    claim["policy_number"] = policy_numbers[0]

            repaired_claims.append(claim)

    if repaired_claims and len(repaired_claims) >= len(parsed_claims):
        parsed_claims = repaired_claims

    if parsed_profile.get("policy_numbers") and not parsed_profile.get("account_number"):
        parsed_profile["account_number"] = ""

    return parsed_claims, parsed_profile




# LOSSQ_UNIVERSAL_SECTION_CSV_CLAIMS_PROFILE_REPAIR_V2
def lossq_universal_section_csv_claims_profile_repair_v2(file_path, parsed_claims=None, parsed_profile=None):
    """
    Universal section-based CSV loss run repair.

    Handles CSV files that include sections such as:
    - EXPOSURE / POLICY INFORMATION
    - ACCOUNT INFORMATION
    - POLICY INFORMATION
    - CLAIMS DETAIL
    - LOSS SUMMARY

    This does not hardcode carrier, insured, file name, or demo data.
    """
    parsed_claims = parsed_claims if isinstance(parsed_claims, list) else []
    parsed_profile = parsed_profile if isinstance(parsed_profile, dict) else {}

    if not str(file_path or "").lower().endswith(".csv"):
        return parsed_claims, parsed_profile

    try:
        with open(file_path, "r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            rows = list(csv.reader(handle))
    except Exception:
        return parsed_claims, parsed_profile

    if not rows:
        return parsed_claims, parsed_profile

    def clean(value):
        return re.sub(r"\s+", " ", str(value or "").replace("\ufeff", "").strip())

    def norm(value):
        return re.sub(r"[^a-z0-9]+", "_", clean(value).lower()).strip("_")

    def money(value):
        raw = clean(value)
        if not raw:
            return 0.0

        neg = raw.startswith("(") and raw.endswith(")")
        raw = raw.replace("$", "").replace(",", "").replace("(", "").replace(")", "")
        raw = re.sub(r"[^0-9.\-]", "", raw)

        if raw in {"", "-", ".", "-."}:
            return 0.0

        try:
            amount = float(raw)
            return -amount if neg else amount
        except Exception:
            return 0.0

    def header_index(headers, candidates):
        normalized_headers = [norm(header) for header in headers]
        normalized_candidates = [norm(candidate) for candidate in candidates]

        for i, header in enumerate(normalized_headers):
            if header in normalized_candidates:
                return i

        for i, header in enumerate(normalized_headers):
            for candidate in normalized_candidates:
                if candidate and (candidate in header or header in candidate):
                    return i

        return None

    def value_at(row, index):
        if index is None:
            return ""
        if index < 0 or index >= len(row):
            return ""
        return clean(row[index])

    def looks_like_policy(value):
        value = clean(value).upper()
        if not value:
            return False
        return lossq_looks_like_policy_but_not_account(value)

    def split_policy_numbers(value):
        raw = clean(value)
        if not raw:
            return []

        found = []
        pieces = re.split(r"\s*(?:/|,|;|\||\band\b|\+)\s*", raw, flags=re.IGNORECASE)

        for piece in pieces:
            piece = clean(piece).upper()
            matches = re.findall(r"\b[A-Z]{1,8}[- ]?\d{2,6}[- ]?[A-Z0-9]{2,12}\b", piece)

            for match in matches:
                match = clean(match).upper().replace(" ", "-")
                if match and match not in found:
                    found.append(match)

        return found

    def infer_policy_line(policy_number, fallback_line=""):
        policy = clean(policy_number).upper()
        fallback = clean(fallback_line)

        if policy.startswith("WC"):
            return "Workers Compensation"
        if policy.startswith(("GL", "CGL")):
            return "General Liability"
        if policy.startswith(("PL", "PROD")):
            return "Products Liability"
        if policy.startswith(("AL", "AUTO", "CA")):
            return "Commercial Auto"
        if policy.startswith(("BOP", "CP", "PROP")):
            return "Property / BOP"
        if policy.startswith(("UMB", "UM")):
            return "Umbrella"
        if policy.startswith(("CY", "CYBER")):
            return "Cyber Liability"

        return fallback or "Unknown"

    def choose_policy_for_claim(line_of_business, policy_numbers):
        if not policy_numbers:
            return ""

        line = clean(line_of_business).upper()

        if "WC" in line or "WORK" in line:
            return next((p for p in policy_numbers if str(p).upper().startswith("WC")), policy_numbers[0])

        if "PROD" in line or "LIAB" in line or "GL" in line or "GENERAL" in line:
            return next(
                (
                    p for p in policy_numbers
                    if str(p).upper().startswith(("GL", "CGL", "PL", "PROD"))
                ),
                policy_numbers[0],
            )

        return policy_numbers[0]

    section_headers = {
        "claims_detail",
        "claim_detail",
        "claim_details",
        "claims",
        "loss_detail",
        "loss_details",
        "claim_listing",
        "claim_list",
    }

    stop_sections = {
        "loss_summary",
        "summary",
        "totals",
        "total",
        "exposure_summary",
        "premium_summary",
        "policy_year",
        "underwriting_notes",
        "notes",
    }

    profile_labels = {}
    claims_header_row_index = None

    for i, row in enumerate(rows):
        first = norm(row[0] if row else "")

        if first in section_headers:
            claims_header_row_index = i + 1
            break

        if len(row) >= 2:
            label = norm(row[0])
            value = clean(row[1])
            if label and value:
                profile_labels[label] = value

    def profile_first(*labels):
        for label in labels:
            value = profile_labels.get(norm(label))
            if clean(value):
                return clean(value)
        return ""

    # Universal profile extraction from label/value section.
    insured_name = profile_first(
        "insured name",
        "named insured",
        "insured",
        "applicant",
        "account name",
        "company name",
        "company",
        "business name",
    )

    if insured_name:
        parsed_profile["business_name"] = insured_name
        parsed_profile["insured_name"] = insured_name
        parsed_profile["named_insured"] = insured_name

    carrier = profile_first("carrier", "writing carrier", "insurance carrier", "company")
    if carrier:
        parsed_profile["carrier"] = carrier
        parsed_profile["carrier_name"] = carrier
        parsed_profile["writing_carrier"] = carrier

    policy_value = profile_first("policy number", "policy numbers", "policy no", "policy")
    policy_numbers = split_policy_numbers(policy_value)

    line_value = profile_first("line of business", "lines of business", "coverage", "lob")
    line_parts = [
        clean(part)
        for part in re.split(r"\s*(?:/|,|;|\||\band\b|\+)\s*", line_value, flags=re.IGNORECASE)
        if clean(part)
    ]

    if policy_numbers:
        parsed_profile["policy_number"] = policy_numbers[0]
        parsed_profile["main_policy"] = policy_numbers[0]
        parsed_profile["policy_numbers"] = policy_numbers
        parsed_profile["policies"] = [
            {
                "policy_number": policy_number,
                "line_of_business": infer_policy_line(
                    policy_number,
                    line_parts[min(index, len(line_parts) - 1)] if line_parts else "",
                ),
                "policy_type": infer_policy_line(
                    policy_number,
                    line_parts[min(index, len(line_parts) - 1)] if line_parts else "",
                ),
                "carrier": carrier or parsed_profile.get("carrier") or "",
                "writing_carrier": carrier or parsed_profile.get("writing_carrier") or "",
            }
            for index, policy_number in enumerate(policy_numbers)
        ]

    policy_period = profile_first("policy period", "policy term", "coverage period", "effective expiration")
    period_dates = re.findall(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", policy_period)

    if len(period_dates) >= 1:
        parsed_profile["effective_date"] = parsed_profile.get("effective_date") or period_dates[0]
    if len(period_dates) >= 2:
        parsed_profile["expiration_date"] = parsed_profile.get("expiration_date") or period_dates[1]

    account_number = profile_first("account number", "account no", "customer number", "client number")
    if account_number and not looks_like_policy(account_number):
        parsed_profile["account_number"] = account_number
    elif parsed_profile.get("account_number") and looks_like_policy(parsed_profile.get("account_number")):
        parsed_profile["account_number"] = ""

    exposure_map = {
        "annual_revenue": ["annual revenue", "revenue", "sales", "gross sales"],
        "payroll": ["total payroll annual", "payroll", "annual payroll"],
        "employee_count": ["full time employees", "employees", "employee count"],
        "operations": ["operations", "business operations", "description of operations"],
        "facilities": ["facilities", "locations", "premises"],
        "sic_code": ["primary sic code", "sic code"],
        "experience_modifier": ["experience modifier", "emod", "e mod", "experience modifier e mod"],
        "safety_program": ["safety program", "risk control", "safety"],
        "evaluation_date": ["evaluation date", "valuation date", "as of date", "loss run date"],
    }

    for target, labels in exposure_map.items():
        value = profile_first(*labels)
        if value:
            parsed_profile[target] = value

    # Universal claims extraction from claims section.
    repaired_claims = []

    if claims_header_row_index is not None and claims_header_row_index < len(rows):
        headers = [clean(value) for value in rows[claims_header_row_index]]

        claim_number_i = header_index(headers, ["claim #", "claim no", "claim number", "claim_number", "claim"])
        dol_i = header_index(headers, ["date of loss", "loss date", "date_of_loss", "dol"])
        reported_i = header_index(headers, ["date reported", "reported date", "date_reported"])
        claimant_i = header_index(headers, ["claimant", "claimant name", "injured worker", "party"])
        line_i = header_index(headers, ["line", "line of business", "coverage", "lob"])
        description_i = header_index(headers, ["description", "loss description", "cause", "claim description"])
        status_i = header_index(headers, ["status", "claim status", "open closed", "open/closed"])
        incurred_i = header_index(headers, ["total incurred", "incurred", "total"])
        paid_i = header_index(headers, ["paid", "total paid"])
        reserve_i = header_index(headers, ["reserve", "total reserve", "outstanding reserve"])
        subro_i = header_index(headers, ["subrogation", "subro", "recovery"])

        for row in rows[claims_header_row_index + 1:]:
            first = norm(row[0] if row else "")

            if first in stop_sections:
                break

            if not any(clean(cell) for cell in row):
                continue

            claim_number = value_at(row, claim_number_i)

            if not claim_number:
                continue

            line = value_at(row, line_i)
            status = value_at(row, status_i)
            paid = money(value_at(row, paid_i))
            reserve = money(value_at(row, reserve_i))
            incurred = money(value_at(row, incurred_i))

            if incurred <= 0 and (paid or reserve):
                incurred = paid + reserve

            claim = {
                "claim_number": claim_number,
                "date_of_loss": value_at(row, dol_i),
                "date_reported": value_at(row, reported_i),
                "claimant": value_at(row, claimant_i),
                "line_of_business": line,
                "description": value_at(row, description_i),
                "claim_status": status,
                "status": status,
                "total_incurred": incurred,
                "paid": paid,
                "reserve": reserve,
                "subrogation": value_at(row, subro_i),
            }

            claim_policy = choose_policy_for_claim(line, policy_numbers)
            if claim_policy:
                claim["policy_number"] = claim_policy

            repaired_claims.append(claim)

    # If this was truly a section CSV and claims were found, trust the section parser.
    if repaired_claims:
        parsed_claims = repaired_claims

    # LOSSQ_CSV_PRODUCING_AGENCY_PROFILE_EXTRACTION_V1
    # Pull Producing Agency / Producer from the uploaded CSV/loss run itself.
    # Do not use the user's company profile, organization name, carrier name, or demo fallback.
    try:
        agency_labels = [
            "producing agency",
            "producing agent",
            "producer",
            "producer name",
            "agency",
            "agency name",
            "broker",
            "broker name",
            "brokerage",
            "broker of record",
            "agent",
            "agent name",
            "prepared by",
            "contact",
            "contact name",
        ]

        csv_producing_agency = ""

        if callable(locals().get("profile_first")):
            csv_producing_agency = profile_first(*agency_labels)

        def _lossq_csv_agency_clean(value):
            return re.sub(r"\s+", " ", str(value or "").replace("\ufeff", "").strip())

        def _lossq_csv_agency_key(value):
            return re.sub(r"[^a-z0-9]+", "", _lossq_csv_agency_clean(value).lower())

        agency_keys = {_lossq_csv_agency_key(label) for label in agency_labels}

        blocked_values = {
            "",
            "claimsdetail",
            "losssummary",
            "exposurepolicyinformation",
            "policyinformation",
            "claim",
            "claims",
            "claimnumber",
            "policy",
            "policynumber",
            "carrier",
            "writingcarrier",
            "insured",
            "insuredname",
            "namedinsured",
            "date",
            "value",
            "field",
        }

        def _lossq_csv_agency_good_value(value):
            clean_value = _lossq_csv_agency_clean(value)
            value_key = _lossq_csv_agency_key(clean_value)
            if not clean_value:
                return False
            if value_key in agency_keys or value_key in blocked_values:
                return False
            if len(clean_value) < 2:
                return False
            return True

        if not csv_producing_agency and isinstance(rows, list):
            # Same-row label/value, example: Producing Agency, ABC Agency
            for row in rows[:120]:
                cleaned_row = [_lossq_csv_agency_clean(cell) for cell in row]
                for idx, cell in enumerate(cleaned_row):
                    if _lossq_csv_agency_key(cell) in agency_keys:
                        for value in cleaned_row[idx + 1:]:
                            if _lossq_csv_agency_good_value(value):
                                csv_producing_agency = value
                                break
                    if csv_producing_agency:
                        break
                if csv_producing_agency:
                    break

        if not csv_producing_agency and isinstance(rows, list):
            # Header row style, example:
            # Producing Agency, Carrier, Policy Number
            # ABC Agency, Zenith, WC-123
            for row_index, row in enumerate(rows[:80]):
                header_keys = [_lossq_csv_agency_key(cell) for cell in row]
                if not any(key in agency_keys for key in header_keys):
                    continue

                for idx, header_key in enumerate(header_keys):
                    if header_key not in agency_keys:
                        continue

                    for next_row in rows[row_index + 1: row_index + 6]:
                        if idx < len(next_row):
                            candidate = _lossq_csv_agency_clean(next_row[idx])
                            if _lossq_csv_agency_good_value(candidate):
                                csv_producing_agency = candidate
                                break
                    if csv_producing_agency:
                        break
                if csv_producing_agency:
                    break

        if csv_producing_agency:
            parsed_profile["agency_name"] = csv_producing_agency
            parsed_profile["producing_agency"] = csv_producing_agency
            parsed_profile["producer"] = csv_producing_agency
            print("LOSSQ_CSV_PRODUCING_AGENCY_EXTRACTED", {
                "agency_name": csv_producing_agency[:120]
            })
    except Exception as exc:
        print("LOSSQ_CSV_PRODUCING_AGENCY_EXTRACTION_ERROR", str(exc)[:200])

    # Never let account number become a policy bundle.
    if parsed_profile.get("account_number") and looks_like_policy(parsed_profile.get("account_number")) and not lossq_final_account_like_v3(parsed_profile.get("account_number")):
        parsed_profile["account_number"] = ""

    return parsed_claims, parsed_profile






# LOSSQ_UNIVERSAL_CSV_SECTION_OVERLAY_V2
def lossq_universal_csv_section_overlay_v2(file_path, parsed_claims=None, parsed_profile=None):
    """
    Universal section-table overlay for CSV loss runs.

    Fixes:
    - Account Number / Customer Number stays account number, not policy number.
    - CLAIMS DETAIL rows are preserved, including specialty lines like Liquor Liability.
    - Claimant, Jurisdiction/State, Adjuster/Examiner are carried into saved claim rows.
    - Exposure / policy rows populate profile exposures and policy schedule.
    """
    import csv
    import re

    parsed_claims = parsed_claims if isinstance(parsed_claims, list) else []
    parsed_profile = parsed_profile if isinstance(parsed_profile, dict) else {}

    if not str(file_path or "").lower().endswith(".csv"):
        return parsed_claims, parsed_profile

    try:
        with open(file_path, "r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            rows = list(csv.reader(handle))
    except Exception:
        return parsed_claims, parsed_profile

    def clean(value):
        return re.sub(r"\s+", " ", str(value or "").replace("\ufeff", "").strip())

    def k(value):
        return re.sub(r"[^a-z0-9]+", "", clean(value).lower())

    def good(value):
        raw = clean(value)
        return bool(raw and raw.lower() not in {"-", "na", "n/a", "none", "null", "unknown"})

    def is_account_like(value):
        raw = clean(value).upper()
        return bool(re.search(r"\b(ACCT|ACCOUNT|CUSTOMER|CLIENT|CUST)\b", raw) or "ACCT" in raw)

    def is_policy_like(value):
        raw = clean(value).upper()
        if not raw or is_account_like(raw):
            return False
        if not re.search(r"\d", raw):
            return False
        if re.search(r"\b(GL|BOP|WC|AUTO|CA|AL|LIQ|LIQUOR|PROP|CP|UMB|UM|IM|CARGO|GAR|DOL|CY|EPL|DO|PL)\b", raw):
            return True
        if "-" in raw and len(raw) >= 6:
            return True
        return False

    def to_money(value):
        raw = clean(value)
        if not raw:
            return ""
        temp = raw.replace("$", "").replace(",", "").replace("(", "-").replace(")", "")
        try:
            return float(temp)
        except Exception:
            return raw

    def to_bool(value):
        raw = clean(value).lower()
        if raw in {"yes", "y", "true", "1", "litigated", "attorney", "suit"}:
            return True
        if raw in {"no", "n", "false", "0", "none", "-", "na", "n/a", ""}:
            return False
        return bool(raw)

    def map_row(headers, row):
        mapped = {}
        for idx, header in enumerate(headers):
            header_key = k(header)
            if header_key:
                mapped[header_key] = clean(row[idx]) if idx < len(row) else ""
        return mapped

    def first(row_map, *labels):
        for label in labels:
            value = row_map.get(k(label), "")
            if good(value):
                return clean(value)
        return ""

    def first_money(row_map, *labels):
        value = first(row_map, *labels)
        return to_money(value) if value != "" else ""

    # -----------------------------
    # Account information label/value rows.
    # -----------------------------
    profile_labels = {
        "businessname": "business_name",
        "accountname": "business_name",
        "namedinsured": "business_name",
        "insured": "business_name",
        "insuredname": "business_name",
        "accountnumber": "account_number",
        "accountno": "account_number",
        "accountid": "account_number",
        "customernumber": "customer_number",
        "customerno": "customer_number",
        "customerid": "customer_number",
        "clientnumber": "customer_number",
        "clientno": "customer_number",
        "producingagency": "agency_name",
        "producingagent": "agency_name",
        "agency": "agency_name",
        "agencyname": "agency_name",
        "broker": "agency_name",
        "brokerage": "agency_name",
        "producer": "producer",
        "producername": "producer",
        "carrier": "carrier_name",
        "writingcarrier": "writing_carrier",
        "evaluationdate": "evaluation_date",
        "valuationdate": "evaluation_date",
        "asofdate": "evaluation_date",
        "industry": "industry",
        "state": "state",
    }

    for row in rows[:200]:
        if len(row) < 2:
            continue

        label_key = k(row[0])
        value = clean(row[1])
        field = profile_labels.get(label_key)

        if field and good(value):
            parsed_profile[field] = value

    if parsed_profile.get("account_number"):
        parsed_profile["customer_number"] = parsed_profile.get("customer_number") or parsed_profile.get("account_number")

    if parsed_profile.get("customer_number") and not parsed_profile.get("account_number"):
        parsed_profile["account_number"] = parsed_profile.get("customer_number")

    if parsed_profile.get("agency_name"):
        parsed_profile["producing_agency"] = parsed_profile.get("producing_agency") or parsed_profile.get("agency_name")
        parsed_profile["producer"] = parsed_profile.get("producer") or parsed_profile.get("agency_name")

    if parsed_profile.get("producer") and not parsed_profile.get("agency_name"):
        parsed_profile["agency_name"] = parsed_profile.get("producer")
        parsed_profile["producing_agency"] = parsed_profile.get("producer")

    for row in rows[:200]:
        if len(row) >= 2 and k(row[0]) in {"policyperiod", "policyterm", "coverageperiod"}:
            period = clean(row[1])
            dates = re.findall(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", period)
            if len(dates) >= 2:
                parsed_profile["effective_date"] = parsed_profile.get("effective_date") or dates[0]
                parsed_profile["expiration_date"] = parsed_profile.get("expiration_date") or dates[1]

    # -----------------------------
    # Table finder.
    # -----------------------------
    def find_header(required_groups, preferred_sections=None):
        preferred_sections = preferred_sections or []
        section_seen = not preferred_sections

        for idx, row in enumerate(rows):
            row_text = " ".join(clean(cell).lower() for cell in row if clean(cell))
            row_keys = {k(cell) for cell in row if clean(cell)}

            if preferred_sections and any(token in row_text for token in preferred_sections):
                section_seen = True
                continue

            if not section_seen:
                continue

            if all(any(option in row_keys for option in group) for group in required_groups):
                return idx, row

        return None, []

    # -----------------------------
    # Exposure / policy table.
    # -----------------------------
    exposure_idx, exposure_headers = find_header(
        [
            {"policynumber", "policyno", "policy"},
            {"lineofbusiness", "coverage", "policytype", "lob", "currentpremium", "exposurebasis"},
        ],
        ["exposure", "policy information", "policy schedule"],
    )

    exposure_rows = []
    if exposure_idx is not None:
        for row in rows[exposure_idx + 1:]:
            row_text = " ".join(clean(cell).lower() for cell in row if clean(cell))

            if not any(clean(cell) for cell in row):
                break

            if any(stop in row_text for stop in ["claims detail", "claim detail", "loss summary", "underwriting notes"]):
                break

            rm = map_row(exposure_headers, row)
            policy_number = first(rm, "Policy Number", "Policy No", "Policy")
            line = first(rm, "Line of Business", "Coverage", "Policy Type", "LOB")

            if not is_policy_like(policy_number) and not line:
                continue

            exposure = {
                "policy_number": policy_number,
                "policy_type": line,
                "line_of_business": line,
                "carrier": first(rm, "Carrier", "Writing Carrier") or parsed_profile.get("carrier_name", ""),
                "effective_date": first(rm, "Effective Date", "Policy Effective Date"),
                "expiration_date": first(rm, "Expiration Date", "Policy Expiration Date"),
                "exposure_basis": first(rm, "Exposure Basis", "Basis"),
                "exposure_value": first(rm, "Exposure Value", "Exposure"),
                "payroll": first_money(rm, "Payroll"),
                "revenue": first_money(rm, "Revenue", "Sales", "Gross Sales"),
                "employee_count": first_money(rm, "Employee Count", "Employees"),
                "vehicle_count": first_money(rm, "Vehicle Count", "Vehicles", "Autos"),
                "driver_count": first_money(rm, "Driver Count", "Drivers"),
                "property_tiv": first_money(rm, "Property TIV", "TIV", "Total Insured Value"),
                "current_premium": first_money(rm, "Current Premium"),
                "expiring_premium": first_money(rm, "Expiring Premium"),
                "target_renewal_premium": first_money(rm, "Target Renewal Premium"),
            }

            exposure_rows.append({key: value for key, value in exposure.items() if value not in ("", None)})

    # -----------------------------
    # Claims detail table.
    # -----------------------------
    claim_idx, claim_headers = find_header(
        [
            {"claimnumber", "claimno", "claim", "claimid"},
            {"policynumber", "policyno", "policy", "totalincurred", "paid", "reserve"},
        ],
        ["claims detail", "claim detail", "claims"],
    )

    csv_claims = []
    if claim_idx is not None:
        for row in rows[claim_idx + 1:]:
            row_text = " ".join(clean(cell).lower() for cell in row if clean(cell))

            if not any(clean(cell) for cell in row):
                break

            if any(stop in row_text for stop in ["underwriting notes", "loss summary", "exposure / policy", "account information"]):
                break

            rm = map_row(claim_headers, row)
            claim_number = first(rm, "Claim Number", "Claim #", "Claim No", "Claim ID", "Claim")
            policy_number = first(rm, "Policy Number", "Policy No", "Policy")

            if not good(claim_number):
                continue

            claim_key = k(claim_number)
            if claim_key in {"claimnumber", "claimno", "claimid", "claim"}:
                continue

            claim = {
                "claim_number": claim_number,
                "policy_number": policy_number,
                "line_of_business": first(rm, "Line of Business", "Coverage", "Policy Type", "LOB"),
                "claim_type": first(rm, "Line of Business", "Coverage", "Policy Type", "LOB"),
                "claimant": first(rm, "Claimant", "Claimant Name", "Injured Worker", "Injured Party", "Employee Name", "Plaintiff", "Customer Name", "Third Party Name"),
                "jurisdiction_state": first(rm, "Jurisdiction/State", "Jurisdiction", "State", "Venue State", "Loss State"),
                "venue_state": first(rm, "Jurisdiction/State", "Jurisdiction", "State", "Venue State", "Loss State"),
                "adjuster": first(rm, "Adjuster", "Adjuster/Examiner", "Examiner", "Claim Adjuster", "Claim Examiner", "File Handler"),
                "examiner": first(rm, "Examiner", "Adjuster/Examiner", "Adjuster", "Claim Examiner", "File Handler"),
                "date_of_loss": first(rm, "Date of Loss", "Loss Date"),
                "date_reported": first(rm, "Date Reported", "Reported Date"),
                "date_closed": first(rm, "Date Closed", "Closed Date"),
                "status": first(rm, "Status", "Claim Status"),
                "cause_of_loss": first(rm, "Cause of Loss", "Loss Cause", "Cause"),
                "description": first(rm, "Description", "Loss Description", "Narrative"),
                "paid_amount": first_money(rm, "Paid", "Paid Amount", "Total Paid"),
                "reserve_amount": first_money(rm, "Reserve", "Reserve Amount", "Outstanding Reserve"),
                "total_incurred": first_money(rm, "Total Incurred", "Incurred", "Gross Incurred", "Net Incurred"),
                "litigation": to_bool(first(rm, "Litigation", "Litigated")),
                "attorney_assigned": to_bool(first(rm, "Attorney Assigned", "Attorney", "Counsel")),
            }

            csv_claims.append({key: value for key, value in claim.items() if value not in ("", None)})

    # -----------------------------
    # Merge parsed claims + CSV section claims.
    # -----------------------------
    merged = []
    seen = {}

    def merge_key(claim):
        claim_number = clean(claim.get("claim_number") or claim.get("Claim Number") or claim.get("claim #")).upper()
        policy_number = clean(claim.get("policy_number") or claim.get("Policy Number") or claim.get("policy")).upper()
        return f"{claim_number}|{policy_number}"

    for claim in parsed_claims:
        if isinstance(claim, dict):
            target = dict(claim)
            merged.append(target)
            seen[merge_key(target)] = target

    overlay_fields = [
        "policy_number",
        "line_of_business",
        "claim_type",
        "claimant",
        "jurisdiction_state",
        "venue_state",
        "adjuster",
        "examiner",
        "date_of_loss",
        "date_reported",
        "date_closed",
        "status",
        "cause_of_loss",
        "description",
        "paid_amount",
        "reserve_amount",
        "total_incurred",
        "litigation",
        "attorney_assigned",
    ]

    added_claims = 0
    updated_claims = 0

    for csv_claim in csv_claims:
        mk = merge_key(csv_claim)

        if mk in seen:
            target = seen[mk]
            for field in overlay_fields:
                value = csv_claim.get(field)
                if value not in ("", None):
                    if field in {"claimant", "jurisdiction_state", "venue_state", "adjuster", "examiner"} or not target.get(field):
                        target[field] = value
            updated_claims += 1
        else:
            target = dict(csv_claim)
            merged.append(target)
            seen[mk] = target
            added_claims += 1

    parsed_claims = merged

    # -----------------------------
    # Exposures and policy schedule.
    # -----------------------------
    if exposure_rows:
        parsed_profile["exposures"] = exposure_rows
        parsed_profile["exposure_inputs"] = {"exposure_rows": exposure_rows}

        def nums(field):
            values = []
            for exposure in exposure_rows:
                try:
                    value = exposure.get(field)
                    if value not in ("", None):
                        values.append(float(value))
                except Exception:
                    pass
            return values

        for field in ["current_premium", "expiring_premium", "target_renewal_premium"]:
            values = nums(field)
            if values:
                parsed_profile[field] = sum(values)
                parsed_profile["exposure_inputs"][field] = sum(values)

        for field in ["payroll", "revenue", "employee_count", "vehicle_count", "driver_count", "property_tiv"]:
            values = nums(field)
            if values:
                parsed_profile[field] = max(values)
                parsed_profile["exposure_inputs"][field] = max(values)

    claim_counts = {}
    claim_totals = {}
    claim_lines = {}

    for claim in parsed_claims:
        policy_number = clean(claim.get("policy_number")).upper()
        if not is_policy_like(policy_number):
            continue

        claim_counts[policy_number] = claim_counts.get(policy_number, 0) + 1

        try:
            claim_totals[policy_number] = claim_totals.get(policy_number, 0.0) + float(claim.get("total_incurred") or 0)
        except Exception:
            pass

        line = clean(claim.get("line_of_business") or claim.get("claim_type"))
        if line:
            claim_lines[policy_number] = line

    policies_by_number = {}

    existing_policies = parsed_profile.get("policies") if isinstance(parsed_profile.get("policies"), list) else []
    for policy in existing_policies:
        if not isinstance(policy, dict):
            continue

        policy_number = clean(policy.get("policy_number") or policy.get("Policy Number")).upper()
        if is_policy_like(policy_number):
            policies_by_number[policy_number] = dict(policy)

    for exposure in exposure_rows:
        policy_number = clean(exposure.get("policy_number")).upper()
        if not is_policy_like(policy_number):
            continue

        policy = policies_by_number.get(policy_number, {})
        policy.update({
            "policy_number": exposure.get("policy_number"),
            "policy_type": exposure.get("policy_type") or exposure.get("line_of_business") or claim_lines.get(policy_number) or policy.get("policy_type"),
            "line_of_business": exposure.get("line_of_business") or exposure.get("policy_type") or claim_lines.get(policy_number) or policy.get("line_of_business"),
            "carrier": exposure.get("carrier") or policy.get("carrier") or parsed_profile.get("carrier_name"),
            "effective_date": exposure.get("effective_date") or policy.get("effective_date") or parsed_profile.get("effective_date"),
            "expiration_date": exposure.get("expiration_date") or policy.get("expiration_date") or parsed_profile.get("expiration_date"),
            "claim_count": claim_counts.get(policy_number, policy.get("claim_count", 0)),
            "total_incurred": claim_totals.get(policy_number, policy.get("total_incurred", 0)),
            "current_premium": exposure.get("current_premium") or policy.get("current_premium"),
            "expiring_premium": exposure.get("expiring_premium") or policy.get("expiring_premium"),
            "target_renewal_premium": exposure.get("target_renewal_premium") or policy.get("target_renewal_premium"),
        })
        policies_by_number[policy_number] = policy

    # Add policy schedule rows from claims even if an exposure row is absent.
    for policy_number, count in claim_counts.items():
        if policy_number not in policies_by_number:
            policies_by_number[policy_number] = {
                "policy_number": policy_number,
                "policy_type": claim_lines.get(policy_number, ""),
                "line_of_business": claim_lines.get(policy_number, ""),
                "carrier": parsed_profile.get("carrier_name") or parsed_profile.get("writing_carrier"),
                "effective_date": parsed_profile.get("effective_date"),
                "expiration_date": parsed_profile.get("expiration_date"),
                "claim_count": count,
                "total_incurred": claim_totals.get(policy_number, 0),
            }

    if policies_by_number:
        parsed_profile["policies"] = list(policies_by_number.values())
        parsed_profile["policy_schedule"] = parsed_profile["policies"]

        first_policy = parsed_profile["policies"][0].get("policy_number")
        current_main = parsed_profile.get("policy_number") or parsed_profile.get("main_policy")

        if not is_policy_like(current_main):
            parsed_profile["policy_number"] = first_policy
            parsed_profile["main_policy"] = first_policy

    # Never let account/customer number overwrite policy fields.
    for field in ["policy_number", "main_policy"]:
        if parsed_profile.get(field) and is_account_like(parsed_profile.get(field)):
            first_policy = ""
            for policy in parsed_profile.get("policies") or []:
                candidate = policy.get("policy_number") if isinstance(policy, dict) else ""
                if is_policy_like(candidate):
                    first_policy = candidate
                    break
            parsed_profile[field] = first_policy

    print("LOSSQ_UNIVERSAL_CSV_SECTION_OVERLAY_V2", {
        "csv_claims": len(csv_claims),
        "added_claims": added_claims,
        "updated_claims": updated_claims,
        "exposure_rows": len(exposure_rows),
        "account_number": str(parsed_profile.get("account_number") or "")[:80],
        "policy_number": str(parsed_profile.get("policy_number") or "")[:80],
    })

    return parsed_claims, parsed_profile


# LOSSQ_CLAIM_DETAIL_FIELDS_FROM_UPLOAD_ROW_V2
def lossq_claim_detail_clean_v2(value):
    return re.sub(r"\s+", " ", str(value or "").replace("\ufeff", "").strip())


def lossq_claim_detail_key_v2(value):
    return re.sub(r"[^a-z0-9]+", "", lossq_claim_detail_clean_v2(value).lower())


def lossq_claim_detail_first_v2(raw_claim, *labels):
    if not isinstance(raw_claim, dict):
        return ""

    label_keys = {lossq_claim_detail_key_v2(label) for label in labels}

    for key, value in raw_claim.items():
        if lossq_claim_detail_key_v2(key) in label_keys:
            clean_value = lossq_claim_detail_clean_v2(value)
            if clean_value and clean_value.lower() not in {"-", "na", "n/a", "none", "null", "unknown"}:
                return clean_value

    return ""


def lossq_apply_claim_detail_fields_to_normalized_claim_v2(normalized_claim, raw_claim):
    if not isinstance(normalized_claim, dict):
        return normalized_claim

    claimant = lossq_claim_detail_first_v2(
        raw_claim,
        "claimant",
        "claimant name",
        "injured worker",
        "injured party",
        "employee name",
        "plaintiff",
        "customer name",
        "third party name",
    )

    jurisdiction_state = lossq_claim_detail_first_v2(
        raw_claim,
        "jurisdiction/state",
        "jurisdiction",
        "state",
        "venue state",
        "loss state",
    )

    adjuster = lossq_claim_detail_first_v2(
        raw_claim,
        "adjuster",
        "adjuster/examiner",
        "examiner",
        "claim adjuster",
        "claim examiner",
        "file handler",
    )

    if claimant:
        normalized_claim["claimant"] = claimant

    if jurisdiction_state:
        normalized_claim["jurisdiction_state"] = jurisdiction_state
        normalized_claim["venue_state"] = normalized_claim.get("venue_state") or jurisdiction_state

    if adjuster:
        normalized_claim["adjuster"] = adjuster
        normalized_claim["examiner"] = normalized_claim.get("examiner") or adjuster

    normalized_claim.pop("claimant_name", None)
    normalized_claim.pop("jurisdiction", None)
    normalized_claim.pop("state", None)
    normalized_claim.pop("adjuster_examiner", None)

    return normalized_claim



# LOSSQ_UNIVERSAL_CSV_ACCOUNT_EXPOSURE_CLAIM_DETAIL_OVERLAY_V1
def lossq_universal_csv_account_exposure_claim_detail_overlay(file_path, parsed_claims=None, parsed_profile=None):
    """
    Universal CSV section overlay.

    Purpose:
    - Pull true account/customer number from uploaded file.
    - Pull exposure/premium rows from uploaded file.
    - Pull every claim row from CLAIMS DETAIL, including Claimant, Jurisdiction/State,
      Adjuster/Examiner, and specialty lines such as Liquor Liability.
    - Merge missing rows/details into parsed_claims without hardcoding any account,
      business, carrier, or sample file.
    """
    import csv
    import re

    parsed_claims = parsed_claims if isinstance(parsed_claims, list) else []
    parsed_profile = parsed_profile if isinstance(parsed_profile, dict) else {}

    if not str(file_path or "").lower().endswith(".csv"):
        return parsed_claims, parsed_profile

    try:
        with open(file_path, "r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            rows = list(csv.reader(handle))
    except Exception:
        return parsed_claims, parsed_profile

    def clean(value):
        return re.sub(r"\s+", " ", str(value or "").replace("\ufeff", "").strip())

    def key(value):
        return re.sub(r"[^a-z0-9]+", "", clean(value).lower())

    def money(value):
        raw = clean(value)
        if not raw:
            return ""
        raw = raw.replace("$", "").replace(",", "").replace("(", "-").replace(")", "")
        try:
            return float(raw)
        except Exception:
            return clean(value)

    def bool_value(value):
        raw = clean(value).lower()
        if raw in {"yes", "y", "true", "1", "litigated", "attorney", "suit"}:
            return True
        if raw in {"no", "n", "false", "0", "none"}:
            return False
        return bool(raw and raw not in {"-", "na", "n/a"})

    def good_text(value):
        raw = clean(value)
        if not raw:
            return False
        lowered = raw.lower()
        if lowered in {"-", "na", "n/a", "none", "null", "unknown"}:
            return False
        return True

    def first(row_map, *labels):
        for label in labels:
            value = row_map.get(key(label), "")
            if good_text(value):
                return clean(value)
        return ""

    def first_money(row_map, *labels):
        value = first(row_map, *labels)
        return money(value) if value != "" else ""

    def row_map_from_headers(headers, row):
        mapped = {}
        for idx, header in enumerate(headers):
            header_key = key(header)
            if not header_key:
                continue
            mapped[header_key] = clean(row[idx]) if idx < len(row) else ""
        return mapped

    profile_label_map = {
        "businessname": "business_name",
        "accountname": "business_name",
        "namedinsured": "business_name",
        "insured": "business_name",
        "insuredname": "business_name",
        "accountnumber": "account_number",
        "accountno": "account_number",
        "account": "account_number",
        "customernumber": "customer_number",
        "customerno": "customer_number",
        "clientnumber": "customer_number",
        "producingagency": "agency_name",
        "producingagent": "agency_name",
        "agency": "agency_name",
        "agencyname": "agency_name",
        "broker": "agency_name",
        "brokerage": "agency_name",
        "producer": "producer",
        "producername": "producer",
        "carrier": "carrier_name",
        "writingcarrier": "writing_carrier",
        "policynumber": "policy_number",
        "mainpolicy": "policy_number",
        "mainpolicynumber": "policy_number",
        "evaluationdate": "evaluation_date",
        "valuationdate": "evaluation_date",
        "asofdate": "evaluation_date",
        "industry": "industry",
        "state": "state",
    }

    # Label/value account section.
    for row in rows[:150]:
        if len(row) < 2:
            continue
        label_key = key(row[0])
        value = clean(row[1])
        field = profile_label_map.get(label_key)
        if field and good_text(value):
            parsed_profile[field] = value

    if parsed_profile.get("account_number"):
        parsed_profile["customer_number"] = parsed_profile.get("customer_number") or parsed_profile.get("account_number")

    if parsed_profile.get("agency_name"):
        parsed_profile["producing_agency"] = parsed_profile.get("producing_agency") or parsed_profile.get("agency_name")
        parsed_profile["producer"] = parsed_profile.get("producer") or parsed_profile.get("agency_name")

    if parsed_profile.get("producer") and not parsed_profile.get("agency_name"):
        parsed_profile["agency_name"] = parsed_profile.get("producer")
        parsed_profile["producing_agency"] = parsed_profile.get("producer")

    # Policy period label.
    for row in rows[:150]:
        if len(row) >= 2 and key(row[0]) in {"policyperiod", "policyterm", "coverageperiod"}:
            period = clean(row[1])
            dates = re.findall(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", period)
            if len(dates) >= 2:
                parsed_profile["effective_date"] = parsed_profile.get("effective_date") or dates[0]
                parsed_profile["expiration_date"] = parsed_profile.get("expiration_date") or dates[1]

    def find_table_header(required_any, preferred_section_tokens=None):
        preferred_section_tokens = preferred_section_tokens or []
        section_seen = not preferred_section_tokens

        for idx, row in enumerate(rows):
            row_text = " ".join(clean(cell).lower() for cell in row if clean(cell))
            row_keys = {key(cell) for cell in row if clean(cell)}

            if preferred_section_tokens and any(token in row_text for token in preferred_section_tokens):
                section_seen = True
                continue

            if not section_seen:
                continue

            if all(any(req in row_keys for req in req_group) for req_group in required_any):
                return idx, row

        return None, []

    # Exposure / policy table.
    exposure_header_idx, exposure_headers = find_table_header(
        required_any=[
            {"policynumber", "policyno", "policy"},
            {"lineofbusiness", "coverage", "policytype", "lob", "exposurebasis", "currentpremium"},
        ],
        preferred_section_tokens=["exposure", "policy information", "policy schedule"],
    )

    exposure_rows = []
    if exposure_header_idx is not None:
        for row in rows[exposure_header_idx + 1:]:
            row_text = " ".join(clean(cell).lower() for cell in row if clean(cell))
            if not any(clean(cell) for cell in row):
                break
            if any(stop in row_text for stop in ["claims detail", "claim detail", "loss summary", "underwriting notes"]):
                break

            row_map = row_map_from_headers(exposure_headers, row)
            policy_number = first(row_map, "Policy Number", "Policy No", "Policy")
            line_of_business = first(row_map, "Line of Business", "Coverage", "Policy Type", "LOB")
            if not policy_number and not line_of_business:
                continue

            exposure = {
                "policy_number": policy_number,
                "policy_type": line_of_business,
                "line_of_business": line_of_business,
                "carrier": first(row_map, "Carrier", "Writing Carrier") or parsed_profile.get("carrier_name", ""),
                "effective_date": first(row_map, "Effective Date", "Policy Effective Date"),
                "expiration_date": first(row_map, "Expiration Date", "Policy Expiration Date"),
                "exposure_basis": first(row_map, "Exposure Basis", "Basis"),
                "exposure_value": first(row_map, "Exposure Value", "Exposure"),
                "payroll": first_money(row_map, "Payroll"),
                "revenue": first_money(row_map, "Revenue", "Sales", "Gross Sales"),
                "employee_count": first_money(row_map, "Employee Count", "Employees"),
                "vehicle_count": first_money(row_map, "Vehicle Count", "Vehicles", "Autos"),
                "driver_count": first_money(row_map, "Driver Count", "Drivers"),
                "property_tiv": first_money(row_map, "Property TIV", "TIV", "Total Insured Value"),
                "current_premium": first_money(row_map, "Current Premium"),
                "expiring_premium": first_money(row_map, "Expiring Premium"),
                "target_renewal_premium": first_money(row_map, "Target Renewal Premium"),
            }

            exposure_rows.append({k: v for k, v in exposure.items() if v not in ("", None)})

    # Claims detail table.
    claim_header_idx, claim_headers = find_table_header(
        required_any=[
            {"claimnumber", "claimno", "claim", "claimid"},
            {"policynumber", "policy", "policyno", "totalincurred", "paid", "reserve"},
        ],
        preferred_section_tokens=["claims detail", "claim detail", "claims"],
    )

    csv_claims = []
    if claim_header_idx is not None:
        for row in rows[claim_header_idx + 1:]:
            row_text = " ".join(clean(cell).lower() for cell in row if clean(cell))
            if not any(clean(cell) for cell in row):
                break
            if any(stop in row_text for stop in ["underwriting notes", "loss summary", "exposure / policy", "account information"]):
                break

            row_map = row_map_from_headers(claim_headers, row)

            claim_number = first(row_map, "Claim Number", "Claim #", "Claim No", "Claim ID", "Claim")
            policy_number = first(row_map, "Policy Number", "Policy No", "Policy")

            if not claim_number:
                continue

            claim = {
                "claim_number": claim_number,
                "policy_number": policy_number,
                "line_of_business": first(row_map, "Line of Business", "Coverage", "Policy Type", "LOB"),
                "claim_type": first(row_map, "Line of Business", "Coverage", "Policy Type", "LOB"),
                "claimant": first(row_map, "Claimant", "Claimant Name", "Injured Worker", "Injured Party", "Employee Name", "Plaintiff", "Customer Name", "Third Party Name"),
                "jurisdiction_state": first(row_map, "Jurisdiction/State", "Jurisdiction", "State", "Venue State", "Loss State"),
                "venue_state": first(row_map, "Jurisdiction/State", "Jurisdiction", "State", "Venue State", "Loss State"),
                "adjuster": first(row_map, "Adjuster", "Adjuster/Examiner", "Examiner", "Claim Adjuster", "Claim Examiner", "File Handler"),
                "examiner": first(row_map, "Examiner", "Adjuster/Examiner", "Adjuster", "Claim Examiner", "File Handler"),
                "date_of_loss": first(row_map, "Date of Loss", "Loss Date"),
                "date_reported": first(row_map, "Date Reported", "Reported Date"),
                "date_closed": first(row_map, "Date Closed", "Closed Date"),
                "status": first(row_map, "Status", "Claim Status"),
                "cause_of_loss": first(row_map, "Cause of Loss", "Loss Cause", "Cause"),
                "description": first(row_map, "Description", "Loss Description", "Narrative"),
                "paid_amount": first_money(row_map, "Paid", "Paid Amount", "Total Paid"),
                "reserve_amount": first_money(row_map, "Reserve", "Reserve Amount", "Outstanding Reserve"),
                "total_incurred": first_money(row_map, "Total Incurred", "Incurred", "Gross Incurred", "Net Incurred"),
                "litigation": bool_value(first(row_map, "Litigation", "Litigated")),
                "attorney_assigned": bool_value(first(row_map, "Attorney Assigned", "Attorney", "Counsel")),
            }

            csv_claims.append({k: v for k, v in claim.items() if v not in ("", None)})

    # Merge CSV claims into parsed claims.
    merged_claims = []
    seen = {}

    def claim_key(claim):
        claim_number = clean(claim.get("claim_number") or claim.get("Claim Number") or claim.get("claim #")).upper()
        policy_number = clean(claim.get("policy_number") or claim.get("Policy Number") or claim.get("policy")).upper()
        return f"{claim_number}|{policy_number}"

    for claim in parsed_claims:
        if not isinstance(claim, dict):
            continue
        merged = dict(claim)
        merged_claims.append(merged)
        seen[claim_key(merged)] = merged

    overlay_fields = [
        "policy_number",
        "line_of_business",
        "claim_type",
        "claimant",
        "jurisdiction_state",
        "venue_state",
        "adjuster",
        "examiner",
        "date_of_loss",
        "date_reported",
        "date_closed",
        "status",
        "cause_of_loss",
        "description",
        "paid_amount",
        "reserve_amount",
        "total_incurred",
        "litigation",
        "attorney_assigned",
    ]

    added_claims = 0
    updated_claims = 0

    for csv_claim in csv_claims:
        ck = claim_key(csv_claim)
        if ck in seen:
            target = seen[ck]
            for field in overlay_fields:
                value = csv_claim.get(field)
                if value not in ("", None):
                    if field in {"claimant", "jurisdiction_state", "venue_state", "adjuster", "examiner"} or not target.get(field):
                        target[field] = value
            updated_claims += 1
        else:
            merged_claims.append(dict(csv_claim))
            seen[ck] = merged_claims[-1]
            added_claims += 1

    parsed_claims = merged_claims

    # Aggregate exposure inputs.
    if exposure_rows:
        parsed_profile["exposures"] = exposure_rows
        parsed_profile["exposure_inputs"] = {
            "exposure_rows": exposure_rows,
        }

        def numeric_values(field):
            values = []
            for exposure in exposure_rows:
                value = exposure.get(field)
                try:
                    if value not in ("", None):
                        values.append(float(value))
                except Exception:
                    pass
            return values

        for field in ["current_premium", "expiring_premium", "target_renewal_premium"]:
            values = numeric_values(field)
            if values:
                parsed_profile[field] = sum(values)
                parsed_profile["exposure_inputs"][field] = sum(values)

        for field in ["payroll", "revenue", "employee_count", "vehicle_count", "driver_count", "property_tiv"]:
            values = numeric_values(field)
            if values:
                parsed_profile[field] = max(values)
                parsed_profile["exposure_inputs"][field] = max(values)

    # Rebuild/merge policy schedule from exposure rows and claim rows.
    if exposure_rows:
        claim_counts = {}
        claim_totals = {}

        for claim in parsed_claims:
            policy_number = clean(claim.get("policy_number")).upper()
            if not policy_number:
                continue
            claim_counts[policy_number] = claim_counts.get(policy_number, 0) + 1
            try:
                claim_totals[policy_number] = claim_totals.get(policy_number, 0.0) + float(claim.get("total_incurred") or 0)
            except Exception:
                pass

        existing_policies = parsed_profile.get("policies") if isinstance(parsed_profile.get("policies"), list) else []
        policies_by_number = {}

        for policy in existing_policies:
            if not isinstance(policy, dict):
                continue
            policy_number = clean(policy.get("policy_number") or policy.get("Policy Number")).upper()
            if policy_number:
                policies_by_number[policy_number] = dict(policy)

        for exposure in exposure_rows:
            policy_number = clean(exposure.get("policy_number")).upper()
            if not policy_number:
                continue

            policy = policies_by_number.get(policy_number, {})
            policy.update({
                "policy_number": exposure.get("policy_number"),
                "policy_type": exposure.get("policy_type") or exposure.get("line_of_business") or policy.get("policy_type"),
                "line_of_business": exposure.get("line_of_business") or exposure.get("policy_type") or policy.get("line_of_business"),
                "carrier": exposure.get("carrier") or policy.get("carrier") or parsed_profile.get("carrier_name"),
                "effective_date": exposure.get("effective_date") or policy.get("effective_date") or parsed_profile.get("effective_date"),
                "expiration_date": exposure.get("expiration_date") or policy.get("expiration_date") or parsed_profile.get("expiration_date"),
                "claim_count": claim_counts.get(policy_number, policy.get("claim_count", 0)),
                "total_incurred": claim_totals.get(policy_number, policy.get("total_incurred", 0)),
                "current_premium": exposure.get("current_premium") or policy.get("current_premium"),
                "expiring_premium": exposure.get("expiring_premium") or policy.get("expiring_premium"),
                "target_renewal_premium": exposure.get("target_renewal_premium") or policy.get("target_renewal_premium"),
            })
            policies_by_number[policy_number] = policy

        parsed_profile["policies"] = list(policies_by_number.values())
        parsed_profile["policy_schedule"] = parsed_profile["policies"]

        if parsed_profile["policies"] and not parsed_profile.get("policy_number"):
            parsed_profile["policy_number"] = parsed_profile["policies"][0].get("policy_number")

    print("LOSSQ_UNIVERSAL_CSV_ACCOUNT_EXPOSURE_CLAIM_DETAIL_OVERLAY", {
        "csv_claims": len(csv_claims),
        "added_claims": added_claims,
        "updated_claims": updated_claims,
        "exposure_rows": len(exposure_rows),
        "account_number": str(parsed_profile.get("account_number") or "")[:80],
    })

    return parsed_claims, parsed_profile


# LOSSQ_CLAIM_DETAIL_FIELDS_FROM_UPLOAD_ROW_V1
def lossq_claim_detail_clean_value(value):
    return re.sub(r"\s+", " ", str(value or "").replace("\ufeff", "").strip())


def lossq_claim_detail_key(value):
    return re.sub(r"[^a-z0-9]+", "", lossq_claim_detail_clean_value(value).lower())


def lossq_claim_detail_value(raw_claim, *labels):
    if not isinstance(raw_claim, dict):
        return ""

    label_keys = {lossq_claim_detail_key(label) for label in labels}

    for key, value in raw_claim.items():
        if lossq_claim_detail_key(key) in label_keys:
            clean_value = lossq_claim_detail_clean_value(value)
            if clean_value and clean_value.lower() not in {"-", "na", "n/a", "none", "null", "unknown"}:
                return clean_value

    return ""


def lossq_apply_claim_detail_fields_to_normalized_claim(normalized_claim, raw_claim):
    if not isinstance(normalized_claim, dict):
        return normalized_claim

    claimant = lossq_claim_detail_value(
        raw_claim,
        "claimant",
        "claimant name",
        "injured worker",
        "injured party",
        "employee name",
        "plaintiff",
        "customer name",
        "third party name",
    )

    jurisdiction_state = lossq_claim_detail_value(
        raw_claim,
        "jurisdiction/state",
        "jurisdiction",
        "state",
        "venue state",
        "loss state",
    )

    adjuster = lossq_claim_detail_value(
        raw_claim,
        "adjuster",
        "adjuster/examiner",
        "examiner",
        "claim adjuster",
        "claim examiner",
        "file handler",
    )

    if claimant:
        normalized_claim["claimant"] = claimant

    if jurisdiction_state:
        normalized_claim["jurisdiction_state"] = jurisdiction_state
        normalized_claim["venue_state"] = normalized_claim.get("venue_state") or jurisdiction_state

    if adjuster:
        normalized_claim["adjuster"] = adjuster
        normalized_claim["examiner"] = normalized_claim.get("examiner") or adjuster

    return normalized_claim



# LOSSQ_UNIVERSAL_PROFILE_CLAIM_FINAL_NORMALIZER_V1
def lossq_universal_profile_claim_final_normalizer(parsed_claims=None, parsed_profile=None):
    """
    Final universal normalizer after all CSV/PDF/XLSX repairs.
    Keeps profile identity, producing agency, account number, policies, and claim rows consistent.
    No carrier, account, customer, or demo-file hardcoding.
    """
    parsed_claims = parsed_claims if isinstance(parsed_claims, list) else []
    parsed_profile = parsed_profile if isinstance(parsed_profile, dict) else {}

    def clean(value):
        return re.sub(r"\s+", " ", str(value or "").replace("\ufeff", "").strip())

    def norm(value):
        return re.sub(r"[^a-z0-9]+", "_", clean(value).lower()).strip("_")

    def looks_like_policy(value):
        value = clean(value).upper()
        if not value:
            return False
        return lossq_looks_like_policy_but_not_account(value)

    def split_policy_numbers(value):
        raw = clean(value)
        if not raw:
            return []

        found = []
        pieces = re.split(r"\s*(?:/|,|;|\||\band\b|\+)\s*", raw, flags=re.IGNORECASE)

        for piece in pieces:
            piece = clean(piece).upper()
            matches = re.findall(r"\b[A-Z]{1,8}[- ]?\d{2,6}[- ]?[A-Z0-9]{2,12}\b", piece)
            for match in matches:
                match = clean(match).upper().replace(" ", "-")
                if match and match not in found:
                    found.append(match)

        return found

    def money(value):
        raw = clean(value)
        if not raw:
            return 0.0
        neg = raw.startswith("(") and raw.endswith(")")
        raw = raw.replace("$", "").replace(",", "").replace("(", "").replace(")", "")
        raw = re.sub(r"[^0-9.\-]", "", raw)
        if raw in {"", "-", ".", "-."}:
            return 0.0
        try:
            amount = float(raw)
            return -amount if neg else amount
        except Exception:
            return 0.0

    def first_profile_value(*keys):
        normalized = {norm(k): v for k, v in parsed_profile.items()}
        for key in keys:
            value = parsed_profile.get(key)
            if clean(value):
                return clean(value)

            value = normalized.get(norm(key))
            if clean(value):
                return clean(value)

        return ""

    # Business / insured name.
    insured_name = first_profile_value(
        "business_name",
        "insured_name",
        "named_insured",
        "insured",
        "applicant",
        "account_name",
        "company_name",
        "company",
    )

    if insured_name and insured_name.lower() not in {"business name not set", "not set", "unknown"}:
        parsed_profile["business_name"] = insured_name
        parsed_profile["insured_name"] = insured_name
        parsed_profile["named_insured"] = insured_name

    # Producing agency / broker.
    producing_agency = first_profile_value(
        "producing_agency",
        "agency_name",
        "agency",
        "broker",
        "brokerage",
        "producer",
        "producer_name",
    )

    if producing_agency and producing_agency.lower() not in {"agency not set", "not set", "unknown"}:
        parsed_profile["producing_agency"] = producing_agency
        parsed_profile["agency_name"] = producing_agency
        parsed_profile["producer"] = producing_agency

    # Policy numbers from policy fields and policy schedule.
    policy_candidates = []
    for key in [
        "policy_number",
        "main_policy",
        "policy_numbers",
        "account_number",
        "customer_number",
    ]:
        value = parsed_profile.get(key)
        if isinstance(value, list):
            for item in value:
                policy_candidates.extend(split_policy_numbers(item))
        else:
            policy_candidates.extend(split_policy_numbers(value))

    policies = parsed_profile.get("policies")
    if isinstance(policies, list):
        for item in policies:
            if isinstance(item, dict):
                policy_candidates.extend(
                    split_policy_numbers(
                        item.get("policy_number")
                        or item.get("policy")
                        or item.get("number")
                    )
                )

    policy_numbers = []
    for policy in policy_candidates:
        policy = clean(policy).upper()
        if policy and policy not in policy_numbers:
            policy_numbers.append(policy)

    if policy_numbers:
        parsed_profile["policy_number"] = policy_numbers[0]
        parsed_profile["main_policy"] = policy_numbers[0]
        parsed_profile["policy_numbers"] = policy_numbers

    # Account number must not be a policy number.
    account_number = clean(parsed_profile.get("account_number"))
    if account_number and looks_like_policy(account_number):
        parsed_profile["account_number"] = ""

    customer_number = clean(parsed_profile.get("customer_number"))
    if customer_number and looks_like_policy(customer_number):
        parsed_profile["customer_number"] = ""

    # Rebuild policy rows while preserving line/carrier/dates/counts already found.
    if policy_numbers:
        existing_rows = parsed_profile.get("policies") if isinstance(parsed_profile.get("policies"), list) else []
        rebuilt = []

        for policy in policy_numbers:
            existing = None
            for row in existing_rows:
                if isinstance(row, dict) and clean(row.get("policy_number")).upper() == policy:
                    existing = dict(row)
                    break

            if existing is None:
                existing = {"policy_number": policy}

            existing["policy_number"] = policy
            existing["carrier"] = existing.get("carrier") or parsed_profile.get("carrier") or parsed_profile.get("carrier_name") or ""
            existing["writing_carrier"] = existing.get("writing_carrier") or parsed_profile.get("writing_carrier") or parsed_profile.get("carrier_name") or ""
            existing["effective_date"] = existing.get("effective_date") or parsed_profile.get("effective_date") or ""
            existing["expiration_date"] = existing.get("expiration_date") or parsed_profile.get("expiration_date") or ""
            rebuilt.append(existing)

        parsed_profile["policies"] = rebuilt

    # Normalize claim rows so DB save logic sees them as real claims.
    normalized_claims = []

    for claim in parsed_claims:
        if not isinstance(claim, dict):
            continue

        claim = dict(claim)

        claim_number = clean(
            claim.get("claim_number")
            or claim.get("claim #")
            or claim.get("claim_no")
            or claim.get("claim")
            or claim.get("claim_id")
        )

        if not claim_number:
            continue

        paid = money(claim.get("paid") or claim.get("total_paid"))
        reserve = money(claim.get("reserve") or claim.get("total_reserve"))
        incurred = money(
            claim.get("total_incurred")
            or claim.get("incurred")
            or claim.get("total")
            or claim.get("gross_incurred")
        )

        if incurred <= 0 and (paid or reserve):
            incurred = paid + reserve

        claim["claim_number"] = claim_number
        claim["paid"] = paid
        claim["reserve"] = reserve
        claim["total_incurred"] = incurred
        claim["incurred"] = incurred

        claim["date_of_loss"] = clean(
            claim.get("date_of_loss")
            or claim.get("loss_date")
            or claim.get("date of loss")
        )

        claim["date_reported"] = clean(
            claim.get("date_reported")
            or claim.get("reported_date")
            or claim.get("date reported")
        )

        claim["claim_status"] = clean(
            claim.get("claim_status")
            or claim.get("status")
            or claim.get("open_closed")
        )

        claim["status"] = claim["claim_status"]

        claim["line_of_business"] = clean(
            claim.get("line_of_business")
            or claim.get("line")
            or claim.get("coverage")
            or claim.get("lob")
        )

        if not clean(claim.get("policy_number")) and policy_numbers:
            line = claim["line_of_business"].upper()
            if "WC" in line or "WORK" in line:
                claim["policy_number"] = next((p for p in policy_numbers if p.startswith("WC")), policy_numbers[0])
            elif "GL" in line or "GENERAL" in line or "LIAB" in line:
                claim["policy_number"] = next((p for p in policy_numbers if p.startswith(("GL", "CGL", "PL"))), policy_numbers[0])
            else:
                claim["policy_number"] = policy_numbers[0]

        if insured_name:
            claim["business_name"] = claim.get("business_name") or insured_name
            claim["named_insured"] = claim.get("named_insured") or insured_name

        if parsed_profile.get("carrier_name") or parsed_profile.get("writing_carrier"):
            claim["carrier_name"] = claim.get("carrier_name") or parsed_profile.get("carrier_name") or parsed_profile.get("writing_carrier")
            claim["writing_carrier"] = claim.get("writing_carrier") or parsed_profile.get("writing_carrier") or parsed_profile.get("carrier_name")

        normalized_claims.append(claim)

    if normalized_claims:
        parsed_claims = normalized_claims

    return parsed_claims, parsed_profile




# LOSSQ_FORCE_SECTION_CSV_CLAIMS_BEFORE_SAVE_V1
def lossq_force_section_csv_claims_before_save(file_path, parsed_claims=None, parsed_profile=None):
    """
    Universal section CSV extraction that runs immediately after parse_file,
    before the DB save loop.

    This is for files where profile rows appear first, then a CLAIMS DETAIL section.
    It does not hardcode insured, carrier, agency, or file names.
    """
    parsed_claims = parsed_claims if isinstance(parsed_claims, list) else []
    parsed_profile = parsed_profile if isinstance(parsed_profile, dict) else {}

    if not str(file_path or "").lower().endswith(".csv"):
        return parsed_claims, parsed_profile

    try:
        with open(file_path, "r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            rows = list(csv.reader(handle))
    except Exception:
        return parsed_claims, parsed_profile

    if not rows:
        return parsed_claims, parsed_profile

    def clean(value):
        return re.sub(r"\s+", " ", str(value or "").replace("\ufeff", "").strip())

    def norm(value):
        return re.sub(r"[^a-z0-9]+", "_", clean(value).lower()).strip("_")

    def money(value):
        raw = clean(value)
        if not raw:
            return 0.0

        neg = raw.startswith("(") and raw.endswith(")")
        raw = raw.replace("$", "").replace(",", "").replace("(", "").replace(")", "")
        raw = re.sub(r"[^0-9.\-]", "", raw)

        if raw in {"", "-", ".", "-."}:
            return 0.0

        try:
            amount = float(raw)
            return -amount if neg else amount
        except Exception:
            return 0.0

    def split_policy_numbers(value):
        raw = clean(value)
        if not raw:
            return []

        found = []
        for piece in re.split(r"\s*(?:/|,|;|\||\band\b|\+)\s*", raw, flags=re.IGNORECASE):
            piece = clean(piece).upper()
            for match in re.findall(r"\b[A-Z]{1,8}[- ]?\d{2,6}[- ]?[A-Z0-9]{2,12}\b", piece):
                match = clean(match).upper().replace(" ", "-")
                if match and match not in found:
                    found.append(match)

        return found

    def header_index(headers, candidates):
        normalized_headers = [norm(header) for header in headers]
        normalized_candidates = [norm(candidate) for candidate in candidates]

        for index, header in enumerate(normalized_headers):
            if header in normalized_candidates:
                return index

        for index, header in enumerate(normalized_headers):
            for candidate in normalized_candidates:
                if candidate and (candidate in header or header in candidate):
                    return index

        return None

    def value_at(row, index):
        if index is None:
            return ""
        if index < 0 or index >= len(row):
            return ""
        return clean(row[index])

    def line_name(value):
        value = clean(value).upper()

        if value in {"WC", "WORKERS COMP", "WORKERS COMPENSATION"} or "WORK" in value:
            return "Workers Compensation"

        if value in {"GL", "GENERAL LIABILITY"} or "GENERAL" in value:
            return "General Liability"

        if "PROD" in value or "PRODUCT" in value:
            return "Products Liability"

        if "AUTO" in value:
            return "Commercial Auto"

        return clean(value) or "Unknown"

    def choose_policy(line, policy_numbers):
        if not policy_numbers:
            return ""

        upper_line = clean(line).upper()

        if "WC" in upper_line or "WORK" in upper_line:
            return next((p for p in policy_numbers if str(p).upper().startswith("WC")), policy_numbers[0])

        if "GL" in upper_line or "GENERAL" in upper_line:
            return next((p for p in policy_numbers if str(p).upper().startswith(("GL", "CGL"))), policy_numbers[0])

        if "PROD" in upper_line or "PRODUCT" in upper_line or "LIAB" in upper_line:
            return next((p for p in policy_numbers if str(p).upper().startswith(("GL", "CGL", "PL", "PROD"))), policy_numbers[0])

        return policy_numbers[0]

    section_claim_headers = {
        "claims_detail",
        "claim_detail",
        "claim_details",
        "claims",
        "loss_detail",
        "loss_details",
        "claim_listing",
        "claim_list",
    }

    stop_sections = {
        "loss_summary",
        "summary",
        "totals",
        "total",
        "exposure_summary",
        "premium_summary",
        "underwriting_notes",
        "notes",
    }

    labels = {}
    claims_header_index = None

    for index, row in enumerate(rows):
        first = norm(row[0] if row else "")

        if first in section_claim_headers:
            claims_header_index = index + 1
            break

        if len(row) >= 2:
            label = norm(row[0])
            value = clean(row[1])
            if label and value:
                labels[label] = value

    if claims_header_index is None or claims_header_index >= len(rows):
        return parsed_claims, parsed_profile

    def first_label(*names):
        for name in names:
            value = labels.get(norm(name))
            if clean(value):
                return clean(value)
        return ""

    profile = dict(parsed_profile)

    insured_name = first_label(
        "insured name",
        "named insured",
        "insured",
        "applicant",
        "account name",
        "company name",
        "business name",
    )

    if insured_name:
        profile["business_name"] = insured_name
        profile["insured_name"] = insured_name
        profile["named_insured"] = insured_name

    carrier = first_label("carrier", "writing carrier", "insurance carrier")
    if carrier:
        profile["carrier"] = carrier
        profile["carrier_name"] = carrier
        profile["writing_carrier"] = carrier

    producing_agency = first_label(
        "producing agency",
        "agency",
        "agency name",
        "broker",
        "brokerage",
        "producer",
        "producer name",
    )

    if producing_agency:
        profile["producing_agency"] = producing_agency
        profile["agency_name"] = producing_agency
        profile["producer"] = producing_agency

    policy_numbers = split_policy_numbers(first_label("policy number", "policy numbers", "policy no", "policy"))

    if policy_numbers:
        profile["policy_number"] = policy_numbers[0]
        profile["main_policy"] = policy_numbers[0]
        profile["policy_numbers"] = policy_numbers

    period = first_label("policy period", "policy term", "coverage period")
    period_dates = re.findall(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", period)

    if len(period_dates) >= 1:
        profile["effective_date"] = profile.get("effective_date") or period_dates[0]
    if len(period_dates) >= 2:
        profile["expiration_date"] = profile.get("expiration_date") or period_dates[1]

    evaluation_date = first_label("evaluation date", "valuation date", "as of date", "loss run date")
    if evaluation_date:
        profile["evaluation_date"] = evaluation_date

    account_number = first_label("account number", "account no", "customer number", "client number")
    if account_number and (lossq_is_true_account_identifier(account_number) or not split_policy_numbers(account_number)):
        profile["account_number"] = account_number
    else:
        profile["account_number"] = ""

    headers = [clean(value) for value in rows[claims_header_index]]

    claim_i = header_index(headers, ["claim #", "claim number", "claim no", "claim"])
    dol_i = header_index(headers, ["date of loss", "loss date", "dol"])
    reported_i = header_index(headers, ["date reported", "reported date", "date_reported"])
    claimant_i = header_index(headers, ["claimant", "claimant name", "injured worker", "party"])
    line_i = header_index(headers, ["line", "line of business", "coverage", "lob"])
    desc_i = header_index(headers, ["description", "loss description", "cause", "claim description"])
    status_i = header_index(headers, ["status", "claim status", "open closed", "open/closed"])
    incurred_i = header_index(headers, ["total incurred", "incurred", "total"])
    paid_i = header_index(headers, ["paid", "total paid"])
    reserve_i = header_index(headers, ["reserve", "total reserve", "outstanding reserve"])
    subro_i = header_index(headers, ["subrogation", "subro", "recovery"])

    repaired_claims = []

    for row in rows[claims_header_index + 1:]:
        first = norm(row[0] if row else "")

        if first in stop_sections:
            break

        if not any(clean(cell) for cell in row):
            continue

        claim_number = value_at(row, claim_i)
        if not claim_number:
            continue

        raw_line = value_at(row, line_i)
        clean_line = line_name(raw_line)
        paid = money(value_at(row, paid_i))
        reserve = money(value_at(row, reserve_i))
        incurred = money(value_at(row, incurred_i))

        if incurred <= 0 and (paid or reserve):
            incurred = paid + reserve

        policy_number = choose_policy(raw_line, policy_numbers)

        claim = {
            "claim_number": claim_number,
            "policy_number": policy_number,
            "date_of_loss": value_at(row, dol_i),
            "date_reported": value_at(row, reported_i),
            "claimant": value_at(row, claimant_i),
            "line_of_business": clean_line,
            "policy_type": clean_line,
            "coverage": clean_line,
            "description": value_at(row, desc_i),
            "loss_description": value_at(row, desc_i),
            "claim_status": value_at(row, status_i),
            "status": value_at(row, status_i),
            "total_incurred": incurred,
            "incurred": incurred,
            "paid": paid,
            "total_paid": paid,
            "reserve": reserve,
            "total_reserve": reserve,
            "subrogation": value_at(row, subro_i),
            "business_name": insured_name,
            "named_insured": insured_name,
            "carrier_name": carrier,
            "writing_carrier": carrier,
        }

        repaired_claims.append(claim)

    if repaired_claims:
        profile["claims"] = repaired_claims
        profile["parsed_claims"] = repaired_claims

        line_groups = {}
        for claim in repaired_claims:
            policy_number = claim.get("policy_number") or ""
            if not policy_number:
                continue

            if policy_number not in line_groups:
                line_groups[policy_number] = {
                    "policy_number": policy_number,
                    "line_of_business": claim.get("line_of_business") or "Unknown",
                    "policy_type": claim.get("line_of_business") or "Unknown",
                    "carrier": carrier,
                    "writing_carrier": carrier,
                    "effective_date": profile.get("effective_date") or "",
                    "expiration_date": profile.get("expiration_date") or "",
                    "claim_count": 0,
                    "total_incurred": 0.0,
                }

            line_groups[policy_number]["claim_count"] += 1
            line_groups[policy_number]["total_incurred"] += money(claim.get("total_incurred"))

        if line_groups:
            profile["policies"] = list(line_groups.values())

        print("LOSSQ_FORCE_SECTION_CSV_CLAIMS_BEFORE_SAVE:", {"claims": len(repaired_claims), "policies": len(profile.get("policies") or [])})
        return repaired_claims, profile

    return parsed_claims, profile




# LOSSQ_UPLOAD_ROOT_CAUSE_DEBUG_V1
def lossq_debug_upload_snapshot(stage, parsed_claims=None, parsed_profile=None, extra=None):
    try:
        claims = parsed_claims if isinstance(parsed_claims, list) else []
        profile = parsed_profile if isinstance(parsed_profile, dict) else {}

        sample_claims = []
        for claim in claims[:5]:
            if isinstance(claim, dict):
                sample_claims.append({
                    "claim_number": claim.get("claim_number") or claim.get("claim #") or claim.get("claim"),
                    "policy_number": claim.get("policy_number"),
                    "line_of_business": claim.get("line_of_business") or claim.get("line") or claim.get("coverage"),
                    "status": claim.get("claim_status") or claim.get("status"),
                    "paid": claim.get("paid") or claim.get("total_paid"),
                    "reserve": claim.get("reserve") or claim.get("total_reserve"),
                    "total_incurred": claim.get("total_incurred") or claim.get("incurred"),
                    "keys": sorted(list(claim.keys()))[:30],
                })

        print("LOSSQ_UPLOAD_DEBUG_SNAPSHOT:", {
            "stage": stage,
            "claim_count": len(claims),
            "sample_claims": sample_claims,
            "profile": {
                "id": profile.get("id"),
                "business_name": profile.get("business_name"),
                "insured_name": profile.get("insured_name"),
                "named_insured": profile.get("named_insured"),
                "carrier_name": profile.get("carrier_name"),
                "writing_carrier": profile.get("writing_carrier"),
                "producing_agency": profile.get("producing_agency"),
                "agency_name": profile.get("agency_name"),
                "account_number": profile.get("account_number"),
                "customer_number": profile.get("customer_number"),
                "policy_number": profile.get("policy_number"),
                "main_policy": profile.get("main_policy"),
                "policy_numbers": profile.get("policy_numbers"),
                "policies": profile.get("policies"),
            },
            "extra": extra or {},
        })
    except Exception as exc:
        print("LOSSQ_UPLOAD_DEBUG_SNAPSHOT_FAILED:", str(exc)[:500])




# LOSSQ_TRUE_ACCOUNT_IDENTIFIER_HELPER_V1
def lossq_is_true_account_identifier(value):
    text = str(value or "").strip().upper()
    if not text:
        return False

    # Universal account/customer/client identifiers should never be treated as policies.
    return bool(
        re.search(r"\b(ACCT|ACCOUNT|CUST|CUSTOMER|CLIENT)\b", text)
        or re.search(r"[-_ ](ACCT|ACCOUNT|CUST|CUSTOMER|CLIENT)[-_ ]", text)
    )


def lossq_looks_like_policy_but_not_account(value):
    text = str(value or "").strip().upper()
    if not text:
        return False
    if lossq_is_true_account_identifier(text):
        return False
    return lossq_looks_like_policy_but_not_account(text)


async def save_uploaded_files(files, policy_number, db, current_user):
    ensure_claim_timeline_columns(db)
    ensure_claim_detail_columns(db)
    ensure_account_profile_columns(db)
    lossq_beta_upload_usage_guard(db, current_user, len(files or []))

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
            lossq_debug_upload_snapshot(
                "after_parse_file",
                parsed_claims,
                parsed_profile,
                {"filename": safe_upload_filename or safe_filename},
            )
            # LOSSQ_FORCE_SECTION_CSV_CLAIMS_BEFORE_SAVE_CALL_V1
            parsed_claims, parsed_profile = lossq_force_section_csv_claims_before_save(
                file_path,
                parsed_claims,
                parsed_profile,
            )
            lossq_debug_upload_snapshot(
                "after_force_section_csv_claims_before_save",
                parsed_claims,
                parsed_profile,
                {"filename": safe_upload_filename or safe_filename},
            )

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

        # LOSSQ_UNIVERSAL_SECTION_CSV_CLAIMS_PROFILE_REPAIR_CALL_V1
        parsed_claims, parsed_profile = lossq_universal_section_csv_claims_profile_repair(
            file_path,
            parsed_claims,
            parsed_profile,
        )

        # LOSSQ_UNIVERSAL_SECTION_CSV_CLAIMS_PROFILE_REPAIR_CALL_V2
        parsed_claims, parsed_profile = lossq_universal_section_csv_claims_profile_repair_v2(
            file_path,
            parsed_claims,
            parsed_profile,
        )
        lossq_debug_upload_snapshot(
            "after_universal_section_csv_v2",
            parsed_claims,
            parsed_profile,
            {"filename": safe_upload_filename or safe_filename if "safe_upload_filename" in locals() else ""},
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

        # LOSSQ_REAPPLY_DIRECT_EXPOSURE_AFTER_CSV_REPAIRS_V1
        # Re-apply direct CSV/XLSX exposure values after CSV claim/profile repairs so they are not lost.
        direct_exposure_inputs_after_csv_repairs = lossq_extract_exposure_inputs_directly_from_file(file_path)
        if direct_exposure_inputs_after_csv_repairs:
            if not isinstance(parsed_profile, dict):
                parsed_profile = {}
            parsed_profile.update({
                k: v for k, v in direct_exposure_inputs_after_csv_repairs.items()
                if v not in ("", None, [], {})
            })
            parsed_profile["exposure_inputs"] = direct_exposure_inputs_after_csv_repairs
            parsed_profile["exposures"] = direct_exposure_inputs_after_csv_repairs
            print("LOSSQ_DIRECT_EXPOSURE_REAPPLIED_AFTER_CSV_REPAIRS:", direct_exposure_inputs_after_csv_repairs)

        # LOSSQ_UNIVERSAL_PRODUCING_AGENCY_EXTRACTION_V1
        upload_agency_name = lossq_header_agency_from_csv(file_path) or lossq_universal_agency_from_csv(file_path)
        if upload_agency_name:
            print("LOSSQ_AGENCY_SELECTED_FROM_UPLOAD:", upload_agency_name)

        # LOSSQ_CLEAN_PROFILE_POLICY_SCHEDULE_ROWS_V1
        parsed_profile = lossq_clean_profile_policy_schedule_rows(parsed_profile, parsed_claims)

        # LOSSQ_APPLY_LINE_OF_BUSINESS_FROM_POLICY_PREFIX_V1
        parsed_claims, parsed_profile = lossq_apply_line_of_business_from_policy_prefix(parsed_claims, parsed_profile)

        # LOSSQ_UNIVERSAL_CSV_ACCOUNT_EXPOSURE_CLAIM_DETAIL_OVERLAY_V1
        parsed_claims, parsed_profile = lossq_universal_csv_account_exposure_claim_detail_overlay(
            file_path=file_path,
            parsed_claims=parsed_claims,
            parsed_profile=parsed_profile,
        )


        # LOSSQ_FINAL_PROFILE_DATES_FROM_POLICIES_V1
        parsed_profile = lossq_final_profile_dates_from_policies(parsed_profile)
        # LOSSQ_UNIVERSAL_PROFILE_CLAIM_FINAL_NORMALIZER_CALL_V1
        parsed_claims, parsed_profile = lossq_universal_profile_claim_final_normalizer(
            parsed_claims,
            parsed_profile,
        )
        lossq_debug_upload_snapshot(
            "after_final_profile_claim_normalizer",
            parsed_claims,
            parsed_profile,
            {"filename": safe_upload_filename or safe_filename if "safe_upload_filename" in locals() else ""},
        )
        parsed_profile = lossq_universal_profile_identity_policy_cleanup(parsed_profile)
        if upload_agency_name:
            parsed_profile = parsed_profile or {}
            parsed_profile["agency_name"] = upload_agency_name
            parsed_profile["producing_agency"] = upload_agency_name
            parsed_profile["producer"] = upload_agency_name

        file_policy_number = clean_input_policy
        file_account_key_for_claims = ""

        claim_policy_number = ""
        # LOSSQ_UNIVERSAL_CSV_SECTION_OVERLAY_V2
        parsed_claims, parsed_profile = lossq_universal_csv_section_overlay_v2(
            file_path=file_path,
            parsed_claims=parsed_claims,
            parsed_profile=parsed_profile,
        )

        # LOSSQ_BETA_FILTER_AND_PURGE_BEFORE_SAVE_V1
        parsed_claims, lossq_beta_removed_rows = lossq_beta_filter_claim_rows(parsed_claims)

        # LOSSQ_UNIVERSAL_CSV_SECTION_OVERLAY_V2_REAPPLY_AFTER_BETA
        parsed_claims, parsed_profile = lossq_universal_csv_section_overlay_v2(
            file_path=file_path,
            parsed_claims=parsed_claims,
            parsed_profile=parsed_profile,
        )


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

        # LOSSQ_FINAL_CSV_ACCOUNT_AND_MISSING_CLAIMS_V4_BEFORE_SAVE_LOOP
        if str(file_path or "").lower().endswith(".csv"):
            parsed_claims, parsed_profile = lossq_v4_merge_csv_sections_before_save(
                file_path=file_path,
                parsed_claims=parsed_claims,
                parsed_profile=parsed_profile,
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

            parsed_profile = lossq_clean_exposure_limits_field(parsed_profile)

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

        lossq_debug_upload_snapshot(
            "before_all_parsed_claims_extend",
            parsed_claims,
            parsed_profile,
            {"filename": safe_upload_filename or safe_filename if "safe_upload_filename" in locals() else ""},
        )
        # LOSSQ_FINAL_REAPPLY_CSV_OVERLAY_BEFORE_SAVE_V3
        if str(file_path or "").lower().endswith(".csv"):
            try:
                if callable(globals().get("lossq_universal_csv_section_overlay_v2")):
                    parsed_claims, parsed_profile = lossq_universal_csv_section_overlay_v2(
                        file_path=file_path,
                        parsed_claims=parsed_claims,
                        parsed_profile=parsed_profile,
                    )
                parsed_profile = lossq_final_repair_profile_account_and_exposures_v3(parsed_profile)
            except Exception as exc:
                print("LOSSQ_FINAL_REAPPLY_CSV_OVERLAY_BEFORE_SAVE_V3_ERROR", str(exc)[:200])

        # LOSSQ_FINAL_CSV_ACCOUNT_AND_MISSING_CLAIMS_V4_BEFORE_EXTEND
        if str(file_path or "").lower().endswith(".csv"):
            parsed_claims, parsed_profile = lossq_v4_merge_csv_sections_before_save(
                file_path=file_path,
                parsed_claims=parsed_claims,
                parsed_profile=parsed_profile,
            )

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

            # LOSSQ_CLAIMANT_FROM_UPLOAD_ROW_V1
            normalized = lossq_apply_claimant_to_normalized_claim(
                normalized_claim=normalized,
                raw_claim=claim_data,
            )

            normalized.pop("claimant_name", None)

            # LOSSQ_CLAIM_DETAIL_FIELDS_FROM_UPLOAD_ROW_V1
            normalized = lossq_apply_claim_detail_fields_to_normalized_claim(normalized, claim_data)

            normalized.pop("claimant_name", None)
            normalized.pop("jurisdiction", None)
            normalized.pop("state", None)
            normalized.pop("adjuster_examiner", None)

            # LOSSQ_CLAIM_DETAIL_FIELDS_FROM_UPLOAD_ROW_V2
            normalized = lossq_apply_claim_detail_fields_to_normalized_claim_v2(normalized, claim_data)

            # LOSSQ_FINAL_SAVE_CLAIM_DETAIL_REPAIR_V3
            normalized = lossq_final_fix_claim_detail_v3(normalized, claim_data)

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
    # LOSSQ_TRUE_ACCOUNT_NUMBER_FROM_UPLOAD_CSV_V1
    upload_true_account_number = lossq_extract_true_account_number_from_upload_csv(file_path)
    if upload_true_account_number:
        profile_data["account_number"] = upload_true_account_number
        profile_data["customer_number"] = profile_data.get("customer_number") or upload_true_account_number
        profile_account_key = upload_true_account_number


    # LOSSQ_UPLOAD_ACCOUNT_NUMBER_MUST_NOT_BE_POLICY_V1
    def _lossq_upload_value_looks_like_policy(value):
        value = str(value or "").strip().upper()

        # LOSSQ_TRUE_ACCOUNT_NUMBER_LOCAL_POLICY_CHECK_V1
        # Account/customer identifiers like WISC-ACCT-2026 are real account
        # numbers and must not be blanked as policy-like values.
        if lossq_true_account_number_value(value):
            return False

        return lossq_looks_like_policy_but_not_account(value)

    if profile_account_key and not _lossq_upload_value_looks_like_policy(profile_account_key):
        profile_data["account_number"] = profile_data.get("account_number") or profile_account_key

    if _lossq_upload_value_looks_like_policy(profile_data.get("account_number")) and not lossq_true_account_number_value(profile_data.get("account_number")):
        profile_data["account_number"] = ""

    if _lossq_upload_value_looks_like_policy(profile_data.get("customer_number")) and not lossq_true_account_number_value(profile_data.get("customer_number")):
        profile_data["customer_number"] = ""
        profile_data["customer_number"] = (
            profile_data.get("customer_number")
            or profile_data.get("account_number")
            or profile_account_key
        )

    # LOSSQ_TRUE_ACCOUNT_NUMBER_FROM_UPLOAD_CSV_V1_REAPPLY_AFTER_CLEANUP
    upload_true_account_number_after_cleanup = lossq_extract_true_account_number_from_upload_csv(file_path)
    if upload_true_account_number_after_cleanup:
        profile_data["account_number"] = upload_true_account_number_after_cleanup
        profile_data["customer_number"] = profile_data.get("customer_number") or upload_true_account_number_after_cleanup
        profile_account_key = upload_true_account_number_after_cleanup

    # Main saved profile key should be the stable account key.
    # Real policy numbers stay in profile_data["policies"].
    if is_bad_policy_key_for_upload(profile_data.get("policy_number")):
        profile_data["policy_number"] = profile_account_key or primary_claim_policy_number or f"UPLOAD-{upload_session_id}"


    # LOSSQ_DO_NOT_USE_POLICY_AS_ACCOUNT_NUMBER_V2
    def _lossq_upload_policy_like(value):
        value = str(value or "").strip().upper()

        # LOSSQ_TRUE_ACCOUNT_NUMBER_FINAL_POLICY_LIKE_GUARD_V1
        # Account/customer identifiers like WISC-ACCT-2026 are valid account
        # numbers. Do not blank them just because they contain letters, dashes,
        # and digits.
        if lossq_true_account_number_value(value):
            return False

        return lossq_looks_like_policy_but_not_account(value)

    if _lossq_upload_policy_like(profile_data.get("account_number")) and not lossq_true_account_number_value(profile_data.get("account_number")):
        profile_data["account_number"] = ""

    if _lossq_upload_policy_like(profile_data.get("customer_number")) and not lossq_true_account_number_value(profile_data.get("customer_number")):
        profile_data["customer_number"] = ""

    # LOSSQ_TRUE_ACCOUNT_NUMBER_FINAL_REAPPLY_AFTER_LAST_POLICY_CLEANUP_V1
    upload_true_account_number_final_cleanup = lossq_extract_true_account_number_from_upload_csv(file_path)
    if upload_true_account_number_final_cleanup:
        profile_data["account_number"] = upload_true_account_number_final_cleanup
        profile_data["customer_number"] = upload_true_account_number_final_cleanup
        profile_account_key = upload_true_account_number_final_cleanup

    lossq_debug_upload_snapshot(
        "before_profile_upsert",
        all_parsed_claims if "all_parsed_claims" in locals() else [],
        profile_data if "profile_data" in locals() else {},
        {
            "total_saved": total_saved if "total_saved" in locals() else None,
            "total_duplicates_skipped": total_duplicates_skipped if "total_duplicates_skipped" in locals() else None,
        },
    )
    profile_data = derive_exposure_inputs_from_policy_schedule(profile_data)

    # LOSSQ_PROFILE_DATA_EXPOSURE_SAVE_DEBUG_V1
    debug_exposure_payload = {
        key: profile_data.get(key)
        for key in [
            "current_premium",
            "expiring_premium",
            "target_renewal_premium",
            "payroll",
            "revenue",
            "sales",
            "employee_count",
            "vehicle_count",
            "driver_count",
            "property_tiv",
            "coverage_limit",
            "deductible",
            "umbrella_limit",
            "cyber_revenue",
            "experience_mod",
            "exposure_basis",
        ]
        if profile_data.get(key) not in ("", None, [], {})
    }
    if debug_exposure_payload:
        print("LOSSQ_PROFILE_DATA_EXPOSURE_BEFORE_SAVE:", debug_exposure_payload)

    # LOSSQ_CLEAN_EXPOSURE_LIMITS_FIELD_V1
    profile_data = lossq_clean_exposure_limits_field(profile_data)

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
