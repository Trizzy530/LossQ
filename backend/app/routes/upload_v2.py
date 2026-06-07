from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.account_profile import AccountProfile
from app.models.claim import Claim
from app.models.upload_history import UploadHistory
from app.role_utils import require_permission
from app.services.audit import record_audit_event
from app.services.lossq_loss_run_pipeline_v2 import parse_loss_run_upload

from app.routes.upload import (
    UPLOAD_DIR,
    clean_profile_value,
    ensure_account_profile_columns,
    ensure_claim_timeline_columns,
    get_db,
    normalize_claim_data,
    serialize_json,
)

router = APIRouter(prefix="/upload", tags=["Upload V2"])


PLACEHOLDER_VALUES = {
    "",
    "business name not set",
    "unnamed business",
    "carrier not set",
    "carrier not detected",
    "writing carrier not set",
    "writing carrier not detected",
    "agency not set",
    "not set",
    "none",
    "null",
    "-",
}


def _clean(value: Any) -> str:
    return clean_profile_value(value)


def _is_placeholder(value: Any) -> bool:
    return _clean(value).lower() in PLACEHOLDER_VALUES


def _first_real_value(*values: Any) -> str:
    for value in values:
        cleaned = _clean(value)
        if cleaned and not _is_placeholder(cleaned):
            return cleaned
    return ""


def _profile_name(profile_data: Dict[str, Any]) -> str:
    return _first_real_value(
        profile_data.get("business_name"),
        profile_data.get("insured"),
        profile_data.get("named_insured"),
        profile_data.get("account_name"),
        profile_data.get("customer_name"),
        profile_data.get("company_name"),
        profile_data.get("named_insured_name"),
    )


def _profile_carrier(profile_data: Dict[str, Any]) -> str:
    return _first_real_value(
        profile_data.get("carrier_name"),
        profile_data.get("carrier"),
        profile_data.get("insurer"),
        profile_data.get("insurance_company"),
        profile_data.get("company"),
    )


def _profile_writing_carrier(profile_data: Dict[str, Any]) -> str:
    return _first_real_value(
        profile_data.get("writing_carrier"),
        profile_data.get("carrier_name"),
        profile_data.get("carrier"),
        profile_data.get("insurer"),
        profile_data.get("insurance_company"),
        profile_data.get("company"),
    )


def _safe_set_if_exists(obj: Any, field: str, value: Any):
    if hasattr(obj, field):
        setattr(obj, field, value)


def _policy_number_from_profile(profile_data: Dict[str, Any]) -> str:
    return _first_real_value(
        profile_data.get("policy_number"),
        profile_data.get("account_number"),
        profile_data.get("customer_number"),
    ).upper()


