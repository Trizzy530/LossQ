from __future__ import annotations

import io
import re
from collections import defaultdict
from typing import Any, Dict, List, Tuple


def _clean(value: Any) -> str:
    value = str(value or "").strip()
    value = re.sub(r"\s+", " ", value)
    return value.strip(" :-|\t\r\n")


def _money_to_float(value: Any) -> float:
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


def _find_first(patterns: List[str], text: str, default: str = "") -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            value = _clean(match.group(1))
            if value:
                return value
    return default


def _is_bad_policy(value: Any) -> bool:
    value = _clean(value).upper()
    if not value:
        return True
    if value in {"POLICY", "POLICY NUMBER", "ACCOUNT", "ACCOUNT NUMBER", "CLAIMS", "YES"}:
        return True
    if len(value) < 4:
        return True
    return False


def _normalize_policy(value: Any) -> str:
    value = _clean(value).upper()
    value = value.replace(" ", "")
    value = value.strip(":-|")
    return value


def _extract_text_from_pdf(content: bytes) -> str:
    text_parts: List[str] = []

    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text:
                text_parts.append(page_text)
    except Exception:
        pass

    text = "\n".join(text_parts)

    # Fallback for non-PDF text uploads.
    if not text.strip():
        try:
            text = content.decode("utf-8", errors="ignore")
        except Exception:
            text = ""

    return text


def _extract_profile(text: str) -> Dict[str, Any]:
    business_name = _find_first(
        [
            r"Named\s*Insured\s*[:\-]\s*(.*?)(?:\n|Policy\s*Number|Carrier\s*:|Report\s*Run\s*Date)",
            r"Insured\s*[:\-]\s*(.*?)(?:\n|Policy\s*Number|Carrier\s*:|Report\s*Run\s*Date)",
            r"Account\s*Name\s*[:\-]\s*(.*?)(?:\n|Policy\s*Number|Carrier\s*:|Report\s*Run\s*Date)",
        ],
        text,
    )

    if business_name.lower() in {"carrier", "policy", "claims", "yes"}:
        business_name = ""

    carrier_name = _find_first(
        [
            r"Carrier\s*[:\-]\s*(.*?)(?:\n|Policy\s*Number|Named\s*Insured|Policy\s*Term)",
            r"Insurance\s*Company\s*[:\-]\s*(.*?)(?:\n|Policy\s*Number|Named\s*Insured|Policy\s*Term)",
            r"Writing\s*Carrier\s*[:\-]\s*(.*?)(?:\n|Policy\s*Number|Named\s*Insured|Policy\s*Term)",
        ],
        text,
    )

    if carrier_name.lower() in {"carrier", "policy", "claims", "yes"}:
        carrier_name = ""

    policy_candidates = [
        _normalize_policy(x)
        for x in re.findall(r"Policy\s*Number\s*[:\-]\s*([A-Z0-9][A-Z0-9\-\s]{3,40})", text, flags=re.IGNORECASE)
    ]
    policy_candidates = [p for p in policy_candidates if not _is_bad_policy(p)]

    policy_number = policy_candidates[0] if policy_candidates else ""

    effective_date = ""
    expiration_date = ""
    term_match = re.search(
        r"Policy\s*Term\s*[:\-]?\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})\s*[-–]\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})",
        text,
        flags=re.IGNORECASE,
    )
    if term_match:
        effective_date = term_match.group(1)
        expiration_date = term_match.group(2)

    return {
        "business_name": business_name,
        "carrier_name": carrier_name,
        "writing_carrier": carrier_name,
        "policy_number": policy_number,
        "account_number": policy_number,
        "customer_number": policy_number,
        "effective_date": effective_date,
        "expiration_date": expiration_date,
        "evaluation_date": "",
        "raw_text_preview": text[:2500],
    }


