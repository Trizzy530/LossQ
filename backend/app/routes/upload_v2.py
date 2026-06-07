from __future__ import annotations

import os
import re
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
    "carrier",
    "carrier not set",
    "carrier not detected",
    "writing carrier",
    "writing carrier not set",
    "writing carrier not detected",
    "agency not set",
    "policy",
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


def _safe_float(value: Any) -> float:
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


def _money_values_from_text(text: Any) -> List[float]:
    text_value = str(text or "")
    values: List[float] = []

    for raw in re.findall(
        r"\$\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})|[0-9]+(?:\.[0-9]{2}))",
        text_value,
    ):
        try:
            amount = float(raw.replace(",", ""))
            if amount > 0:
                values.append(amount)
        except Exception:
            continue

    return values


def _extract_date_from_text(text: Any, label: str) -> str:
    text_value = str(text or "")
    match = re.search(
        rf"{re.escape(label)}\s*[:\-]\s*([0-9]{{1,2}}/[0-9]{{1,2}}/[0-9]{{2,4}})",
        text_value,
        flags=re.IGNORECASE,
    )
    return match.group(1).strip() if match else ""


def _extract_status_from_text(text: Any) -> str:
    text_value = str(text or "")
    match = re.search(
        r"Status\s+of\s+Loss\s*[:\-]\s*([A-Za-z]+)",
        text_value,
        flags=re.IGNORECASE,
    )

    if match:
        status = match.group(1).strip().title()
        if status.lower() in {"closed", "open", "pending", "reopened"}:
            return status

    if re.search(r"\bClosed\b", text_value, flags=re.IGNORECASE):
        return "Closed"
    if re.search(r"\bOpen\b", text_value, flags=re.IGNORECASE):
        return "Open"

    return ""


def _normalize_line_of_business(value: Any, description: Any) -> str:
    current = _clean(value)
    desc = str(description or "").lower()

    if current and current.lower() not in {"unknown", "not set", "none", "policy"}:
        return current

    if "workers comp" in desc or "employee" in desc:
        return "Workers Comp"

    if "cargo" in desc:
        return "Cargo"

    if "collision" in desc or "vehicle" in desc or "auto" in desc or "truck" in desc:
        return "Commercial Auto"

    if "property damage" in desc or "damaged floor" in desc or "damaged wall" in desc:
        return "General Liability"

    return current or "Unknown"


def _repair_claim_values(claim_data: Dict[str, Any], fallback_policy_number: str) -> Dict[str, Any]:
    repaired = dict(claim_data or {})
    description = repaired.get("description") or repaired.get("loss_description") or ""

    loss_date_from_text = _extract_date_from_text(description, "Loss Date")
    reported_date_from_text = _extract_date_from_text(description, "Loss Report Date")
    status_from_text = _extract_status_from_text(description)

    if loss_date_from_text:
        repaired["loss_date"] = loss_date_from_text
        repaired["date_of_loss"] = loss_date_from_text

    if reported_date_from_text:
        repaired["reported_date"] = reported_date_from_text
        repaired["date_reported"] = reported_date_from_text

    if status_from_text:
        repaired["status"] = status_from_text

    amounts = _money_values_from_text(description)
    max_amount = max(amounts) if amounts else 0.0

    current_total = _safe_float(
        repaired.get("total_incurred")
        or repaired.get("total_amount")
        or repaired.get("incurred")
        or repaired.get("total_net_loss")
    )

    # Repair obvious OCR/table mistakes like $0, $2, or $49 when the claim text
    # contains a much larger total net loss.
    if max_amount > 0 and (current_total <= 0 or current_total < (max_amount * 0.50)):
        repaired["total_incurred"] = max_amount
        repaired["total_amount"] = max_amount
        repaired["total_net_loss"] = max_amount

    paid_amount = _safe_float(repaired.get("paid_amount") or repaired.get("paid"))
    if max_amount > 0 and paid_amount <= 0:
        repaired["paid_amount"] = max_amount
        repaired["paid"] = max_amount

    reserve_amount = _safe_float(
        repaired.get("reserve_amount")
        or repaired.get("reserve")
        or repaired.get("remaining_reserves")
    )
    if reserve_amount <= 0:
        repaired["reserve_amount"] = 0

    repaired["policy_number"] = _clean(repaired.get("policy_number") or fallback_policy_number).upper()
    repaired["line_of_business"] = _normalize_line_of_business(
        repaired.get("line_of_business"),
        description,
    )

    return repaired


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


def _valid_policy_number(value: Any) -> bool:
    policy = _clean(value).upper()
    if not policy or policy in {"POLICY", "POLICY NUMBER", "ACCOUNT", "ACCOUNT NUMBER"}:
        return False
    return bool(re.search(r"[A-Z0-9]", policy)) and len(policy) >= 4


