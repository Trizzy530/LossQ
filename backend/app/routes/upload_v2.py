from __future__ import annotations

import os
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

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
    upsert_account_profile,
)

router = APIRouter(prefix="/upload", tags=["Upload V2"])


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


async def save_uploaded_files_v2(files, policy_number, db: Session, current_user: dict):
    ensure_claim_timeline_columns(db)
    ensure_account_profile_columns(db)

    os.makedirs(UPLOAD_DIR, exist_ok=True)

    total_saved = 0
    total_duplicates_skipped = 0
    uploaded_files = []
    all_parsed_claims = []
    direct_profile = {}

    upload_session_id = datetime.now().strftime("%Y%m%d%H%M%S")
    clean_input_policy = str(policy_number or "").strip()

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

        parsed_profile = parsed.get("profile") or {}
        parsed_policies = parsed.get("policies") or parsed_profile.get("policies") or []
        parsed_validation = parsed.get("validation") or parsed_profile.get("validation") or {}

        file_policy_number = clean_input_policy

        claim_policy_number = ""
        for claim_data in parsed_claims:
            claim_policy = clean_profile_value(claim_data.get("policy_number"))
            if claim_policy:
                claim_policy_number = claim_policy
                break

        parsed_policy = clean_profile_value(
            parsed_profile.get("policy_number")
            or parsed.get("policy_number")
        )

        parsed_account = clean_profile_value(
            parsed_profile.get("account_number")
            or parsed_profile.get("customer_number")
            or parsed.get("account_number")
        )

        if parsed_policy:
            file_policy_number = parsed_policy
        elif claim_policy_number:
            file_policy_number = claim_policy_number
        elif parsed_account:
            file_policy_number = parsed_account
        elif not file_policy_number:
            file_policy_number = f"UPLOAD-{upload_session_id}-{len(uploaded_files) + 1}"

        if not parsed_profile.get("policy_number"):
            parsed_profile["policy_number"] = file_policy_number

        if not parsed_profile.get("account_number"):
            parsed_profile["account_number"] = parsed_account or file_policy_number

        if parsed_policies:
            parsed_profile["policies"] = parsed_policies

        if parsed_validation:
            parsed_profile["validation"] = parsed_validation

        for key, value in parsed_profile.items():
            if value and not direct_profile.get(key):
                direct_profile[key] = value

        if not direct_profile.get("policy_number"):
            direct_profile["policy_number"] = file_policy_number

        if not direct_profile.get("account_number"):
            direct_profile["account_number"] = file_policy_number

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

        uploaded_files.append(
            {
                "filename": file.filename,
                "claims_saved": file_saved,
                "duplicates_skipped": file_duplicates,
                "policy_number": file_policy_number,
            }
        )

    profile_data = dict(direct_profile)

    if not profile_data.get("policy_number"):
        profile_data["policy_number"] = (
            profile_data.get("account_number")
            or clean_input_policy
            or f"UPLOAD-{upload_session_id}"
        )

    if not profile_data.get("account_number"):
        profile_data["account_number"] = profile_data.get("policy_number")

    if not profile_data.get("business_name"):
        for claim_data in all_parsed_claims:
            possible_name = clean_profile_value(
                claim_data.get("business_name")
                or claim_data.get("insured")
                or claim_data.get("insured_name")
                or claim_data.get("named_insured")
                or claim_data.get("account_name")
            )
            if possible_name:
                profile_data["business_name"] = possible_name
                break

    if not profile_data.get("carrier_name"):
        profile_data["carrier_name"] = direct_profile.get("carrier_name") or ""

    if not profile_data.get("writing_carrier"):
        profile_data["writing_carrier"] = (
            direct_profile.get("writing_carrier")
            or direct_profile.get("carrier_name")
            or ""
        )

    primary_claim_policy_number = ""
    for claim_data in all_parsed_claims:
        claim_policy_number = clean_profile_value(claim_data.get("policy_number"))
        if claim_policy_number:
            primary_claim_policy_number = claim_policy_number
            break

    profile_policy_number = clean_profile_value(profile_data.get("policy_number"))
    profile_account_number = clean_profile_value(
        profile_data.get("account_number") or profile_data.get("customer_number")
    )

    if primary_claim_policy_number and (
        not profile_policy_number
        or profile_policy_number == profile_account_number
        or profile_policy_number.isdigit()
    ):
        profile_data["policy_number"] = primary_claim_policy_number

    profile = upsert_account_profile(db, profile_data, current_user)

    record_audit_event(
        db,
        current_user=current_user,
        action="loss_run_uploaded_v2",
        resource_type="upload",
        resource_id=profile_data.get("policy_number"),
        details={
            "parser": "lossq_loss_run_pipeline_v2",
            "policy_number": profile_data.get("policy_number"),
            "account_number": profile_data.get("account_number"),
            "business_name": profile_data.get("business_name"),
            "saved_claims": total_saved,
            "duplicates_skipped": total_duplicates_skipped,
            "profile_auto_populated": bool(profile),
            "policy_count": len(profile_data.get("policies") or []),
            "validation": profile_data.get("validation") or {},
            "uploaded_files": uploaded_files,
        },
    )

    db.commit()

    return {
        "message": "Loss run file(s) uploaded successfully with V2 parser",
	"v2_database_save_enabled": True,
        "saved_claims": total_saved,
        "duplicates_skipped": total_duplicates_skipped,
        "policy_number": profile_data.get("policy_number"),
        "account_number": profile_data.get("account_number"),
        "profile_auto_populated": bool(profile),
        "profile": profile_data,
        "policies": profile_data.get("policies") or [],
        "validation": profile_data.get("validation") or {},
        "uploaded_files": uploaded_files,
        "claims": all_parsed_claims,
        "parsed_claims": all_parsed_claims,
        "claim_count": len(all_parsed_claims),
    }