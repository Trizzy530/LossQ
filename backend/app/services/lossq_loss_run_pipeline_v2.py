from __future__ import annotations


import io
import re
from typing import Any, Dict, List, Tuple
from app.services.universal_lob import enrich_claims_with_universal_lob, enrich_claim_with_universal_lob


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
    standalone_re = re.compile(
        r"^\s*([A-Z]{2,6}-(?:AL|GL|WC|CG|CA|AUTO|CARGO|MT)-[A-Z0-9]+-\d{1,4})\s*$",
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


def _policy_by_prefix(claim_number: str, policy_positions: List[Tuple[int, str]]) -> str:
    """Use claim number prefix to find the best matching policy."""
    claim = claim_number.upper()
    candidates = [policy for _, policy in policy_positions]
    for policy in candidates:
        p = policy.upper()
        if claim.startswith("AL") and ("-AL-" in p or "-CA-" in p):
            return policy
        if claim.startswith("GL") and "-GL-" in p:
            return policy
        if claim.startswith("WC") and "-WC-" in p:
            return policy
        if claim.startswith(("CG", "MT")) and "-CG-" in p:
            return policy
    return ""


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
        "business_name": business_name,
        "carrier_name": carrier_name,
        "writing_carrier": carrier_name,
        "policy_number": first_policy,
        "account_number": first_policy,
        "customer_number": first_policy,
        "effective_date": effective_date,
        "expiration_date": expiration_date,
        "evaluation_date": "",
        "raw_text_preview": text[:2500],
    }


def _extract_claim_sections(
    text: str, fallback_policy: str
) -> List[Tuple[str, str, str]]:
    policy_positions = _find_policy_numbers(text)
    labeled_pattern = re.compile(
        r"Claim\s*Number\s*[:\-]?\s*(?:\n\s*)?"
        r"([A-Z]{1,6}-[A-Z0-9]{2,12}-[0-9]{2,12}"
        r"|[A-Z]{1,6}-[0-9]{4,12}"
        r"|[A-Z]{2,6}[0-9]{4,12})",
        flags=re.IGNORECASE,
    )
    standalone_pattern = re.compile(
        r"^\s*((?:AL|GL|WC|CG|MT|AU|CA)-\d{2}-\d{4,10}|(?:AL|GL|WC|CG|MT|AU|CA)-[0-9]{4,10}-[0-9]{1,6})\s*$",
        flags=re.IGNORECASE | re.MULTILINE,
    )
    all_matches = []
    for m in labeled_pattern.finditer(text):
        all_matches.append(m)
    for m in standalone_pattern.finditer(text):
        already = any(
            abs(m.start() - existing.start()) < 50 for existing in all_matches
        )
        if not already:
            all_matches.append(m)
    all_matches.sort(key=lambda m: m.start())
    sections: List[Tuple[str, str, str]] = []
    for index, match in enumerate(all_matches):
        raw_claim = _clean(match.group(1)).upper().replace(" ", "-")
        claim_number = re.sub(r"-{2,}", "-", raw_claim).strip("-")
        if not _looks_like_real_claim_number(claim_number):
            continue
        start = match.start()
        end = (
            all_matches[index + 1].start()
            if index + 1 < len(all_matches)
            else min(len(text), start + 2500)
        )
        section = text[start:end]
        policy_number = _nearest_policy_before(
            policy_positions, start, fallback_policy
        )
        if not _looks_like_policy(policy_number):
            policy_number = fallback_policy
        # Override with prefix-based match when available - more reliable than position
        prefix_match = _policy_by_prefix(claim_number, policy_positions)
        if prefix_match:
            policy_number = prefix_match
        sections.append((claim_number, policy_number, section))
    return sections


def _extract_amounts_from_section(section: str) -> List[float]:
    values: List[float] = []
    for raw in re.findall(
        r"\$\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})|[0-9]+(?:\.[0-9]{2}))",
        section,
    ):
        amount = _money_to_float(raw)
        if amount > 0:
            values.append(amount)
    return values


def _extract_date(section: str, label: str) -> str:
    match = re.search(
        rf"{re.escape(label)}\s*[:\-]?\s*(?:\n\s*)?([0-9]{{1,2}}/[0-9]{{1,2}}/[0-9]{{2,4}})",
        section,
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else ""


def _extract_status(section: str) -> str:
    match = re.search(
        r"Status\s*of\s*Loss\s*[:\-]?\s*(?:\n\s*)?([A-Za-z]+)",
        section,
        flags=re.IGNORECASE,
    )
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
        r"Description\s*of\s*Loss\s*[:\-]?\s*(.*?)(?:Claimant\s+Type\s+Of\s+Loss|Claimant\s+TypeOfLoss|Claimant\s*\n|$)",
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
        return "Motor Truck Cargo"
    if claim_upper.startswith("GL") or "general liability" in section_lower:
        return "General Liability"
    if (
        claim_upper.startswith("AL")
        or claim_upper.startswith("AU")
        or claim_upper.startswith("CA")
        or "collision" in section_lower
        or "vehicle" in section_lower
        or "auto" in section_lower
    ):
        return "Auto Liability"
    if "property damage" in section_lower:
        return "General Liability"
    return "Unknown"


def _extract_claims(text: str, fallback_policy: str) -> List[Dict[str, Any]]:
    claims: List[Dict[str, Any]] = []
    for claim_number, policy_number, section in _extract_claim_sections(
        text, fallback_policy
    ):
        amounts = _extract_amounts_from_section(section)
        total_incurred = amounts[-1] if amounts else 0.0
        paid_amount = amounts[0] if amounts else 0.0
        reserve_amount = 0.0
        status = _extract_status(section)
        if status.lower() == "open" and total_incurred > paid_amount:
            reserve_amount = round(total_incurred - paid_amount, 2)
        claims.append({
            "claim_number": claim_number,
            "policy_number": policy_number,
            "line_of_business": _infer_lob(section, claim_number),
            "loss_date": _extract_date(section, "Loss Date"),
            "date_of_loss": _extract_date(section, "Loss Date"),
            "reported_date": _extract_date(section, "Loss Report Date"),
            "date_reported": _extract_date(section, "Loss Report Date"),
            "status": status,
            "paid_amount": paid_amount,
            "reserve_amount": reserve_amount,
            "total_incurred": total_incurred,
            "description": _extract_description(section),
        })
    return enrich_claims_with_universal_lob(claims)


def _policy_rollup(claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for claim in claims:
        policy_number = _normalize_policy(claim.get("policy_number"))
        if not _looks_like_policy(policy_number):
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
        grouped[policy_number]["total_incurred"] += _money_to_float(
            claim.get("total_incurred")
        )
    return list(grouped.values())


def parse_loss_run_upload(filename: str, content: bytes) -> Dict[str, Any]:
    text = _extract_text_from_pdf(content)
    profile = _extract_profile(text)
    fallback_policy = profile.get("policy_number") or ""
    claims = _extract_claims(text, fallback_policy)
    if not profile.get("policy_number") and claims:
        profile["policy_number"] = claims[0].get("policy_number", "")
        profile["account_number"] = profile["policy_number"]
        profile["customer_number"] = profile["policy_number"]
    policies = _policy_rollup(claims)
    total_incurred = round(
        sum(_money_to_float(c.get("total_incurred")) for c in claims), 2
    )
    validation = {
        "is_valid": bool(claims),
        "confidence_score": 92 if claims else 40,
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




