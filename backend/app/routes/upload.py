from fastapi import APIRouter, UploadFile, File, Depends, Form
from sqlalchemy.orm import Session
from sqlalchemy import text, inspect
import shutil
import os
from datetime import datetime
from typing import List, Any

from app.database import SessionLocal
from app.models.claim import Claim
from app.models.upload_history import UploadHistory
from app.models.account_profile import AccountProfile
from app.services.parser_service import (
    extract_text_from_pdf,
    parse_claims_from_text,
    extract_profile_from_text,
    extract_policies_from_text,
)
from app.services.excel_parser_service import parse_claims_from_excel
from app.role_utils import require_permission
from app.services.audit import record_audit_event

router = APIRouter(prefix="/upload", tags=["Upload"])

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def parse_file(file_path: str, filename: str):
    """
    Parse uploaded files into claims + profile.

    Production behavior:
    - Reads every PDF page.
    - Uses normal text extraction first.
    - Falls back to OCR for scanned/image PDFs.
    - Returns profile, claims, and policy schedule metadata.
    """

    filename_lower = str(filename or "").lower()
    text_data = ""

    if filename_lower.endswith(".pdf"):
        # 1. Try normal text extraction across ALL pages.
        try:
            from pypdf import PdfReader

            reader = PdfReader(file_path)
            page_texts = []
            total_pages = len(reader.pages)

            for page_index, page in enumerate(reader.pages):
                try:
                    extracted = page.extract_text() or ""
                    if extracted.strip():
                        page_texts.append(
                            f"\n\n--- PAGE {page_index + 1} OF {total_pages} ---\n{extracted}"
                        )
                except Exception:
                    continue

            text_data = "\n".join(page_texts).strip()
        except Exception:
            text_data = ""

        # 2. OCR fallback across ALL pages if text extraction fails.
        if len(text_data.strip()) < 100:
            try:
                from pdf2image import convert_from_path
                import pytesseract

                images = convert_from_path(file_path, dpi=250)
                ocr_pages = []

                for page_index, image in enumerate(images):
                    try:
                        page_text = pytesseract.image_to_string(image) or ""
                        ocr_pages.append(
                            f"\n\n--- OCR PAGE {page_index + 1} OF {len(images)} ---\n{page_text}"
                        )
                    except Exception as page_error:
                        ocr_pages.append(
                            f"\n\n--- OCR PAGE {page_index + 1} FAILED ---\n{str(page_error)}"
                        )

                text_data = "\n".join(ocr_pages).strip()
            except Exception as ocr_error:
                text_data = text_data or f"OCR failed: {str(ocr_error)}"

    else:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text_data = f.read()
        except Exception:
            text_data = ""

    claims = parse_claims_from_text(text_data)
    profile = extract_profile_from_text(text_data)

    try:
        policies = extract_policies_from_text(text_data, profile)
    except Exception:
        policies = profile.get("policies") or []

    profile["policies"] = policies
    profile["raw_text_preview"] = text_data[:5000]
    profile["page_parse_note"] = "Parsed full document with all-page PDF extraction and OCR fallback."

    return claims, profile

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
        "agency_name": clean_profile_value(direct_profile.get("agency_name")),
        "policy_number": clean_profile_value(direct_profile.get("policy_number")),
        "effective_date": parse_date(direct_profile.get("effective_date")) or "",
        "expiration_date": parse_date(direct_profile.get("expiration_date")) or "",
        "evaluation_date": parse_date(direct_profile.get("evaluation_date")) or datetime.now().date().isoformat(),
    }

    for item in parsed_claims:
        if not profile["business_name"]:
            profile["business_name"] = clean_profile_value(
                pick(item, ["business_name", "insured_name", "named_insured", "account_name"], "")
            )

        if not profile["carrier_name"]:
            profile["carrier_name"] = clean_profile_value(
                pick(item, ["carrier_name", "insurance_carrier", "carrier"], "")
            )

        if not profile["agency_name"]:
            profile["agency_name"] = clean_profile_value(
                pick(item, ["agency_name", "broker_name", "agency"], "")
            )

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
        profile["policy_number"] = clean_profile_value(fallback_policy_number)

    return profile


