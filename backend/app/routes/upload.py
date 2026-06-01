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
)
from app.services.excel_parser_service import parse_claims_from_excel
from app.role_utils import require_permission

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
    lower_name = filename.lower()

    if lower_name.endswith(".pdf"):
        text_data = extract_text_from_pdf(file_path)
        claims = parse_claims_from_text(text_data)
        profile = extract_profile_from_text(text_data)
        return claims, profile

    if lower_name.endswith(".csv") or lower_name.endswith(".xlsx"):
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

    formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%m-%d-%Y",
        "%m-%d-%y",
    ]

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
        existing_columns = [
            column["name"] for column in inspector.get_columns("claims")
        ]

        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                db.execute(
                    text(f"ALTER TABLE claims ADD COLUMN {column_name} {column_type}")
                )

        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Claim timeline column check failed: {e}")


def normalize_claim_data(raw: dict, fallback_policy_number: str, current_user: dict):
    extracted_policy_number = clean_profile_value(
        pick(raw, ["policy_number", "policy_no", "policy"], "")
    )

    final_policy_number = extracted_policy_number or fallback_policy_number

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


def extract_profile_data(parsed_claims: list[dict], fallback_policy_number: str, direct_profile: dict | None = None):
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
    policy_number: str = Form(...),
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
    uploaded_files = []
    all_parsed_claims = []
    direct_profile = {}

    for file in files:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        safe_filename = file.filename.replace(" ", "_")
        file_path = os.path.join(UPLOAD_DIR, f"{timestamp}_{safe_filename}")

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        parsed_claims, parsed_profile = parse_file(file_path, file.filename)

        if parsed_profile:
            for key, value in parsed_profile.items():
                if value and not direct_profile.get(key):
                    direct_profile[key] = value

        all_parsed_claims.extend(parsed_claims)

        for claim_data in parsed_claims:
            normalized = normalize_claim_data(
                raw=claim_data,
                fallback_policy_number=policy_number,
                current_user=current_user,
            )

            db.add(Claim(**normalized))

        upload_record = UploadHistory(
            filename=file.filename,
            stored_path=file_path,
            content_type=file.content_type,
            claims_saved=len(parsed_claims),
            uploaded_at=datetime.now().isoformat(),
            uploaded_by_user_id=current_user["user_id"],
            organization_id=current_user["organization_id"],
        )

        db.add(upload_record)

        total_saved += len(parsed_claims)

        uploaded_files.append({
            "filename": file.filename,
            "claims_saved": len(parsed_claims),
            "policy_number": policy_number,
        })

    profile_data = extract_profile_data(
        parsed_claims=all_parsed_claims,
        fallback_policy_number=policy_number,
        direct_profile=direct_profile,
    )

    profile = upsert_account_profile(db, profile_data, current_user)

    db.commit()

    return {
        "message": "Loss run file(s) uploaded successfully",
        "saved_claims": total_saved,
        "policy_number": profile_data.get("policy_number") or policy_number,
        "profile_auto_populated": bool(profile),
        "profile": profile_data,
        "uploaded_files": uploaded_files,
    }