def force_save_account_profile_v2(
    db: Session,
    *,
    profile_data: Dict[str, Any],
    current_user: Dict[str, Any],
):
    """
    Universal hard-save for V2 profile data.

    This does not hard-code any customer or carrier.
    It uses whatever V2 parsed from the uploaded document and forces every
    duplicate AccountProfile row for the same organization + policy number to
    receive the parsed values.
    """
    policy_number = _policy_number_from_profile(profile_data)
    if not policy_number:
        return None

    business_name = _profile_name(profile_data)
    carrier_name = _profile_carrier(profile_data)
    writing_carrier = _profile_writing_carrier(profile_data)
    agency_name = _first_real_value(profile_data.get("agency_name"))

    matching_profiles = (
        db.query(AccountProfile)
        .filter(AccountProfile.organization_id == current_user["organization_id"])
        .filter(func.upper(AccountProfile.policy_number) == policy_number)
        .all()
    )

    if not matching_profiles:
        profile = AccountProfile(
            organization_id=current_user["organization_id"],
            policy_number=policy_number,
        )
        db.add(profile)
        db.flush()
        matching_profiles = [profile]

    for profile in matching_profiles:
        if business_name:
            profile.business_name = business_name
        elif _is_placeholder(getattr(profile, "business_name", "")):
            profile.business_name = "Business Name Not Set"

        if carrier_name:
            profile.carrier_name = carrier_name
        elif _is_placeholder(getattr(profile, "carrier_name", "")):
            profile.carrier_name = "Carrier Not Detected"

        if agency_name:
            profile.agency_name = agency_name
        elif _is_placeholder(getattr(profile, "agency_name", "")):
            profile.agency_name = "Agency Not Set"

        profile.policy_number = policy_number

        profile.effective_date = (
            _first_real_value(profile_data.get("effective_date"))
            or getattr(profile, "effective_date", None)
            or "Not Set"
        )

        profile.expiration_date = (
            _first_real_value(profile_data.get("expiration_date"))
            or getattr(profile, "expiration_date", None)
            or "Not Set"
        )

        profile.evaluation_date = (
            _first_real_value(profile_data.get("evaluation_date"))
            or getattr(profile, "evaluation_date", None)
            or datetime.now().date().isoformat()
        )

        _safe_set_if_exists(
            profile,
            "writing_carrier",
            writing_carrier
            or carrier_name
            or (
                "Carrier Not Detected"
                if _is_placeholder(getattr(profile, "writing_carrier", ""))
                else getattr(profile, "writing_carrier", "")
            ),
        )

        _safe_set_if_exists(
            profile,
            "account_number",
            _first_real_value(profile_data.get("account_number")) or policy_number,
        )

        _safe_set_if_exists(
            profile,
            "customer_number",
            _first_real_value(
                profile_data.get("customer_number"),
                profile_data.get("account_number"),
            )
            or policy_number,
        )

        _safe_set_if_exists(
            profile,
            "producer_number",
            _first_real_value(profile_data.get("producer_number")),
        )

        _safe_set_if_exists(
            profile,
            "policies",
            serialize_json(profile_data.get("policies") or [], []),
        )

        _safe_set_if_exists(
            profile,
            "validation",
            serialize_json(profile_data.get("validation") or {}, {}),
        )

        _safe_set_if_exists(
            profile,
            "raw_text_preview",
            _clean(profile_data.get("raw_text_preview")),
        )

    # Extra hard SQL-style update. This is intentionally redundant to guarantee
    # old duplicate placeholder rows cannot survive after V2 parsing succeeds.
    update_values: Dict[str, Any] = {
        "policy_number": policy_number,
        "account_number": _first_real_value(profile_data.get("account_number")) or policy_number,
        "customer_number": _first_real_value(
            profile_data.get("customer_number"),
            profile_data.get("account_number"),
        )
        or policy_number,
        "policies": serialize_json(profile_data.get("policies") or [], []),
        "validation": serialize_json(profile_data.get("validation") or {}, {}),
    }

    if business_name:
        update_values["business_name"] = business_name

    if carrier_name:
        update_values["carrier_name"] = carrier_name
    else:
        update_values["carrier_name"] = "Carrier Not Detected"

    if writing_carrier or carrier_name:
        update_values["writing_carrier"] = writing_carrier or carrier_name
    else:
        update_values["writing_carrier"] = "Carrier Not Detected"

    if agency_name:
        update_values["agency_name"] = agency_name
    else:
        update_values["agency_name"] = "Agency Not Set"

    if _first_real_value(profile_data.get("effective_date")):
        update_values["effective_date"] = _first_real_value(profile_data.get("effective_date"))

    if _first_real_value(profile_data.get("expiration_date")):
        update_values["expiration_date"] = _first_real_value(profile_data.get("expiration_date"))

    if _first_real_value(profile_data.get("evaluation_date")):
        update_values["evaluation_date"] = _first_real_value(profile_data.get("evaluation_date"))
    else:
        update_values["evaluation_date"] = datetime.now().date().isoformat()

    try:
        db.query(AccountProfile).filter(
            AccountProfile.organization_id == current_user["organization_id"],
            func.upper(AccountProfile.policy_number) == policy_number,
        ).update(update_values, synchronize_session=False)
    except Exception:
        # If a production DB is missing one optional column, still keep the core
        # object assignment above instead of breaking the upload.
        db.rollback()
        for profile in matching_profiles:
            if business_name:
                profile.business_name = business_name
            profile.carrier_name = carrier_name or "Carrier Not Detected"
            _safe_set_if_exists(profile, "writing_carrier", writing_carrier or carrier_name or "Carrier Not Detected")
        db.flush()

    db.flush()

    saved = (
        db.query(AccountProfile)
        .filter(AccountProfile.organization_id == current_user["organization_id"])
        .filter(func.upper(AccountProfile.policy_number) == policy_number)
        .order_by(AccountProfile.id.desc())
        .first()
    )

    if saved:
        db.refresh(saved)

    return saved