def _build_policy_rollup_from_claims(claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rollup: Dict[str, Dict[str, Any]] = {}

    for claim in claims:
        policy_number = _clean(claim.get("policy_number")).upper()
        if not _valid_policy_number(policy_number):
            continue

        lob = _clean(claim.get("line_of_business")) or "Unknown"
        total = _safe_float(claim.get("total_incurred") or claim.get("total_amount"))

        if policy_number not in rollup:
            rollup[policy_number] = {
                "policy_number": policy_number,
                "policy_type": lob,
                "line_of_business": lob,
                "claim_count": 0,
                "total_incurred": 0.0,
            }

        rollup[policy_number]["claim_count"] += 1
        rollup[policy_number]["total_incurred"] += total

        if rollup[policy_number]["line_of_business"] in {"", "Unknown"} and lob:
            rollup[policy_number]["line_of_business"] = lob
            rollup[policy_number]["policy_type"] = lob

    return list(rollup.values())


def force_save_account_profile_v2(
    db: Session,
    *,
    profile_data: Dict[str, Any],
    current_user: Dict[str, Any],
):
    policy_number = _policy_number_from_profile(profile_data)
    if not _valid_policy_number(policy_number):
        return None

    business_name = _profile_name(profile_data)
    carrier_name = _profile_carrier(profile_data)
    writing_carrier = _profile_writing_carrier(profile_data)
    agency_name = _first_real_value(profile_data.get("agency_name"))

    matching_profiles = (
        db.query(AccountProfile)
        .filter(AccountProfile.organization_id == current_user["organization_id"])
        .filter(func.upper(func.trim(AccountProfile.policy_number)) == policy_number)
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
            profile.carrier_name = "Carrier Not Set"

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
                "Carrier Not Set"
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

        _safe_set_if_exists(profile, "producer_number", _first_real_value(profile_data.get("producer_number")))
        _safe_set_if_exists(profile, "policies", serialize_json(profile_data.get("policies") or [], []))
        _safe_set_if_exists(profile, "validation", serialize_json(profile_data.get("validation") or {}, {}))
        _safe_set_if_exists(profile, "raw_text_preview", _clean(profile_data.get("raw_text_preview")))

    db.flush()

    saved = (
        db.query(AccountProfile)
        .filter(AccountProfile.organization_id == current_user["organization_id"])
        .filter(func.upper(func.trim(AccountProfile.policy_number)) == policy_number)
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
    total_existing_claims_deleted = 0
    policies_replaced_this_upload = set()

    uploaded_files = []
    all_parsed_claims: List[Dict[str, Any]] = []
    all_repaired_claims: List[Dict[str, Any]] = []
    saved_claim_rows: List[Dict[str, Any]] = []
    latest_profile_data: Dict[str, Any] = {}
    latest_saved_profile = None

    upload_session_id = datetime.now().strftime("%Y%m%d%H%M%S")
    clean_input_policy = clean_profile_value(policy_number)

    claim_columns = {column.name for column in Claim.__table__.columns}

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
            if _valid_policy_number(claim_policy):
                claim_policy_number = claim_policy
                break

        if not _valid_policy_number(file_policy_number) and claim_policy_number:
            file_policy_number = claim_policy_number

        if not _valid_policy_number(file_policy_number):
            file_policy_number = f"UPLOAD-{upload_session_id}-{len(uploaded_files) + 1}"

        file_policy_number = clean_profile_value(file_policy_number).upper()

        repaired_claims = [
            _repair_claim_values(claim_data, file_policy_number)
            for claim_data in parsed_claims
        ]

        # Drop obvious header/non-claim rows.
        repaired_claims = [
            claim for claim in repaired_claims
            if _clean(claim.get("claim_number")).upper() not in {"", "UNKNOWN", "CLAIM NUMBER"}
            and _valid_policy_number(claim.get("policy_number"))
        ]

        rollup_from_claims = _build_policy_rollup_from_claims(repaired_claims)

        detected_policy_numbers = {file_policy_number}
        for claim in repaired_claims:
            claim_policy_number = _clean(claim.get("policy_number")).upper()
            if _valid_policy_number(claim_policy_number):
                detected_policy_numbers.add(claim_policy_number)
        for policy_item in rollup_from_claims:
            policy_item_number = _clean(policy_item.get("policy_number")).upper()
            if _valid_policy_number(policy_item_number):
                detected_policy_numbers.add(policy_item_number)

        parsed_profile["policy_number"] = file_policy_number
        parsed_profile["account_number"] = (
            _first_real_value(parsed_profile.get("account_number"))
            or file_policy_number
        )
        parsed_profile["customer_number"] = (
            _first_real_value(parsed_profile.get("customer_number"))
            or parsed_profile["account_number"]
        )

        parsed_profile["policies"] = rollup_from_claims or parsed_policies

        calculated_total = sum(_safe_float(c.get("total_incurred")) for c in repaired_claims)
        parsed_profile["validation"] = parsed_validation or {}
        parsed_profile["validation"]["claim_count"] = len(repaired_claims)
        parsed_profile["validation"]["calculated_total_incurred"] = round(calculated_total, 2)
        parsed_profile["validation"]["policy_count"] = len(parsed_profile["policies"] or [])

        latest_profile_data = parsed_profile
        latest_saved_profile = force_save_account_profile_v2(
            db,
            profile_data=parsed_profile,
            current_user=current_user,
        )

        policies_to_replace = [
            policy_number_item
            for policy_number_item in detected_policy_numbers
            if _valid_policy_number(policy_number_item)
            and policy_number_item not in policies_replaced_this_upload
        ]

        if policies_to_replace:
            existing_claims_deleted = (
                db.query(Claim)
                .filter(
                    Claim.organization_id == current_user["organization_id"],
                    func.upper(func.trim(Claim.policy_number)).in_(policies_to_replace),
                )
                .delete(synchronize_session=False)
            )

            total_existing_claims_deleted += existing_claims_deleted
            policies_replaced_this_upload.update(policies_to_replace)
            db.flush()

        file_saved = 0
        file_duplicates = 0

        for claim_data in repaired_claims:
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

            # Map repaired fields into the actual Claim model columns.
            normalized["date_of_loss"] = (
                claim_data.get("date_of_loss")
                or claim_data.get("loss_date")
                or normalized.get("date_of_loss")
            )
            normalized["date_reported"] = (
                claim_data.get("date_reported")
                or claim_data.get("reported_date")
                or normalized.get("date_reported")
            )
            normalized["status"] = claim_data.get("status") or normalized.get("status") or "Open"
            normalized["line_of_business"] = claim_data.get("line_of_business") or normalized.get("line_of_business")
            normalized["paid_amount"] = _safe_float(claim_data.get("paid_amount") or normalized.get("paid_amount"))
            normalized["reserve_amount"] = _safe_float(claim_data.get("reserve_amount") or normalized.get("reserve_amount"))
            normalized["total_incurred"] = _safe_float(claim_data.get("total_incurred") or normalized.get("total_incurred"))

            if not claim_number or claim_number == "UNKNOWN":
                print("Skipping claim without valid claim number")
                continue

            existing_claim = (
                db.query(Claim)
                .filter(
                    Claim.organization_id == current_user["organization_id"],
                    Claim.claim_number == claim_number,
                    func.upper(func.trim(Claim.policy_number)) == policy_value,
                )
                .first()
            )

            if existing_claim:
                print(f"Skipping duplicate claim: {claim_number} / {policy_value}")
                file_duplicates += 1
                total_duplicates_skipped += 1
                continue

            safe_claim_data = {
                key: value
                for key, value in normalized.items()
                if key in claim_columns
            }

            saved_claim = Claim(**safe_claim_data)
            db.add(saved_claim)
            db.flush()

            saved_claim_rows.append(
                {
                    "id": getattr(saved_claim, "id", None),
                    "claim_number": getattr(saved_claim, "claim_number", claim_number),
                    "policy_number": getattr(saved_claim, "policy_number", policy_value),
                    "line_of_business": getattr(saved_claim, "line_of_business", None),
                    "claim_type": getattr(saved_claim, "claim_type", None),
                    "date_of_loss": getattr(saved_claim, "date_of_loss", None),
                    "date_reported": getattr(saved_claim, "date_reported", None),
                    "status": getattr(saved_claim, "status", None),
                    "description": getattr(saved_claim, "description", None),
                    "paid_amount": getattr(saved_claim, "paid_amount", 0),
                    "reserve_amount": getattr(saved_claim, "reserve_amount", 0),
                    "total_incurred": getattr(saved_claim, "total_incurred", 0),
                    "flag": getattr(saved_claim, "flag", None),
                    "litigation": getattr(saved_claim, "litigation", False),
                }
            )

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
                "existing_claims_deleted": total_existing_claims_deleted,
                "policies_replaced": sorted(list(policies_replaced_this_upload)),
                "policy_number": file_policy_number,
            }
        )

        all_parsed_claims.extend(parsed_claims)
        all_repaired_claims.extend(repaired_claims)

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
            "existing_claims_deleted": total_existing_claims_deleted,
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
            .filter(func.upper(func.trim(AccountProfile.policy_number)) == saved_profile_policy_number)
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
        "v2_replace_old_policy_claims": True,
        "v2_claim_money_date_status_repair": True,
        "v2_safe_claim_field_filter": True,
        "v2_claim_model_column_mapping": True,
        "v2_saved_claim_rows_with_ids": True,
        "saved_claims": total_saved,
        "existing_claims_deleted": total_existing_claims_deleted,
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
        "claims": saved_claim_rows or all_repaired_claims,
        "saved_claim_rows": saved_claim_rows,
        "parsed_claims": all_repaired_claims,
        "raw_parsed_claims": all_parsed_claims,
        "claim_count": len(all_repaired_claims),
    }