def _find_policy_for_position(text: str, position: int, fallback_policy: str) -> str:
    before = text[:position]
    matches = list(
        re.finditer(
            r"Policy\s*Number\s*[:\-]\s*([A-Z0-9][A-Z0-9\-\s]{3,40})",
            before,
            flags=re.IGNORECASE,
        )
    )

    for match in reversed(matches):
        policy = _normalize_policy(match.group(1))
        if not _is_bad_policy(policy):
            return policy

    return fallback_policy


def _extract_claim_sections(text: str, fallback_policy: str) -> List[Tuple[str, str, str]]:
    """
    Returns tuples of (claim_number, policy_number, claim_section_text).
    Uses actual "Claim Number:" anchors so policy numbers do not become claims.
    """
    claim_pattern = re.compile(
        r"Claim\s*Number\s*[:\-]\s*([A-Z]{1,4}[-\s]?[A-Z0-9]{2,20}(?:[-\s][A-Z0-9]{2,20})*)",
        flags=re.IGNORECASE,
    )

    matches = list(claim_pattern.finditer(text))
    sections: List[Tuple[str, str, str]] = []

    for index, match in enumerate(matches):
        claim_number = _clean(match.group(1)).upper().replace(" ", "-")
        claim_number = re.sub(r"-{2,}", "-", claim_number)

        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else min(len(text), start + 2500)
        section = text[start:end]

        if claim_number in {"CLAIM", "CLAIM-NUMBER", "POLICY"}:
            continue

        policy_number = _find_policy_for_position(text, start, fallback_policy)

        if _is_bad_policy(policy_number):
            policy_number = fallback_policy

        sections.append((claim_number, policy_number, section))

    return sections


def _extract_amounts_from_section(section: str) -> List[float]:
    values: List[float] = []
    for raw in re.findall(r"\$\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})|[0-9]+(?:\.[0-9]{2}))", section):
        amount = _money_to_float(raw)
        if amount > 0:
            values.append(amount)
    return values