def upsert_account_profile(db: Session, profile_data: dict, current_user: dict):
    policy_number = clean_profile_value(profile_data.get("policy_number"))

    if not policy_number:
        return None

    existing = (
        db.query(AccountProfile)
        .filter(AccountProfile.organization_id == current_user["organization_id"])
        .filter(AccountProfile.policy_number == policy_number)
        .first()
    )

    if existing:
        for field, value in profile_data.items():
            cleaned_value = clean_profile_value(value)

            if cleaned_value and hasattr(existing, field):
                setattr(existing, field, cleaned_value)

        return existing

    new_profile = AccountProfile(
        business_name=profile_data.get("business_name") or "Business Name Not Set",
        carrier_name=profile_data.get("carrier_name") or "Carrier Not Set",
        agency_name=profile_data.get("agency_name") or "Agency Not Set",
        policy_number=policy_number,
        effective_date=profile_data.get("effective_date") or "Not Set",
        expiration_date=profile_data.get("expiration_date") or "Not Set",
        evaluation_date=profile_data.get("evaluation_date") or datetime.now().date().isoformat(),
        organization_id=current_user["organization_id"],
    )

    db.add(new_profile)
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


async def save_uploaded_files(files, policy_number, db, current_user):
    ensure_claim_timeline_columns(db)

    total_saved = 0
    total_duplicates_skipped = 0
    uploaded_files = []
    all_parsed_claims = []
    direct_profile = {}

    upload_session_id = datetime.now().strftime("%Y%m%d%H%M%S")
    clean_input_policy = str(policy_number or "").strip()

    for file in files:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        safe_filename = file.filename.replace(" ", "_")
        file_path = os.path.join(UPLOAD_DIR, f"{timestamp}_{safe_filename}")

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        parsed_claims, parsed_profile = parse_file(file_path, file.filename)

        file_policy_number = clean_input_policy

        if parsed_profile:
            parsed_policy = str(parsed_profile.get("policy_number") or "").strip()
            if parsed_policy:
                file_policy_number = parsed_policy

            for key, value in parsed_profile.items():
                if value and not direct_profile.get(key):
                    direct_profile[key] = value

        if not file_policy_number:
            for claim_data in parsed_claims:
                claim_policy = str(claim_data.get("policy_number") or "").strip()
                if claim_policy:
                    file_policy_number = claim_policy
                    break

        if not file_policy_number:
            file_policy_number = f"UPLOAD-{upload_session_id}-{len(uploaded_files) + 1}"

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
            policy_value = str(normalized.get("policy_number") or file_policy_number).strip()

            normalized["claim_number"] = claim_number
            normalized["policy_number"] = policy_value

            duplicate_query = db.query(Claim).filter(
                Claim.organization_id == current_user["organization_id"],
                Claim.claim_number == claim_number,
                Claim.policy_number == policy_value,
            )

            existing_claim = duplicate_query.first()

            if existing_claim:
                print(f"Skipping duplicate claim: {claim_number} / {policy_value}")
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

        uploaded_files.append({
            "filename": file.filename,
            "claims_saved": file_saved,
            "duplicates_skipped": file_duplicates,
            "policy_number": file_policy_number,
        })

    profile_data = extract_profile_data(
        parsed_claims=all_parsed_claims,
        fallback_policy_number=direct_profile.get("policy_number") or clean_input_policy or f"UPLOAD-{upload_session_id}",
        direct_profile=direct_profile,
    )

    if not profile_data.get("policy_number"):
        profile_data["policy_number"] = direct_profile.get("policy_number") or f"UPLOAD-{upload_session_id}"

    profile = upsert_account_profile(db, profile_data, current_user)

    db.commit()

    record_audit_event(
        db,
        current_user=current_user,
        action="loss_run_uploaded",
        resource_type="upload",
        resource_id=profile_data.get("policy_number"),
        details={
            "policy_number": profile_data.get("policy_number"),
            "saved_claims": total_saved,
            "duplicates_skipped": total_duplicates_skipped,
            "profile_auto_populated": bool(profile),
            "uploaded_files": uploaded_files,
        },
    )

    return {
        "message": "Loss run file(s) uploaded successfully",
        "saved_claims": total_saved,
        "duplicates_skipped": total_duplicates_skipped,
        "policy_number": profile_data.get("policy_number"),
        "profile_auto_populated": bool(profile),
        "profile": profile_data,
        "uploaded_files": uploaded_files,
    }