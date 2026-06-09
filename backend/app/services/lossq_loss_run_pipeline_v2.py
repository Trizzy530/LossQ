from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Tuple


BAD_LABELS = {
    "",
    "POLICY",
    "POLICYNUMBER",
    "POLICYTERM",
    "CLAIMS",
    "YES",
    "NO",
    "CARRIER",
    "NAMEDINSURED",
    "REPORT",
    "REPORTDATE",
    "PAG",
    "PAGE",
    "UPLOAD",
    "CLAIM",
    "CLAIMNUMBER",
    "AND",
    "LINE",
    "COVERAGE",
    "STATUS",
    "TOTAL",
    "INCURRED",
    "PAID",
    "RESERVE",
    "OPEN",
    "CLOSED",
}

FAKE_CLAIM_TOKENS = {
    "AND-COMMERCIAL-AUTO",
    "BODILY-INJURY-FILES",
    "LINE-COVERAGE",
    "COMMERCIAL-AUTO",
    "AUTO-LIABILITY",
    "GENERAL-LIABILITY",
    "WORKERS-COMP",
    "WORKERS-COMPENSATION",
    "MOTOR-TRUCK-CARGO",
    "CARGO",
    "CLAIM-NUMBER",
    "CLAIM-NO",
    "LOSS-RUN",
    "POLICY-NUMBER",
    "TOTAL-INCURRED",
    "PAID-LOSS",
    "CASE-RESERVE",
}


def _clean(value: Any) -> str:
    value = str(value or "").strip()
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n\s+", "\n", value)
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