def _extract_date(section: str, label: str) -> str:
    match = re.search(
        rf"{re.escape(label)}\s*[:\-]\s*([0-9]{{1,2}}/[0-9]{{1,2}}/[0-9]{{2,4}})",
        section,
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else ""


def _extract_status(section: str) -> str:
    match = re.search(r"Status\s*of\s*Loss\s*[:\-]\s*([A-Za-z]+)", section, flags=re.IGNORECASE)
    if match:
        value = match.group(1).strip().title()
        if value.lower() in {"open", "closed", "pending", "reopened"}:
            return value

    if re.search(r"\bOpen\b", section, flags=re.IGNORECASE):
        return "Open"
    if re.search(r"\bClosed\b", section, flags=re.IGNORECASE):
        return "Closed"

    return ""


def _extract_description(section: str) -> str:
    match = re.search(
        r"Description\s*of\s*Loss\s*[:\-]\s*(.*?)(?:Claimant\s+Type\s+Of\s+Loss|Claimant\s+TypeOfLoss|$)",
        section,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match:
        return _clean(match.group(1))
    return _clean(section[:500])


def _infer_lob(section: str, claim_number: str) -> str:
    section_lower = section.lower()
    claim_upper = claim_number.upper()

    if claim_upper.startswith("WC") or "workers comp" in section_lower:
        return "Workers Comp"
    if claim_upper.startswith("CG") or "cargo" in section_lower:
        return "Cargo"
    if claim_upper.startswith("GL") or "general liability" in section_lower:
        return "General Liability"
    if claim_upper.startswith("AU") or "collision" in section_lower or "vehicle" in section_lower or "truck" in section_lower:
        return "Commercial Auto"
    if "property damage" in section_lower:
        return "General Liability"
    return "Unknown"


def _extract_claims(text: str, fallback_policy: str) -> List[Dict[str, Any]]:
    claims: List[Dict[str, Any]] = []

    for claim_number, policy_number, section in _extract_claim_sections(text, fallback_policy):
        amounts = _extract_amounts_from_section(section)

        total_incurred = max(amounts) if amounts else 0.0

        # Try to read paid and reserve from the table. For most loss runs, the
        # largest amount is safest as the total net loss when extraction is messy.
        paid_amount = total_incurred
        reserve_amount = 0.0

        if re.search(r"\bOpen\b", section, flags=re.IGNORECASE) and len(amounts) >= 2:
            # Open claims commonly show paid + remaining reserve + net loss.
            # Keep total as largest, paid as first meaningful amount, reserve as
            # the second-largest if it is below/equal total.
            paid_amount = amounts[0]
            possible_reserves = [a for a in amounts if a != paid_amount and a <= total_incurred]
            reserve_amount = max(possible_reserves) if possible_reserves else 0.0

        claim = {
            "claim_number": claim_number,
            "policy_number": policy_number,
            "line_of_business": _infer_lob(section, claim_number),
            "loss_date": _extract_date(section, "Loss Date"),
            "date_of_loss": _extract_date(section, "Loss Date"),
            "reported_date": _extract_date(section, "Loss Report Date"),
            "date_reported": _extract_date(section, "Loss Report Date"),
            "status": _extract_status(section),
            "paid_amount": paid_amount,
            "reserve_amount": reserve_amount,
            "total_incurred": total_incurred,
            "description": _extract_description(section),
        }

        claims.append(claim)

    return claims


def _policy_rollup(claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}

    for claim in claims:
        policy_number = _normalize_policy(claim.get("policy_number"))
        if _is_bad_policy(policy_number):
            continue

        lob = _clean(claim.get("line_of_business")) or "Unknown"

        if policy_number not in grouped:
            grouped[policy_number] = {
                "policy_number": policy_number,
                "policy_type": lob,
                "line_of_business": lob,
                "claim_count": 0,
                "total_incurred": 0.0,
            }

        grouped[policy_number]["claim_count"] += 1
        grouped[policy_number]["total_incurred"] += _money_to_float(claim.get("total_incurred"))

    return list(grouped.values())


def parse_loss_run_upload(filename: str, content: bytes) -> Dict[str, Any]:
    """
    Universal V2 parser entry point used by app.routes.upload_v2.

    Goal: favor accuracy over over-extraction.
    - Only creates claims from actual "Claim Number:" anchors.
    - Rejects header labels like POLICY as policy numbers.
    - Uses the nearest previous Policy Number as the claim policy.
    - Reads dates/status/amounts from each claim section.
    """
    text = _extract_text_from_pdf(content)
    profile = _extract_profile(text)

    fallback_policy = profile.get("policy_number") or ""
    claims = _extract_claims(text, fallback_policy)

    # If the first policy number is missing but claims have policies, use the first claim policy.
    if not profile.get("policy_number") and claims:
        profile["policy_number"] = claims[0].get("policy_number", "")
        profile["account_number"] = profile["policy_number"]
        profile["customer_number"] = profile["policy_number"]

    policies = _policy_rollup(claims)

    total_incurred = round(sum(_money_to_float(c.get("total_incurred")) for c in claims), 2)

    validation = {
        "is_valid": bool(claims),
        "confidence_score": 90 if claims else 40,
        "needs_manual_review": not bool(claims),
        "needs_review": [],
        "warnings": [],
        "policy_count": len(policies),
        "claim_count": len(claims),
        "calculated_total_incurred": total_incurred,
        "document_total_incurred": 0,
        "policy_rollup": policies,
    }

    if not profile.get("carrier_name"):
        validation["needs_review"].append("Carrier or writing carrier was not detected.")

    if not profile.get("business_name"):
        validation["needs_review"].append("Business/account name was not detected.")

    profile["policies"] = policies
    profile["validation"] = validation

    return {
        "filename": filename,
        "profile": profile,
        "policies": policies,
        "validation": validation,
        "claims": claims,
        "parsed_claims": claims,
        "claim_count": len(claims),
    }
