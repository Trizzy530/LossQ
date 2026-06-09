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
from app.services.document_intelligence.parser_cleanup import cleanup_loss_run_extraction
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

FAKE_CLAIM_VALUES = {
    "",
    "UNKNOWN",
    "CLAIM NUMBER",
    "CLAIM-NUMBER",
    "CLAIM NO",
    "CLAIM-NO",
    "LOSS RUN",
    "LOSS-RUN",
    "AUTO-LIABILITY",
    "AUTO LIABILITY",
    "GENERAL-LIABILITY",
    "GENERAL LIABILITY",
    "WORKERS-COMP",
    "WORKERS COMP",
    "WORKERS-COMPENSATION",
    "WORKERS COMPENSATION",
    "MOTOR-TRUCK-CARGO",
    "MOTOR TRUCK CARGO",
    "CARGO",
    "GL-GATE",
    "AL-GATE",
    "WC-GATE",
    "CG-GATE",
}

BAD_POLICY_VALUES = {
    "",
    "POLICY",
    "POLICY NUMBER",
    "ACCOUNT",
    "ACCOUNT NUMBER",
    "MUTUAL-INSURANCE",
    "GENERAL-LIABILITY",
    "AUTO-LIABILITY",
    "WORKERS-COMP",
    "WORKERS-COMPENSATION",
    "MOTOR-TRUCK-CARGO",
    "CARGO",
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


def _policy_item_number(policy_item: Any) -> str:
    if isinstance(policy_item, dict):
        return _clean(
            policy_item.get("policy_number")
            or policy_item.get("policyNumber")
            or policy_item.get("account_number")
            or policy_item.get("accountNumber")
        ).upper()

    return _clean(policy_item).upper()


def _looks_like_fake_policy_fragment(policy_number: Any) -> bool:
    policy = _clean(policy_number).upper()

    if not policy:
        return True

    fake_tokens = {
        "MUTU-AL",
        "PORT-AL",
        "TOT-AL",
        "GENER-AL",
        "ACTU-AL",
        "MANU-AL",
        "DETAIL-AL",
        "NORM-AL",
        "PARTI-AL",
        "MUTUAL-INSURANCE",
        "GENERAL-LIABILITY",
        "AUTO-LIABILITY",
        "WORKERS-COMP",
        "MOTOR-TRUCK-CARGO",
        "TOTAL-INCURRED",
        "PARTIAL-EXPORT",
        "PORTAL-EXPORT",
    }

    if any(token in policy for token in fake_tokens):
        return True

    if not re.search(r"\d", policy):
        return True

    return False


def _valid_policy_number(value: Any) -> bool:
    policy = _clean(value).upper()

    if not policy or policy in BAD_POLICY_VALUES:
        return False
    if policy.startswith("UPLOAD-"):
        return False
    if policy in FAKE_CLAIM_VALUES:
        return False
    if _looks_like_fake_policy_fragment(policy):
        return False

    return bool(re.search(r"[A-Z0-9]", policy)) and len(policy) >= 4


def _policy_by_claim_prefix(claim_number: Any, policies: List[Dict[str, Any]]) -> str:
    claim = _clean(claim_number).upper()

    if not claim or not isinstance(policies, list):
        return ""

    for policy in policies:
        policy_number = _policy_item_number(policy)
        policy_upper = policy_number.upper()

if claim.startswith("AL") and ("-AL-" in policy_upper or "-CA-" in policy_upper):
            return policy_number
        if claim.startswith("GL") and "-GL-" in policy_upper:
            return policy_number
        if claim.startswith("WC") and "-WC-" in policy_upper:
            return policy_number
        if claim.startswith(("CG", "MT", "CARGO")) and "-CG-" in policy_upper:
            return policy_number

    return ""


def _claim_number_looks_real(value: Any) -> bool:
    claim_number = _clean(value).upper()

    if not claim_number or claim_number in FAKE_CLAIM_VALUES:
        return False

    if claim_number in BAD_POLICY_VALUES:
        return False

    if not re.search(r"\d", claim_number):
        return False

    if re.match(r"^[A-Z]{2,6}-(AL|GL|WC|CG)-[A-Z0-9]+-\d{1,4}$", claim_number):
        return False

    return True


def _claim_has_money(claim: Dict[str, Any]) -> bool:
    return (
        _safe_float(claim.get("total_incurred") or claim.get("total_amount") or claim.get("incurred")) > 0
        or _safe_float(claim.get("paid_amount") or claim.get("paid")) > 0
        or _safe_float(claim.get("reserve_amount") or claim.get("reserve")) > 0
    )


def _claim_debug_summary(label: str, claims: Any) -> Dict[str, Any]:
    if not isinstance(claims, list):
        return {
            f"{label}_count": 0,
            f"{label}_sample": [],
        }

    sample = []
    for claim in claims[:10]:
        if isinstance(claim, dict):
            sample.append(
                {
                    "claim_number": claim.get("claim_number") or claim.get("claimNumber"),
                    "policy_number": claim.get("policy_number") or claim.get("policyNumber"),
                    "paid_amount": claim.get("paid_amount") or claim.get("paid"),
                    "reserve_amount": claim.get("reserve_amount") or claim.get("reserve"),
                    "total_incurred": claim.get("total_incurred") or claim.get("total_amount") or claim.get("incurred"),
                    "line_of_business": claim.get("line_of_business"),
                    "status": claim.get("status"),
                }
            )

    return {
        f"{label}_count": len(claims),
        f"{label}_sample": sample,
    }


def _filtered_out_claim_debug_summary(label: str, claims: Any) -> Dict[str, Any]:
    if not isinstance(claims, list):
        return {
            f"{label}_count": 0,
            f"{label}_sample": [],
        }

    sample = []
    for claim in claims[:15]:
        if isinstance(claim, dict):
            sample.append(
                {
                    "claim_number": claim.get("claim_number"),
                    "policy_number": claim.get("policy_number"),
                    "total_incurred": claim.get("total_incurred"),
                    "paid_amount": claim.get("paid_amount"),
                    "reserve_amount": claim.get("reserve_amount"),
                    "claim_number_looks_real": _claim_number_looks_real(claim.get("claim_number")),
                    "policy_number_valid": _valid_policy_number(claim.get("policy_number")),
                    "claim_has_money": _claim_has_money(claim),
                    "line_of_business": claim.get("line_of_business"),
                    "status": claim.get("status"),
                }
            )

    return {
        f"{label}_count": len(claims),
        f"{label}_sample": sample,
    }


def _repair_claim_values(
    claim_data: Dict[str, Any],
    fallback_policy_number: str,
    parsed_policies: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
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

    mapped_policy_number = _policy_by_claim_prefix(
        repaired.get("claim_number") or repaired.get("claimNumber"),
        parsed_policies or [],
    )

    repaired["policy_number"] = _clean(
        mapped_policy_number
        or repaired.get("policy_number")
        or fallback_policy_number
    ).upper()

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


def _filter_policy_schedule_items(policies: Any) -> List[Dict[str, Any]]:
    if not isinstance(policies, list):
        return []

    cleaned: List[Dict[str, Any]] = []
    seen = set()

    for item in policies:
        if not isinstance(item, dict):
            continue

        policy_number = _policy_item_number(item)

        if not _valid_policy_number(policy_number):
            continue

        if _looks_like_fake_policy_fragment(policy_number):
            continue

        if policy_number in seen:
            continue

        row = dict(item)
        row["policy_number"] = policy_number
        cleaned.append(row)
        seen.add(policy_number)

    return cleaned


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




def _fallback_policy_item_number(policy_item: Any) -> str:
    if isinstance(policy_item, dict):
        return _clean(
            policy_item.get("policy_number")
            or policy_item.get("policyNumber")
            or policy_item.get("account_number")
            or policy_item.get("accountNumber")
        ).upper()

    return _clean(policy_item).upper()


def _fallback_extract_next_line_label(raw_text: Any, label: str) -> str:
    lines = [_clean(line) for line in str(raw_text or "").replace("\r", "\n").splitlines()]
    label_lower = label.lower().strip()

    for index, line in enumerate(lines):
        if line.lower().strip() == label_lower and index + 1 < len(lines):
            return _clean(lines[index + 1])

        if line.lower().startswith(label_lower + ":"):
            return _clean(line.split(":", 1)[1])

    return ""


def _fallback_lob_from_policy(policy_number: Any) -> str:
    policy = _clean(policy_number).upper()

    if "-AL-" in policy:
        return "Auto Liability"
    if "-GL-" in policy:
        return "General Liability"
    if "-WC-" in policy:
        return "Workers Comp"
    if "-CG-" in policy:
        return "Motor Truck Cargo"

    return "Unknown"


def _fallback_extract_policies_from_raw_text(raw_text: Any) -> List[Dict[str, Any]]:
    lines = [_clean(line) for line in str(raw_text or "").replace("\r", "\n").splitlines()]
    policies: List[Dict[str, Any]] = []
    seen = set()

    policy_re = re.compile(r"^[A-Z]{2,6}-(?:AL|GL|WC|CG)-[A-Z0-9]+-\d{1,4}$", re.IGNORECASE)

    for index, line in enumerate(lines):
        policy_number = _clean(line).upper()

        if not policy_re.fullmatch(policy_number):
            continue

        if policy_number in seen:
            continue

        lob = _fallback_lob_from_policy(policy_number)

        nearby = lines[max(0, index - 6):min(len(lines), index + 8)]
        dates = [
            item for item in nearby
            if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2}", item)
        ]

        policy = {
            "policy_number": policy_number,
            "line_of_business": lob,
            "policy_type": lob,
        }

        if len(dates) >= 1:
            policy["effective_date"] = dates[0]
        if len(dates) >= 2:
            policy["expiration_date"] = dates[1]

        policies.append(policy)
        seen.add(policy_number)

    return policies


def _fallback_money(value: Any) -> float:
    text_value = _clean(value)
    match = re.search(r"\$?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})|\d+(?:\.\d{2}))", text_value)

    if not match:
        return 0.0

    return _safe_float(match.group(1))


def _fallback_is_money_line(value: Any) -> bool:
    return bool(
        re.fullmatch(
            r"\$?\s*\d{1,3}(?:,\d{3})*(?:\.\d{2})|\$?\s*\d+(?:\.\d{2})",
            _clean(value),
        )
    )


def _fallback_is_date_or_dash(value: Any) -> bool:
    return bool(
        re.fullmatch(
            r"\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2}|-",
            _clean(value),
        )
    )


def _fallback_extract_claims_from_raw_text(raw_text: Any, policies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    lines = [_clean(line) for line in str(raw_text or "").replace("\r", "\n").splitlines()]
    lines = [line for line in lines if line]

    valid_policies = []
    for policy in policies or []:
        policy_number = _fallback_policy_item_number(policy)
        if _valid_policy_number(policy_number):
            valid_policies.append(policy_number)

    if not valid_policies:
        return []

    claim_re = re.compile(r"^(?:AL|GL|WC|CG|MT|CARGO)-[A-Z0-9-]+$", re.IGNORECASE)

    claims: List[Dict[str, Any]] = []
    seen = set()

    for index, line in enumerate(lines):
        policy_number = _clean(line).upper()

        if policy_number not in valid_policies:
            continue

        if index + 8 >= len(lines):
            continue

        claim_number = _clean(lines[index + 1]).upper()

        if not claim_re.fullmatch(claim_number):
            continue

        if not re.search(r"\d", claim_number):
            continue

        if claim_number in seen:
            continue

        block = lines[index:index + 18]

        money_indexes = []
        for offset, item in enumerate(block):
            if _fallback_is_money_line(item):
                money_indexes.append(offset)

        if len(money_indexes) < 3:
            continue

        paid_index = money_indexes[0]
        reserve_index = money_indexes[1]
        total_index = money_indexes[2]

        paid = _fallback_money(block[paid_index])
        reserve = _fallback_money(block[reserve_index])
        total = _fallback_money(block[total_index])

        if paid <= 0 and reserve <= 0 and total <= 0:
            continue

        date_values = [
            item for item in block[2:paid_index]
            if _fallback_is_date_or_dash(item)
        ]

        status = ""
        description_parts = []

        for item in block[2:paid_index]:
            clean_item = _clean(item)
            lower_item = clean_item.lower()

            if lower_item in {"open", "closed", "pending", "reopened"}:
                status = clean_item.title()
                continue

            if _fallback_is_date_or_dash(clean_item):
                continue

            if clean_item:
                description_parts.append(clean_item)

        if not status:
            status = "Open" if reserve > 0 else "Closed"

        lob = _fallback_lob_from_policy(policy_number)
        description = _clean(" ".join(description_parts))

        claim = {
            "claim_number": claim_number,
            "policy_number": policy_number,
            "line_of_business": lob,
            "claim_type": lob,
            "date_of_loss": date_values[0] if len(date_values) >= 1 and date_values[0] != "-" else "",
            "loss_date": date_values[0] if len(date_values) >= 1 and date_values[0] != "-" else "",
            "date_reported": date_values[1] if len(date_values) >= 2 and date_values[1] != "-" else "",
            "reported_date": date_values[1] if len(date_values) >= 2 and date_values[1] != "-" else "",
            "closed_date": date_values[2] if len(date_values) >= 3 and date_values[2] != "-" else "",
            "status": status,
            "description": description,
            "loss_description": description,
            "paid_amount": paid,
            "paid": paid,
            "reserve_amount": reserve,
            "reserve": reserve,
            "total_incurred": total,
            "total_amount": total,
            "total_net_loss": total,
        }

        claims.append(claim)
        seen.add(claim_number)

    return claims




def _fallback_extract_full_text_from_content(content: bytes | None) -> str:
    if not content:
        return ""

    try:
        from io import BytesIO
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(content))
        parts = []

        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                parts.append(page_text)

        return "\n".join(parts).strip()
    except Exception:
        return ""


def _fallback_policy_lob_from_policy_number(policy_number: Any) -> str:
    policy = _clean(policy_number).upper()

    if "-AL-" in policy:
        return "Auto Liability"
    if "-GL-" in policy:
        return "General Liability"
    if "-WC-" in policy:
        return "Workers Comp"
    if "-CG-" in policy:
        return "Motor Truck Cargo"

    return "Unknown"


def _fallback_enrich_policy_schedule(raw_text: Any, policies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not policies:
        return []

    lines = [_clean(line) for line in str(raw_text or "").replace("\r", "\n").splitlines()]
    lines = [line for line in lines if line]

    enriched: List[Dict[str, Any]] = []

    for policy in policies:
        if not isinstance(policy, dict):
            continue

        item = dict(policy)
        policy_number = _fallback_policy_item_number(item)

        if not policy_number:
            continue

        inferred_lob = _fallback_policy_lob_from_policy_number(policy_number)

        current_lob = _clean(
            item.get("line_of_business")
            or item.get("policy_type")
            or item.get("coverage")
            or item.get("lob")
        )

        if not current_lob or current_lob.lower() == "unknown":
            item["line_of_business"] = inferred_lob
            item["policy_type"] = inferred_lob
            item["coverage"] = inferred_lob
            item["lob"] = inferred_lob

        effective = _clean(item.get("effective_date") or item.get("effective"))
        expiration = _clean(item.get("expiration_date") or item.get("expiration"))

        for index, line in enumerate(lines):
            if _clean(line).upper() != policy_number:
                continue

            nearby = lines[max(0, index - 8):min(len(lines), index + 12)]
            dates = [
                value for value in nearby
                if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2}", value)
            ]

            if not effective and len(dates) >= 1:
                effective = dates[0]

            if not expiration and len(dates) >= 2:
                expiration = dates[1]

            break

        if effective:
            item["effective_date"] = effective
            item["effective"] = effective

        if expiration:
            item["expiration_date"] = expiration
            item["expiration"] = expiration

        item["policy_number"] = policy_number
        enriched.append(item)

    return enriched



def _apply_raw_text_fallback_if_needed(parsed: Dict[str, Any], content: bytes | None = None) -> Dict[str, Any]:
    if not isinstance(parsed, dict):
        return parsed

    profile = dict(parsed.get("profile") or {})

    full_content_text = _fallback_extract_full_text_from_content(content)

    raw_text = (
        full_content_text
        or parsed.get("raw_text")
        or parsed.get("text")
        or parsed.get("extracted_text")
        or profile.get("raw_text")
        or profile.get("text")
        or profile.get("extracted_text")
        or parsed.get("raw_text_preview")
        or profile.get("raw_text_preview")
        or ""
    )

    if not raw_text:
        return parsed

    existing_claims = parsed.get("claims") or parsed.get("parsed_claims") or []
    existing_policies = parsed.get("policies") or profile.get("policies") or []

    fallback_business = _fallback_extract_next_line_label(raw_text, "Named Insured")
    fallback_carrier = _fallback_extract_next_line_label(raw_text, "Writing Carrier")
    fallback_policies = _fallback_extract_policies_from_raw_text(raw_text)

    if fallback_policies and len(fallback_policies) > len(existing_policies):
        fallback_policies = _fallback_enrich_policy_schedule(raw_text, fallback_policies)
        parsed["policies"] = fallback_policies
        profile["policies"] = fallback_policies
        parsed["policy_count"] = len(fallback_policies)

        current_policy = _clean(parsed.get("policy_number")).upper()
        if not _valid_policy_number(current_policy):
            parsed["policy_number"] = fallback_policies[0]["policy_number"]
            profile["policy_number"] = fallback_policies[0]["policy_number"]

    elif existing_policies:
        enriched_existing_policies = _fallback_enrich_policy_schedule(raw_text, existing_policies)
        if enriched_existing_policies:
            parsed["policies"] = enriched_existing_policies
            profile["policies"] = enriched_existing_policies
            parsed["policy_count"] = len(enriched_existing_policies)

    policies_for_claims = parsed.get("policies") or profile.get("policies") or fallback_policies
    fallback_claims = _fallback_extract_claims_from_raw_text(raw_text, policies_for_claims)

    if fallback_business and not _first_real_value(parsed.get("business_name"), profile.get("business_name")):
        parsed["business_name"] = fallback_business
        parsed["named_insured"] = fallback_business
        profile["business_name"] = fallback_business
        profile["named_insured"] = fallback_business

    if fallback_carrier and not _first_real_value(parsed.get("carrier_name"), profile.get("carrier_name")):
        parsed["carrier_name"] = fallback_carrier
        parsed["writing_carrier"] = fallback_carrier
        profile["carrier_name"] = fallback_carrier
        profile["writing_carrier"] = fallback_carrier

    if fallback_claims and len(fallback_claims) > len(existing_claims):
        parsed["claims"] = fallback_claims
        parsed["parsed_claims"] = fallback_claims
        parsed["claim_count"] = len(fallback_claims)
        parsed["total_incurred"] = round(
            sum(_safe_float(claim.get("total_incurred")) for claim in fallback_claims),
            2,
        )

    parsed["profile"] = profile
    return parsed



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
    all_filtered_out_claims: List[Dict[str, Any]] = []
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
        parsed = cleanup_loss_run_extraction(
            parsed,
            filename=(file.filename or safe_filename),
            content=content,
        )
        parsed = _apply_raw_text_fallback_if_needed(parsed, content=content)

        parsed_claims = (
            parsed.get("claims")
            or parsed.get("parsed_claims")
            or parsed.get("saved_claim_rows")
            or []
        )

        parsed_profile = dict(parsed.get("profile") or {})
        parsed_policies = parsed.get("policies") or parsed_profile.get("policies") or []
        parsed_policies = _filter_policy_schedule_items(parsed_policies)
        parsed_validation = parsed.get("validation") or parsed_profile.get("validation") or {}

        schedule_policy_number = ""
        for policy_item in parsed_policies:
            policy_item_number = _policy_item_number(policy_item)
            if _valid_policy_number(policy_item_number):
                schedule_policy_number = policy_item_number
                break

        file_policy_number = (
            clean_input_policy
            or schedule_policy_number
            or _first_real_value(parsed_profile.get("policy_number"))
            or _first_real_value(parsed.get("policy_number"))
            or _first_real_value(parsed_profile.get("account_number"))
            or _first_real_value(parsed.get("account_number"))
            or _first_real_value(parsed_profile.get("customer_number"))
            or _first_real_value(parsed.get("customer_number"))
        )

        claim_policy_number = ""
        for claim_data in parsed_claims:
            claim_policy = clean_profile_value(claim_data.get("policy_number"))
            if _valid_policy_number(claim_policy):
                claim_policy_number = claim_policy
                break

        if not _valid_policy_number(file_policy_number) and claim_policy_number:
            file_policy_number = claim_policy_number

        unresolved_policy_fallback = (
            _clean(file_policy_number).upper()
            if _valid_policy_number(file_policy_number)
            else ""
        )

        repaired_claims = [
            _repair_claim_values(claim_data, unresolved_policy_fallback, parsed_policies)
            for claim_data in parsed_claims
        ]

        filtered_repaired_claims: List[Dict[str, Any]] = []
        filtered_out_claims: List[Dict[str, Any]] = []

        for claim in repaired_claims:
            if (
                _claim_number_looks_real(claim.get("claim_number"))
                and _valid_policy_number(claim.get("policy_number"))
                and _claim_has_money(claim)
            ):
                filtered_repaired_claims.append(claim)
            else:
                filtered_out_claims.append(claim)

        repaired_claims = filtered_repaired_claims
        all_filtered_out_claims.extend(filtered_out_claims)

        rollup_from_claims = _filter_policy_schedule_items(
            _build_policy_rollup_from_claims(repaired_claims)
        )

        if not _valid_policy_number(file_policy_number):
            for claim in repaired_claims:
                candidate = _clean(claim.get("policy_number")).upper()
                if _valid_policy_number(candidate):
                    file_policy_number = candidate
                    break

        if not _valid_policy_number(file_policy_number):
            for policy_item in rollup_from_claims:
                candidate = _clean(policy_item.get("policy_number")).upper()
                if _valid_policy_number(candidate):
                    file_policy_number = candidate
                    break

        can_persist_policy = _valid_policy_number(file_policy_number)

        debug_policy_number = _clean(file_policy_number).upper()
        if not can_persist_policy:
            debug_policy_number = f"UPLOAD-{upload_session_id}-{len(uploaded_files) + 1}"

        detected_policy_numbers = set()
        if can_persist_policy:
            detected_policy_numbers.add(_clean(file_policy_number).upper())

        for claim in repaired_claims:
            claim_policy_number = _clean(claim.get("policy_number")).upper()
            if _valid_policy_number(claim_policy_number):
                detected_policy_numbers.add(claim_policy_number)

        for policy_item in rollup_from_claims:
            policy_item_number = _clean(policy_item.get("policy_number")).upper()
            if _valid_policy_number(policy_item_number):
                detected_policy_numbers.add(policy_item_number)

        parsed_profile["policy_number"] = _clean(file_policy_number).upper() if can_persist_policy else ""
        parsed_profile["account_number"] = (
            _first_real_value(parsed_profile.get("account_number"))
            or (_clean(file_policy_number).upper() if can_persist_policy else "")
        )
        parsed_profile["customer_number"] = (
            _first_real_value(parsed_profile.get("customer_number"))
            or parsed_profile["account_number"]
        )
        parsed_profile["policies"] = parsed_policies or rollup_from_claims

        calculated_total = sum(_safe_float(c.get("total_incurred")) for c in repaired_claims)
        parsed_profile["validation"] = parsed_validation or {}
        parsed_profile["validation"]["claim_count"] = len(repaired_claims)
        parsed_profile["validation"]["calculated_total_incurred"] = round(calculated_total, 2)
        parsed_profile["validation"]["policy_count"] = len(parsed_profile["policies"] or [])
        parsed_profile["validation"]["can_persist_policy"] = can_persist_policy
        parsed_profile["validation"]["debug_policy_number"] = debug_policy_number

        latest_profile_data = parsed_profile
        latest_saved_profile = None

        if can_persist_policy:
            latest_saved_profile = force_save_account_profile_v2(
                db,
                profile_data=parsed_profile,
                current_user=current_user,
            )

        file_existing_claims_deleted = 0
        policies_to_replace = [
            policy_number_item
            for policy_number_item in detected_policy_numbers
            if _valid_policy_number(policy_number_item)
            and policy_number_item not in policies_replaced_this_upload
        ]

        if policies_to_replace and len(repaired_claims) > 0:
            existing_claims_deleted = (
                db.query(Claim)
                .filter(
                    Claim.organization_id == current_user["organization_id"],
                    func.upper(func.trim(Claim.policy_number)).in_(policies_to_replace),
                )
                .delete(synchronize_session=False)
            )

            file_existing_claims_deleted = existing_claims_deleted
            total_existing_claims_deleted += existing_claims_deleted
            policies_replaced_this_upload.update(policies_to_replace)
            db.flush()

        file_saved = 0
        file_duplicates = 0

        for claim_data in repaired_claims:
            normalized = normalize_claim_data(
                raw=claim_data,
                fallback_policy_number=_clean(file_policy_number).upper() if can_persist_policy else "",
                current_user=current_user,
            )

            claim_number = str(normalized.get("claim_number") or "").strip().upper()
            policy_value = str(
                normalized.get("policy_number")
                or claim_data.get("policy_number")
                or (_clean(file_policy_number).upper() if can_persist_policy else "")
            ).strip().upper()

            normalized["claim_number"] = claim_number
            normalized["policy_number"] = policy_value

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
                continue

            if not _claim_number_looks_real(claim_number):
                continue

            if not _valid_policy_number(policy_value):
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
                file_duplicates += 1
                total_duplicates_skipped += 1
                continue

            safe_claim_data = {
                key: value
                for key, value in normalized.items()
                if key in claim_columns
            }

            safe_claim_data["organization_id"] = current_user["organization_id"]
            safe_claim_data["claim_number"] = claim_number
            safe_claim_data["policy_number"] = policy_value

            saved_claim = Claim(**safe_claim_data)
            db.add(saved_claim)
            db.flush()
            db.refresh(saved_claim)

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

        upload_history_payload = {
            "filename": file.filename or safe_filename,
            "organization_id": current_user["organization_id"],
        }

        if hasattr(UploadHistory, "stored_path"):
            upload_history_payload["stored_path"] = file_path
        elif hasattr(UploadHistory, "file_path"):
            upload_history_payload["file_path"] = file_path

        if hasattr(UploadHistory, "content_type"):
            upload_history_payload["content_type"] = file.content_type

        if hasattr(UploadHistory, "claims_saved"):
            upload_history_payload["claims_saved"] = file_saved

        if hasattr(UploadHistory, "uploaded_at"):
            upload_history_payload["uploaded_at"] = datetime.now()

        if hasattr(UploadHistory, "uploaded_by_user_id"):
            upload_history_payload["uploaded_by_user_id"] = current_user["user_id"]
        elif hasattr(UploadHistory, "user_id"):
            upload_history_payload["user_id"] = current_user["user_id"]

        db.add(UploadHistory(**upload_history_payload))

        uploaded_files.append(
            {
                "filename": file.filename,
                "claims_saved": file_saved,
                "duplicates_skipped": file_duplicates,
                "existing_claims_deleted": file_existing_claims_deleted,
                "policies_replaced": sorted(list(policies_to_replace)),
                "policy_number": _clean(file_policy_number).upper() if can_persist_policy else "",
                "debug_policy_number": debug_policy_number,
                "can_persist_policy": can_persist_policy,
            }
        )

        all_parsed_claims.extend(parsed_claims)
        all_repaired_claims.extend(repaired_claims)

    if latest_profile_data and _valid_policy_number(latest_profile_data.get("policy_number")):
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
        resource_id=latest_profile_data.get("policy_number") or latest_profile_data.get("account_number") or "unknown",
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

    raw_claim_debug = _claim_debug_summary("raw_parsed_claims_debug", all_parsed_claims)
    repaired_claim_debug = _claim_debug_summary("repaired_claims_debug", all_repaired_claims)
    filtered_out_claim_debug = _filtered_out_claim_debug_summary("filtered_out_claims_debug", all_filtered_out_claims)
    saved_claim_debug = _claim_debug_summary("saved_claim_rows_debug", saved_claim_rows)

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
        "v2_multi_policy_claim_replacement": True,
        "v2_claim_debug_enabled": True,
        "v2_invalid_policy_guard_enabled": True,
        "v2_delayed_upload_fallback_enabled": True,
        **raw_claim_debug,
        **repaired_claim_debug,
        **filtered_out_claim_debug,
        **saved_claim_debug,
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