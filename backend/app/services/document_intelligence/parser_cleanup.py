from __future__ import annotations

import re
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None


MONEY_RE = re.compile(r"\(?\$?\s*([0-9]{1,3}(?:,[0-9]{3})*|[0-9]+)(?:\.(\d{2}))?\)?")
MONEY_TOKEN_RE = re.compile(r"\(?\$\s*[0-9]{1,3}(?:,[0-9]{3})*(?:\.\d{2})?\)?|\(?\$\s*[0-9]+(?:\.\d{2})?\)?")
DATE_RE = re.compile(r"\b(?:\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})\b")

POLICY_RE = re.compile(
    r"\b(?:GP|[A-Z]{2,6})[-\s]?(?:AL|AUTO|GL|WC|CG|CARGO|MT|MT-CARGO)[-\s]?[A-Z0-9]{3,12}(?:[-\s]?\d{1,4})?\b",
    re.IGNORECASE,
)

KNOWN_FAKE_CLAIM_VALUES = {
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
}


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _get_nested(data: Dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _normalize_spaces(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalize_policy_number(value: Any) -> str:
    text = _normalize_spaces(value).upper()
    text = text.replace(" ", "-")
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def _money_to_float(value: Any) -> float:
    if value is None:
        return 0.0

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return 0.0

    negative = text.startswith("(") and text.endswith(")")
    text = text.replace("$", "").replace(",", "").replace("(", "").replace(")", "").strip()

    try:
        amount = float(text)
        return -amount if negative else amount
    except Exception:
        match = MONEY_RE.search(str(value))
        if not match:
            return 0.0
        whole = match.group(1).replace(",", "")
        cents = match.group(2) or "00"
        amount = float(f"{whole}.{cents}")
        return -amount if negative else amount


def _extract_pdf_text(filename: str, content: Optional[bytes]) -> str:
    if not content:
        return ""

    if not filename.lower().endswith(".pdf"):
        return ""

    if PdfReader is None:
        return ""

    try:
        reader = PdfReader(BytesIO(content))
        parts: List[str] = []

        for page_index, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
            if page_text.strip():
                parts.append(f"--- PAGE {page_index} ---\n{page_text}")

        return "\n\n".join(parts).strip()
    except Exception as exc:
        print("LossQ cleanup PDF text fallback failed:", str(exc))
        return ""


def _collect_raw_text(parsed: Dict[str, Any], filename: str = "", content: Optional[bytes] = None) -> str:
    profile = _as_dict(parsed.get("profile"))
    account = _as_dict(parsed.get("account"))
    metadata = _as_dict(parsed.get("metadata"))

    raw_text = _first_text(
        parsed.get("raw_text_preview"),
        parsed.get("raw_text"),
        parsed.get("text"),
        parsed.get("extracted_text"),
        profile.get("raw_text_preview"),
        profile.get("raw_text"),
        profile.get("text"),
        profile.get("extracted_text"),
        account.get("raw_text_preview"),
        account.get("raw_text"),
        metadata.get("raw_text_preview"),
        metadata.get("raw_text"),
    )

    if not raw_text:
        raw_text = _extract_pdf_text(filename, content)

    return raw_text


def _extract_after_label(raw_text: str, labels: List[str]) -> str:
    for label in labels:
        pattern = re.compile(
            rf"{re.escape(label)}\s*[:\-]\s*(.+?)(?:\n|$)",
            re.IGNORECASE,
        )
        match = pattern.search(raw_text)
        if match:
            value = _normalize_spaces(match.group(1))
            value = re.sub(r"\s{2,}.*$", "", value).strip()
            if value:
                return value
    return ""


def _extract_business_name(raw_text: str) -> str:
    value = _extract_after_label(
        raw_text,
        [
            "Named Insured",
            "Insured Name",
            "Business Name",
            "Account Name",
            "Applicant",
        ],
    )

    if value:
        return value

    match = re.search(
        r"\b([A-Z][A-Za-z0-9&.,' -]+?(?:LLC|INC\.?|CORP\.?|COMPANY|CO\.|LTD\.?))\b",
        raw_text,
        re.IGNORECASE,
    )
    return _normalize_spaces(match.group(1)) if match else ""


def _extract_carrier_name(raw_text: str) -> str:
    value = _extract_after_label(
        raw_text,
        [
            "Writing Carrier",
            "Carrier Name",
            "Insurer Name",
            "Insurer",
            "Insurance Company",
            "Company",
        ],
    )

    if value:
        return value

    match = re.search(
        r"\b([A-Z][A-Za-z0-9&.,' -]+?(?:Insurance Co\.?|Insurance Company|Mutual Insurance Co\.?|Mutual|Indemnity|Casualty|Underwriters))\b",
        raw_text,
        re.IGNORECASE,
    )
    return _normalize_spaces(match.group(1)) if match else ""


def _line_of_business_from_text(text: str) -> str:
    upper = text.upper()

    if "WORK" in upper and ("COMP" in upper or "COMPENSATION" in upper):
        return "Workers Comp"

    if "GENERAL" in upper and "LIAB" in upper:
        return "General Liability"

    if "CARGO" in upper:
        return "Motor Truck Cargo"

    if "AUTO" in upper or "AL-" in upper or "-AL-" in upper:
        return "Auto Liability"

    return ""


def _extract_policy_rows(raw_text: str) -> List[Dict[str, Any]]:
    policies: List[Dict[str, Any]] = []
    seen = set()

    for line in raw_text.splitlines():
        clean_line = _normalize_spaces(line)
        if not clean_line:
            continue

        policy_matches = list(POLICY_RE.finditer(clean_line))
        if not policy_matches:
            continue

        for match in policy_matches:
            policy_number = _normalize_policy_number(match.group(0))
            if policy_number in seen:
                continue

            lob = _line_of_business_from_text(clean_line)
            if not lob:
                lob = _line_of_business_from_text(policy_number)

            dates = DATE_RE.findall(clean_line)

            policy = {
                "policy_number": policy_number,
                "line_of_business": lob or "Unknown",
            }

            if len(dates) >= 1:
                policy["effective_date"] = dates[0]
            if len(dates) >= 2:
                policy["expiration_date"] = dates[1]

            policies.append(policy)
            seen.add(policy_number)

    return policies


def _claim_policy_from_claim_number(claim_number: str, policies: List[Dict[str, Any]]) -> str:
    upper = claim_number.upper()

    policy_by_lob = {
        "AL": "",
        "GL": "",
        "WC": "",
        "CG": "",
    }

    for policy in policies:
        policy_number = _normalize_policy_number(policy.get("policy_number"))
        lob = _line_of_business_from_text(
            f"{policy.get('line_of_business', '')} {policy_number}"
        ).upper()

        if "AUTO" in lob:
            policy_by_lob["AL"] = policy_number
        elif "GENERAL" in lob:
            policy_by_lob["GL"] = policy_number
        elif "WORKERS" in lob:
            policy_by_lob["WC"] = policy_number
        elif "CARGO" in lob:
            policy_by_lob["CG"] = policy_number

    if upper.startswith(("AL-", "AUTO-", "CA-", "AU-")):
        return policy_by_lob.get("AL", "")

    if upper.startswith(("GL-", "GENERAL-")):
        return policy_by_lob.get("GL", "")

    if upper.startswith(("WC-", "WORK-")):
        return policy_by_lob.get("WC", "")

    if upper.startswith(("CG-", "CARGO-", "MT-")):
        return policy_by_lob.get("CG", "")

    return ""


def _lob_from_claim_number_or_policy(claim_number: str, policy_number: str) -> str:
    text = f"{claim_number} {policy_number}".upper()

    if text.startswith(("WC-", "WORK-")) or "-WC-" in text:
        return "Workers Comp"

    if text.startswith(("GL-", "GENERAL-")) or "-GL-" in text:
        return "General Liability"

    if text.startswith(("CG-", "CARGO-", "MT-")) or "-CG-" in text or "CARGO" in text:
        return "Motor Truck Cargo"

    if text.startswith(("AL-", "AUTO-", "CA-", "AU-")) or "-AL-" in text:
        return "Auto Liability"

    return ""


def _is_fake_header_claim(claim: Dict[str, Any], policies: List[Dict[str, Any]]) -> bool:
    claim_number = _normalize_spaces(claim.get("claim_number") or claim.get("claimNumber"))
    claim_upper = claim_number.upper()

    if not claim_upper:
        return True

    normalized_fake_values = {value.upper() for value in KNOWN_FAKE_CLAIM_VALUES}

    if claim_upper in normalized_fake_values:
        return True

    policy_numbers = {
        _normalize_policy_number(policy.get("policy_number"))
        for policy in policies
        if policy.get("policy_number")
    }

    if _normalize_policy_number(claim_upper) in policy_numbers:
        return True

    # Common parser failure: fragments from policy/header rows become zero-dollar claims.
    if claim_upper in {"AL", "GL", "WC", "CG", "AUTO", "LIABILITY"}:
        return True

    if re.fullmatch(r"(?:AL|GL|WC|CG)[-\s]?\d{3,}", claim_upper):
        for policy in policies:
            policy_number = _normalize_policy_number(policy.get("policy_number"))
            compact_policy = policy_number.replace("-", "")
            compact_claim = claim_upper.replace("-", "").replace(" ", "")
            if compact_claim and compact_claim in compact_policy:
                return True

    incurred = _money_to_float(
        claim.get("total_incurred")
        or claim.get("incurred")
        or claim.get("total")
        or claim.get("amount")
    )

    paid = _money_to_float(claim.get("paid") or claim.get("paid_amount"))
    reserve = _money_to_float(claim.get("reserve") or claim.get("reserve_amount"))

    description = _normalize_spaces(
        claim.get("description")
        or claim.get("loss_description")
        or claim.get("claim_description")
        or claim.get("cause_of_loss")
    )

    if incurred == 0 and paid == 0 and reserve == 0:
        if _line_of_business_from_text(claim_upper) or _line_of_business_from_text(description):
            return True

    return False



def _claim_match_is_inside_policy_number(line: str, match: re.Match[str]) -> bool:
    """
    Prevent policy numbers like GP-AL-240177-01 from creating fake claims like AL-240177.
    """
    start = match.start()
    end = match.end()

    for policy_match in POLICY_RE.finditer(line):
        if policy_match.start() <= start and end <= policy_match.end():
            return True

    before = line[max(0, start - 4):start].upper()
    after = line[end:end + 4].upper()

    if before.endswith("GP-") or before.endswith("GP "):
        return True

    if re.match(r"[-\s]?\d{1,4}\b", after):
        return True

    return False

def _extract_claim_rows_from_raw_text(raw_text: str, policies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    claims: List[Dict[str, Any]] = []
    seen = set()

    claim_number_re = re.compile(r"\b(?:AL|GL|WC|CG|AUTO|CARGO|MT)[- ][A-Z0-9]{3,20}\b", re.IGNORECASE)

    for line in raw_text.splitlines():
        clean_line = _normalize_spaces(line)
        if not clean_line:
            continue

        # Skip pure policy/header lines.
        if POLICY_RE.search(clean_line) and not claim_number_re.search(clean_line):
            continue

        claim_match = claim_number_re.search(clean_line)
        if not claim_match:
            continue

        if _claim_match_is_inside_policy_number(clean_line, claim_match):
            continue

        claim_number = _normalize_spaces(claim_match.group(0)).upper().replace(" ", "-")

        if claim_number in seen:
            continue

        upper_claim = claim_number.upper()
        if upper_claim in KNOWN_FAKE_CLAIM_VALUES:
            continue

        money_values = [_money_to_float(m.group(0)) for m in MONEY_TOKEN_RE.finditer(clean_line)]
        money_values = [value for value in money_values if value != 0]

        dates = DATE_RE.findall(clean_line)
        policy_number = _claim_policy_from_claim_number(claim_number, policies)

        total_incurred = money_values[-1] if money_values else 0.0
        reserve = money_values[-2] if len(money_values) >= 2 else 0.0
        paid = money_values[-3] if len(money_values) >= 3 else max(total_incurred - reserve, 0.0)

        description = clean_line[claim_match.end():].strip(" -|")
        description = re.sub(r"\$?\(?[0-9,]+(?:\.\d{2})?\)?", "", description)
        description = DATE_RE.sub("", description)
        description = _normalize_spaces(description)

        claim = {
            "claim_number": claim_number,
            "policy_number": policy_number,
            "line_of_business": _lob_from_claim_number_or_policy(claim_number, policy_number) or "Unknown",
            "description": description,
            "loss_description": description,
            "paid": round(paid, 2),
            "reserve": round(reserve, 2),
            "total_incurred": round(total_incurred, 2),
            "status": "Open" if reserve > 0 else "Closed",
        }

        if len(dates) >= 1:
            claim["date_of_loss"] = dates[0]
        if len(dates) >= 2:
            claim["date_reported"] = dates[1]

        claims.append(claim)
        seen.add(claim_number)

    return claims


def _clean_existing_claims(existing_claims: Any, policies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(existing_claims, list):
        return []

    cleaned: List[Dict[str, Any]] = []
    seen = set()

    for item in existing_claims:
        if not isinstance(item, dict):
            continue

        claim = dict(item)

        if _is_fake_header_claim(claim, policies):
            continue

        claim_number = _normalize_spaces(claim.get("claim_number") or claim.get("claimNumber")).upper().replace(" ", "-")
        if not claim_number:
            continue

        if claim_number in seen:
            continue

        policy_number = _normalize_policy_number(claim.get("policy_number") or claim.get("policyNumber"))

        if not policy_number:
            policy_number = _claim_policy_from_claim_number(claim_number, policies)

        lob = (
            _normalize_spaces(claim.get("line_of_business") or claim.get("lob") or claim.get("coverage_type"))
            or _lob_from_claim_number_or_policy(claim_number, policy_number)
            or "Unknown"
        )

        claim["claim_number"] = claim_number
        claim["policy_number"] = policy_number
        claim["line_of_business"] = lob
        claim["total_incurred"] = round(
            _money_to_float(
                claim.get("total_incurred")
                or claim.get("incurred")
                or claim.get("total")
                or claim.get("amount")
            ),
            2,
        )
        claim["paid"] = round(_money_to_float(claim.get("paid") or claim.get("paid_amount")), 2)
        claim["reserve"] = round(_money_to_float(claim.get("reserve") or claim.get("reserve_amount")), 2)

        if not claim.get("status"):
            claim["status"] = "Open" if claim["reserve"] > 0 else "Closed"

        cleaned.append(claim)
        seen.add(claim_number)

    return cleaned


def _claim_total(claims: List[Dict[str, Any]]) -> float:
    return round(sum(_money_to_float(claim.get("total_incurred")) for claim in claims), 2)


def _apply_profile(parsed: Dict[str, Any], business_name: str, carrier_name: str, policies: List[Dict[str, Any]]) -> None:
    profile = _as_dict(parsed.get("profile"))
    account = _as_dict(parsed.get("account"))

    if business_name:
        parsed["business_name"] = business_name
        profile["business_name"] = business_name
        account["business_name"] = business_name
        parsed["named_insured"] = business_name
        profile["named_insured"] = business_name

    if carrier_name:
        parsed["carrier_name"] = carrier_name
        parsed["writing_carrier"] = carrier_name
        profile["carrier_name"] = carrier_name
        profile["writing_carrier"] = carrier_name
        account["carrier_name"] = carrier_name

    if policies:
        parsed["policies"] = policies
        profile["policies"] = policies

        primary_policy = policies[0].get("policy_number", "")
        if primary_policy:
            parsed["policy_number"] = primary_policy
            profile["policy_number"] = primary_policy
            account["policy_number"] = primary_policy

        first_effective = policies[0].get("effective_date")
        first_expiration = policies[0].get("expiration_date")

        if first_effective:
            profile["effective_date"] = first_effective
            account["effective_date"] = first_effective
            parsed["effective_date"] = first_effective

        if first_expiration:
            profile["expiration_date"] = first_expiration
            account["expiration_date"] = first_expiration
            parsed["expiration_date"] = first_expiration

    parsed["profile"] = profile
    parsed["account"] = account


def cleanup_loss_run_extraction(
    parsed: Dict[str, Any],
    filename: str = "",
    content: bytes | None = None,
) -> Dict[str, Any]:
    """
    Final cleanup layer for messy loss run extraction.

    This function is intentionally defensive because normal OCR/parser output can vary.
    It now accepts the uploaded file bytes so the cleanup layer can extract PDF text
    directly when raw_text/raw_text_preview was not passed forward by the normal route.
    """

    if not isinstance(parsed, dict):
        return parsed

    raw_text = _collect_raw_text(parsed, filename=filename or "", content=content)

    if raw_text:
        parsed["raw_text_preview"] = raw_text[:12000]

        print("\n\n================ LOSSQ RAW TEXT DEBUG START ================")
        print(raw_text[:20000])
        print("================ LOSSQ RAW TEXT DEBUG END ================\n\n")

    business_name = _extract_business_name(raw_text) if raw_text else ""
    carrier_name = _extract_carrier_name(raw_text) if raw_text else ""
    policies = _extract_policy_rows(raw_text) if raw_text else []

    existing_claims = (
        parsed.get("claims")
        or parsed.get("parsed_claims")
        or parsed.get("claim_rows")
        or parsed.get("losses")
        or []
    )

    cleaned_claims = _clean_existing_claims(existing_claims, policies)

    raw_claims = _extract_claim_rows_from_raw_text(raw_text, policies) if raw_text else []

    # Prefer raw-text claim extraction when the existing parser clearly over-counted by treating
    # policy/header rows as claims. This fixes messy multi-line PDFs without disrupting normal uploads.
    if raw_claims:
        if not cleaned_claims:
            final_claims = raw_claims
        elif len(cleaned_claims) > len(raw_claims) and len(raw_claims) >= 3:
            final_claims = raw_claims
        else:
            final_claims = cleaned_claims
    else:
        final_claims = cleaned_claims

    if final_claims:
        parsed["claims"] = final_claims
        parsed["parsed_claims"] = final_claims
        parsed["claim_count"] = len(final_claims)
        parsed["total_incurred"] = _claim_total(final_claims)

    if policies:
        parsed["policy_count"] = len(policies)

    _apply_profile(parsed, business_name, carrier_name, policies)

    # Prevent fallback UPLOAD-* values from winning when real profile/policy data exists.
    policy_number = _normalize_policy_number(parsed.get("policy_number"))
    if policy_number.startswith("UPLOAD-") and policies:
        real_policy = policies[0].get("policy_number", "")
        if real_policy:
            parsed["policy_number"] = real_policy
            parsed.setdefault("profile", {})["policy_number"] = real_policy
            parsed.setdefault("account", {})["policy_number"] = real_policy

    return parsed
