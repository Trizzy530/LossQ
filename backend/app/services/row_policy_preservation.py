from __future__ import annotations

import re
from typing import Any, Dict, Optional


PLACEHOLDER_VALUES = {
    "",
    "-",
    "--",
    "n/a",
    "na",
    "none",
    "null",
    "not set",
    "not available",
    "unknown",
    "policy number",
    "policy no",
    "policy",
    "account number",
    "claim number",
    "claim no",
    "status",
    "total",
    "subtotal",
    "grand total",
    "summary",
}


POLICY_NUMBER_KEYS = [
    "policy_number",
    "policy number",
    "policy no",
    "policy_no",
    "policy #",
    "policy",
    "policy id",
    "policy_id",
    "account policy",
    "account_number",
    "account number",
]

LINE_KEYS = [
    "line_of_business",
    "line of business",
    "policy_type",
    "policy type",
    "coverage",
    "coverage type",
    "coverage_type",
    "coverage_line",
    "line",
    "lob",
    "class",
]

CLAIM_NUMBER_KEYS = [
    "claim_number",
    "claim number",
    "claim no",
    "claim_no",
    "claim #",
    "claim",
    "claim_id",
]

STATUS_KEYS = [
    "status",
    "claim status",
    "claim_status",
    "open closed",
    "open/closed",
    "state",
]

CLOSED_DATE_KEYS = [
    "date closed",
    "closed date",
    "date_closed",
    "close date",
    "closure date",
]


def _clean_value(value: Any) -> str:
    if value is None:
        return ""

    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)
    return text.strip(" :;,\t\r\n")


def _key(value: Any) -> str:
    text = _clean_value(value).lower()
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text)
    return text


def _is_real_value(value: Any) -> bool:
    text = _clean_value(value)
    if not text:
        return False

    lowered = text.lower()
    if lowered in PLACEHOLDER_VALUES:
        return False

    if lowered.startswith("total ") or lowered.endswith(" total"):
        return False

    return True


def _lookup(raw: Dict[str, Any], keys: list[str]) -> str:
    if not isinstance(raw, dict):
        return ""

    normalized_map: Dict[str, Any] = {}

    for key, value in raw.items():
        if key is None:
            continue

        normalized_key = _key(key)
        normalized_map[normalized_key] = value
        normalized_map[normalized_key.replace(" ", "_")] = value

    for wanted in keys:
        wanted_key = _key(wanted)
        for candidate_key in (wanted_key, wanted_key.replace(" ", "_")):
            if candidate_key in normalized_map and _is_real_value(normalized_map[candidate_key]):
                return _clean_value(normalized_map[candidate_key])

    return ""


def normalize_line_of_business(value: Any) -> str:
    text = _clean_value(value)
    if not text:
        return ""

    lowered = text.lower()
    compact = re.sub(r"[^a-z0-9]", "", lowered)

    if compact in {"gl", "cgl"} or "general liability" in lowered or "commercial general liability" in lowered:
        return "General Liability"

    if compact in {"wc"} or "workers comp" in lowered or "worker compensation" in lowered or "workers compensation" in lowered:
        return "Workers Compensation"

    if "commercial auto" in lowered or compact in {"auto", "ca", "al"} or "fleet" in lowered or "vehicle" in lowered:
        return "Commercial Auto"

    if compact in {"bop"} or "businessowners" in lowered or "business owner" in lowered:
        return "Businessowners Policy"

    if "property" in lowered or compact in {"cp"}:
        return "Commercial Property"

    if "cyber" in lowered or compact in {"cy", "cyb"}:
        return "Cyber Liability"

    if "employment practices" in lowered or "epli" in lowered or compact in {"epli"}:
        return "Employment Practices Liability"

    if "directors" in lowered or "officers" in lowered or "d&o" in lowered or "d and o" in lowered or compact in {"do", "dando"}:
        return "Directors and Officers"

    if "umbrella" in lowered or "excess" in lowered or compact in {"umb", "xs"}:
        return "Umbrella Liability"

    if "professional" in lowered or "errors" in lowered or "omissions" in lowered or compact in {"pl", "eo", "eando"}:
        return "Professional Liability"

    if "inland marine" in lowered or compact in {"im"}:
        return "Inland Marine"

    return text


def infer_line_from_policy_or_claim(policy_number: str, claim_number: str = "") -> str:
    combined = f"{policy_number} {claim_number}".upper()

    checks = [
        ("EPLI", "Employment Practices Liability"),
        ("D&O", "Directors and Officers"),
        ("D-O", "Directors and Officers"),
        ("DO", "Directors and Officers"),
        ("UMB", "Umbrella Liability"),
        ("CYB", "Cyber Liability"),
        ("CY", "Cyber Liability"),
        ("BOP", "Businessowners Policy"),
        ("WC", "Workers Compensation"),
        ("AUTO", "Commercial Auto"),
        ("CA", "Commercial Auto"),
        ("GL", "General Liability"),
        ("CGL", "General Liability"),
        ("CP", "Commercial Property"),
        ("PROP", "Commercial Property"),
        ("PL", "Professional Liability"),
        ("E&O", "Professional Liability"),
        ("EO", "Professional Liability"),
        ("IM", "Inland Marine"),
    ]

    for token, label in checks:
        if re.search(rf"(^|[^A-Z0-9]){re.escape(token)}([^A-Z0-9]|$)", combined):
            return label

    return ""


def normalize_claim_status(raw: Dict[str, Any], normalized: Dict[str, Any]) -> Dict[str, Any]:
    row_status = _lookup(raw, STATUS_KEYS)
    closed_date = _lookup(raw, CLOSED_DATE_KEYS)

    status_text = _clean_value(row_status).lower()

    if status_text:
        if any(token in status_text for token in ["open", "pending", "reopen", "active"]):
            normalized["status"] = "Open"
            normalized["claim_status"] = "Open"
        elif any(token in status_text for token in ["closed", "close", "settled", "resolved"]):
            normalized["status"] = "Closed"
            normalized["claim_status"] = "Closed"
    elif _is_real_value(closed_date):
        normalized["status"] = "Closed"
        normalized["claim_status"] = "Closed"

    return normalized


def preserve_row_policy_fields(
    raw: Dict[str, Any],
    normalized: Dict[str, Any],
    fallback_policy_number: Optional[str] = None,
) -> Dict[str, Any]:
    if not isinstance(normalized, dict):
        normalized = {}

    row_policy_number = _lookup(raw, POLICY_NUMBER_KEYS)
    row_line = _lookup(raw, LINE_KEYS)
    row_claim_number = _lookup(raw, CLAIM_NUMBER_KEYS)

    existing_policy = _clean_value(normalized.get("policy_number"))
    fallback_policy = _clean_value(fallback_policy_number)

    if _is_real_value(row_policy_number):
        normalized["policy_number"] = row_policy_number
    elif not _is_real_value(existing_policy) and _is_real_value(fallback_policy):
        normalized["policy_number"] = fallback_policy

    normalized_policy = _clean_value(normalized.get("policy_number"))

    normalized_line = normalize_line_of_business(row_line)

    if not normalized_line:
        normalized_line = infer_line_from_policy_or_claim(normalized_policy, row_claim_number)

    if normalized_line:
        normalized["line_of_business"] = normalized_line
        normalized["policy_type"] = normalized_line
        normalized["coverage"] = normalized_line
        normalized["coverage_type"] = normalized_line
        normalized["line"] = normalized_line

    normalized = normalize_claim_status(raw, normalized)

    return normalized