@router.post("/loss-run-v2")
async def upload_loss_run_v2(
    file: UploadFile = File(...),
    policy_number: str = Form(default=""),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("upload")),
):
    return await save_uploaded_files_v2(
        files=[file],
        policy_number=policy_number,
        db=db,
        current_user=current_user,
    )


@router.post("/loss-runs-v2")
async def upload_multiple_loss_runs_v2(
    files: List[UploadFile] = File(...),
    policy_number: str = Form(default=""),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("upload")),
):
    return await save_uploaded_files_v2(
        files=files,
        policy_number=policy_number,
        db=db,
        current_user=current_user,
    )


async def save_uploaded_files_v2(
    files: List[UploadFile],
    policy_number: str,
    db: Session,
    current_user: dict,
):
    ensure_claim_timeline_columns(db)
    ensure_account_profile_columns(db)
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    total_saved = 0
    total_duplicates_skipped = 0
    uploaded_files = []
    all_parsed_claims: List[Dict[str, Any]] = []
    latest_profile_data: Dict[str, Any] = {}
    latest_saved_profile = None

    upload_session_id = datetime.now().strftime("%Y%m%d%H%M%S")
    clean_input_policy = clean_profile_value(policy_number)

    for file in files:
        content = await file.read()

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        safe_filename = (file.filename or "loss_run.pdf").replace(" ", "_")
        file_path = os.path.join(UPLOAD_DIR, f"{timestamp}_{safe_filename}")

        with open(file_path, "wb") as buffer:
            buffer.write(content)

        parsed = parse_loss_run_upload(file.filename or safe_filename, content)

        parsed_claims = (
            parsed.get("claims")
            or parsed.get("parsed_claims")
            or parsed.get("saved_claim_rows")
            or []
        )

        parsed_profile = dict(parsed.get("profile") or {})
        parsed_policies = parsed.get("policies") or parsed_profile.get("policies") or []
        parsed_validation = parsed.get("validation") or parsed_profile.get("validation") or {}

        file_policy_number = (
            clean_input_policy
            or _first_real_value(parsed_profile.get("policy_number"))
            or _first_real_value(parsed.get("policy_number"))
            or _first_real_value(parsed_profile.get("account_number"))
            or _first_real_value(parsed.get("account_number"))
        )

        claim_policy_number = ""
        for claim_data in parsed_claims:
            claim_policy = clean_profile_value(claim_data.get("policy_number"))
            if claim_policy:
                claim_policy_number = claim_policy
                break

        if not file_policy_number and claim_policy_number:
            file_policy_number = claim_policy_number

        if not file_policy_number:
            file_policy_number = f"UPLOAD-{upload_session_id}-{len(uploaded_files) + 1}"

        file_policy_number = clean_profile_value(file_policy_number).upper()

        parsed_profile["policy_number"] = file_policy_number
        parsed_profile["account_number"] = (
            _first_real_value(parsed_profile.get("account_number"))
            or file_policy_number
        )
        parsed_profile["customer_number"] = (
            _first_real_value(parsed_profile.get("customer_number"))
            or parsed_profile["account_number"]
        )

        if parsed_policies:
            parsed_profile["policies"] = parsed_policies

        if parsed_validation:
            parsed_profile["validation"] = parsed_validation

        latest_profile_data = parsed_profile
        latest_saved_profile = force_save_account_profile_v2(
            db,
            profile_data=parsed_profile,
            current_user=current_user,
        )

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
            ).strip().upper()

            normalized["claim_number"] = claim_number
            normalized["policy_number"] = policy_value

            if not claim_number or claim_number == "UNKNOWN":
                print("Skipping claim without valid claim number")
                continue

            existing_claim = (
                db.query(Claim)
                .filter(
                    Claim.organization_id == current_user["organization_id"],
                    Claim.claim_number == claim_number,
                    Claim.policy_number == policy_value,
                )
                .first()
            )

            if existing_claim:
                print(f"Skipping duplicate claim: {claim_number} / {policy_value}")
                file_duplicates += 1
                total_duplicates_skipped += 1
                continue

            db.add(Claim(**normalized))
            file_saved += 1
            total_saved += 1

        db.add(
            UploadHistory(
                filename=file.filename,
                stored_path=file_path,
                content_type=file.content_type,
                claims_saved=file_saved,
                uploaded_at=datetime.now().isoformat(),
                uploaded_by_user_id=current_user["user_id"],
                organization_id=current_user["organization_id"],
            )
        )

        uploaded_files.append(
            {
                "filename": file.filename,
                "claims_saved": file_saved,
                "duplicates_skipped": file_duplicates,
                "policy_number": file_policy_number,
            }
        )

        all_parsed_claims.extend(parsed_claims)

    if latest_profile_data:
        latest_saved_profile = force_save_account_profile_v2(
            db,
            profile_data=latest_profile_data,
            current_user=current_user,
        )

    record_audit_event(
        db,
        current_user=current_user,
        action="loss_run_uploaded_v2",
        resource_type="upload",
        resource_id=latest_profile_data.get("policy_number"),
        details={
            "parser": "lossq_loss_run_pipeline_v2",
            "policy_number": latest_profile_data.get("policy_number"),
            "account_number": latest_profile_data.get("account_number"),
            "business_name": latest_profile_data.get("business_name"),
            "carrier_name": latest_profile_data.get("carrier_name"),
            "writing_carrier": latest_profile_data.get("writing_carrier"),
            "saved_profile_business_name": getattr(latest_saved_profile, "business_name", None),
            "saved_profile_carrier_name": getattr(latest_saved_profile, "carrier_name", None),
            "saved_claims": total_saved,
            "duplicates_skipped": total_duplicates_skipped,
            "profile_auto_populated": bool(latest_saved_profile),
            "policy_count": len(latest_profile_data.get("policies") or []),
            "validation": latest_profile_data.get("validation") or {},
            "uploaded_files": uploaded_files,
        },
    )

    db.commit()

    saved_profile_policy_number = clean_profile_value(
        latest_profile_data.get("policy_number")
    ).upper()

    saved_profile_after_commit = None
    if saved_profile_policy_number:
        saved_profile_after_commit = (
            db.query(AccountProfile)
            .filter(AccountProfile.organization_id == current_user["organization_id"])
            .filter(func.upper(AccountProfile.policy_number) == saved_profile_policy_number)
            .order_by(AccountProfile.id.desc())
            .first()
        )

    return {
        "message": "Loss run file(s) uploaded successfully with V2 parser",
        "v2_database_save_enabled": True,
        "v2_hard_profile_save_enabled": True,
        "v2_direct_account_profile_save": True,
        "v2_business_name_force_overwrite": True,
        "v2_duplicate_profile_update_enabled": True,
        "v2_carrier_fallback_enabled": True,
        "saved_claims": total_saved,
        "duplicates_skipped": total_duplicates_skipped,
        "policy_number": latest_profile_data.get("policy_number"),
        "account_number": latest_profile_data.get("account_number"),
        "profile_auto_populated": bool(saved_profile_after_commit),
        "saved_profile_business_name": getattr(saved_profile_after_commit, "business_name", None),
        "saved_profile_carrier_name": getattr(saved_profile_after_commit, "carrier_name", None),
        "saved_profile_writing_carrier": getattr(saved_profile_after_commit, "writing_carrier", None),
        "saved_profile_policy_number": getattr(saved_profile_after_commit, "policy_number", None),
        "profile": latest_profile_data,
        "policies": latest_profile_data.get("policies") or [],
        "validation": latest_profile_data.get("validation") or {},
        "uploaded_files": uploaded_files,
        "claims": all_parsed_claims,
        "parsed_claims": all_parsed_claims,
        "claim_count": len(all_parsed_claims),
    }