def _normalize_policy(value: Any) -> str:
    raw = _clean(value).upper()
    raw = re.split(
        r"(POLICY\s*TERM|POLICYTERM|CLAIM\s*DETAILS|CLAIMDETAILS|REPORT\s*RUN|REPORTRUN|NAMED\s*INSURED|NAMEDINSURED|CARRIER|PAGE|LH\s*\d)",
        raw,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    raw = raw.replace(" ", "")
    raw = raw.strip(":-|.,;")
    raw = re.sub(r"[^A-Z0-9\-]", "", raw)
    return raw


def _looks_like_policy(value: Any) -> bool:
    policy = _normalize_policy(value)
    if not policy or policy in BAD_LABELS:
        return False
    if policy.startswith("POLICY") or policy.startswith("CLAIM"):
        return False
    if len(policy) < 4:
        return False
    if not re.search(r"\d", policy):
        return False
    return True


def _looks_like_real_claim_number(value: Any) -> bool:
    """
    A real claim number must:
    - Have at least one digit
    - Not be a known fake token
    - Not be a pure LOB label
    - Be at least 5 characters
    - Contain at least one letter AND one digit
    """
    claim = _clean(value).upper().replace(" ", "-")
    claim = re.sub(r"-{2,}", "-", claim).strip("-")

    if not claim:
        return False
    if len(claim) < 5:
        return False
    if claim in BAD_LABELS:
        return False
    if claim in FAKE_CLAIM_TOKENS:
        return False
    if not re.search(r"\d", claim):
        return False
    if not re.search(r"[A-Z]", claim):
        return False
    # Reject pure LOB fragments
    lob_fragments = {
        "COMMERCIAL", "AUTO", "LIABILITY", "GENERAL", "WORKERS",
        "COMPENSATION", "CARGO", "TRUCK", "BODILY", "INJURY",
        "PROPERTY", "DAMAGE", "MEDICAL", "EXPENSE",
    }
    parts = set(claim.replace("-", " ").split())
    if parts.issubset(lob_fragments):
        return False
    return True


def _extract_text_from_pdf(content: bytes) -> str:
    text_parts: List[str] = []

    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                text_parts.append(page_text)
    except Exception:
        pass

    text = "\n".join(text_parts)

    if not text.strip():
        try:
            text = content.decode("utf-8", errors="ignore")
        except Exception:
            text = ""

    return text


def _nonempty_lines(text: str) -> List[str]:
    return [_clean(line) for line in text.splitlines() if _clean(line)]


def _extract_header_blocks(text: str) -> List[Dict[str, str]]:
    lines = _nonempty_lines(text)
    blocks: List[Dict[str, str]] = []

    for i in range(len(lines)):
        window = [line.lower().replace(" ", "") for line in lines[i: i + 5]]

        if (
            len(window) >= 5
            and window[0].startswith("reportrundate")
            and window[1].startswith("namedinsured")
            and window[2].startswith("carrier")
            and window[3].startswith("policynumber")
            and window[4].startswith("policyterm")
        ):
            values = lines[i + 5: i + 10]
            if len(values) >= 5:
                candidate = {
                    "report_run_date": values[0],
                    "business_name": values[1],
                    "carrier_name": values[2],
                    "writing_carrier": values[2],
                    "policy_number": _normalize_policy(values[3]),
                    "policy_term": values[4],
                }
                if _looks_like_policy(candidate["policy_number"]):
                    blocks.append(candidate)

    return blocks


def _find_inline_value(patterns: List[str], text: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            value = _clean(match.group(1))
            if value:
                return value
    return ""


def _find_policy_numbers(text: str) -> List[Tuple[int, str]]:
    found: List[Tuple[int, str]] = []

    patterns = [
        r"Policy\s*Number\s*[:\-]\s*([A-Z0-9][A-Z0-9\-\s]{3,60})",
        r"Policy\s*#\s*[:\-]\s*([A-Z0-9][A-Z0-9\-\s]{3,60})",
        r"Policy\s*Number\s*\n\s*([A-Z0-9][A-Z0-9\-\s]{3,60})",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            policy = _normalize_policy(match.group(1))
            if _looks_like_policy(policy):
                found.append((match.start(), policy))

    for block in _extract_header_blocks(text):
        policy = block.get("policy_number", "")
        if _looks_like_policy(policy):
            pos = text.find(policy)
            if pos < 0:
                pos = 0
            found.append((pos, policy))

    # Also scan for standalone policy-shaped tokens on their own line
    # Format: GP-AL-240177-01 or 4537898-40 etc.
    standalone_re = re.compile(
        r"^\s*([A-Z]{2,6}-(?:AL|GL|WC|CG|AUTO|CARGO|MT)-[A-Z0-9]+-\d{1,4})\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    for match in standalone_re.finditer(text):
        policy = _normalize_policy(match.group(1))
        if _looks_like_policy(policy):
            found.append((match.start(), policy))

    deduped: List[Tuple[int, str]] = []
    seen = set()
    for pos, policy in sorted(found, key=lambda item: item[0]):
        if policy not in seen:
            seen.add(policy)
            deduped.append((pos, policy))

    return deduped


def _nearest_policy_before(
    policy_positions: List[Tuple[int, str]], pos: int, fallback: str
) -> str:
    selected = fallback
    for policy_pos, policy in policy_positions:
        if policy_pos <= pos:
            selected = policy
        else:
            break
    return selected if _looks_like_policy(selected) else fallback


def _extract_profile(text: str) -> Dict[str, Any]:
    blocks = _extract_header_blocks(text)
    first_block = blocks[0] if blocks else {}

    business_name = first_block.get("business_name") or _find_inline_value(
        [
            r"Named\s*Insured\s*[:\-]\s*(.*?)(?:\n|Policy\s*Number|Carrier\s*:|Policy\s*Term|Report\s*Run\s*Date)",
            r"Insured\s*[:\-]\s*(.*?)(?:\n|Policy\s*Number|Carrier\s*:|Policy\s*Term|Report\s*Run\s*Date)",
            r"Insured\s*\n\s*(.*?)(?:\n|Policy\s*Number|Carrier|Policy\s*Term)",
            r"Account\s*Name\s*[:\-]\s*(.*?)(?:\n|Policy\s*Number|Carrier\s*:|Policy\s*Term)",
        ],
        text,
    )

    if business_name and business_name.lower() in {
        "carrier", "policy", "claims", "yes", "policy term"
    }:
        business_name = ""

    carrier_name = first_block.get("carrier_name") or _find_inline_value(
        [
            r"Carrier\s*[:\-]\s*(.*?)(?:\n|Policy\s*Number|Named\s*Insured|Policy\s*Term)",
            r"Insurance\s*Company\s*[:\-]\s*(.*?)(?:\n|Policy\s*Number|Named\s*Insured|Policy\s*Term)",
            r"Writing\s*Carrier\s*[:\-]\s*(.*?)(?:\n|Policy\s*Number|Named\s*Insured|Policy\s*Term)",
        ],
        text,
    )

    if carrier_name and carrier_name.lower() in {
        "carrier", "policy", "claims", "yes", "policy term"
    }:
        carrier_name = ""

    policy_positions = _find_policy_numbers(text)
    first_policy = first_block.get("policy_number") or (
        policy_positions[0][1] if policy_positions else ""
    )

    effective_date = ""
    expiration_date = ""
    policy_term = first_block.get("policy_term", "")
    term_match = re.search(
        r"([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})\s*[-\u2013]\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})",
        policy_term,
    )
    if not term_match:
        term_match = re.search(
            r"Policy\s*Term\s*[:\-]?\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})\s*[-\u2013]\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})",
            text,
            flags=re.IGNORECASE,
        )
    if term_match:
        effective_date = term_match.group(1)
        expiration_date = term_match.group(2)

    return {
        "business_name":