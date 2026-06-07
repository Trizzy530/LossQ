"""
LossQ Loss Run Pipeline V2 — Phase 1 through Phase 3 foundation.

Drop-in purpose:
- Reads common PDF/Excel/CSV text/table outputs.
- Detects major carrier templates.
- Extracts account profile, policy schedule, claim rows, and totals.
- Runs validation so uncertain data is flagged instead of guessed.

Important:
This file is designed to be imported by your existing upload route. It does not
change auth, CORS, database models, or deployment settings.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .lossq_carrier_templates import detect_carrier, extract_policy_numbers, normalize_row
from .lossq_validation import number, validate_loss_run_payload

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None


COVERAGE_KEYWORDS = {
    "commercial auto": ["commercial auto", "business auto", "auto liability", "bap"],
    "general liability": ["general liability", "gl", "premises", "products completed"],
    "motor truck cargo": ["motor truck cargo", "cargo", "truck cargo"],
    "workers compensation": ["workers compensation", "workers comp", "wc", "work comp"],
    "property": ["property", "commercial property"],
    "umbrella": ["umbrella", "excess"],
}


def read_upload_bytes(filename: str, content: bytes) -> Tuple[str, List[Dict[str, Any]]]:
    suffix = Path(filename or "").suffix.lower()

    if suffix == ".pdf":
        return read_pdf_text(content), []

    if suffix in {".xlsx", ".xls"} and pd is not None:
        frames = pd.read_excel(io.BytesIO(content), sheet_name=None)
        rows: List[Dict[str, Any]] = []
        text_parts: List[str] = []
        for sheet_name, frame in frames.items():
            frame = frame.fillna("")
            text_parts.append(f"Sheet: {sheet_name}\n" + frame.to_string(index=False))
            rows.extend(frame.to_dict(orient="records"))
        return "\n".join(text_parts), rows

    if suffix == ".csv":
        decoded = content.decode("utf-8", errors="ignore")
        reader = csv.DictReader(io.StringIO(decoded))
        rows = list(reader)
        return decoded, rows

    return content.decode("utf-8", errors="ignore"), []


def read_pdf_text(content: bytes) -> str:
    if PdfReader is None:
        return content.decode("utf-8", errors="ignore")

    try:
        reader = PdfReader(io.BytesIO(content))
        text_parts = []
        for page in reader.pages:
            text_parts.append(page.extract_text() or "")
        return "\n".join(text_parts)
    except Exception:
        return content.decode("utf-8", errors="ignore")


def extract_profile(text: str, carrier_display_name: str) -> Dict[str, Any]:
    profile: Dict[str, Any] = {
        "carrier_name": carrier_display_name if carrier_display_name != "Generic Carrier" else "",
        "writing_carrier": carrier_display_name if carrier_display_name != "Generic Carrier" else "",
    }

    patterns = {
        "business_name": [
            r"(?:insured|named insured|account name|customer)\s*[:\-]\s*(.+)",
            r"loss runs?\s+for\s+(.+)",
        ],
        "account_number": [r"(?:account number|account no|customer number|customer no)\s*[:\-]\s*([A-Z0-9\-]+)"],
        "policy_number": [r"(?:policy number|policy no|account policy|policy)\s*[:\-]\s*([A-Z0-9\-]+)"],
        "effective_date": [r"(?:effective date|policy effective|from)\s*[:\-]\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})"],
        "expiration_date": [r"(?:expiration date|expiry date|policy expiration|to)\s*[:\-]\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})"],
        "agency_name": [r"(?:agency|producer|producing agency|broker)\s*[:\-]\s*(.+)"],
    }

    for field, field_patterns in patterns.items():
        for pattern in field_patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                value = clean_line(match.group(1))
                if value:
                    profile[field] = value[:120]
                    break

    if not profile.get("policy_number"):
        policies = extract_policy_numbers(text)
        account_like = [p for p in policies if "ACCT" in p]
        if account_like:
            profile["policy_number"] = account_like[0]
        elif policies:
            profile["policy_number"] = policies[0]

    if not profile.get("account_number") and profile.get("policy_number", "").upper().find("ACCT") >= 0:
        profile["account_number"] = profile["policy_number"]

    return profile


def clean_line(value: str) -> str:
    value = str(value or "").strip()
    value = re.sub(r"\s{2,}", " ", value)
    value = re.split(r"\s{3,}|\n", value)[0].strip()
    return value


def guess_coverage(line: str) -> str:
    lower = line.lower()
    for coverage, keywords in COVERAGE_KEYWORDS.items():
        if any(keyword in lower for keyword in keywords):
            return coverage.title()
    return ""


def extract_policy_schedule(text: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    policies: Dict[str, Dict[str, Any]] = {}

    # First pass: table rows from Excel/CSV.
    for raw in rows or []:
        row = normalize_row(raw)
        policy_number = str(row.get("policy_number") or "").strip().upper()
        if not policy_number:
            joined = " ".join(str(v) for v in raw.values())
            found = extract_policy_numbers(joined)
            policy_number = found[0] if found else ""
        if not policy_number:
            continue

        coverage = row.get("line_of_business") or guess_coverage(" ".join(str(v) for v in raw.values()))
        policies.setdefault(policy_number, {
            "policy_number": policy_number,
            "policy_type": coverage or "Needs Review",
            "line_of_business": coverage or "Needs Review",
            "writing_carrier": row.get("writing_carrier") or "",
            "carrier": row.get("carrier") or "",
            "effective_date": row.get("effective_date") or "",
            "expiration_date": row.get("expiration_date") or "",
            "claim_count": 0,
            "total_incurred": 0,
        })

    # Second pass: text lines from PDFs.
    for line in text.splitlines():
        found = extract_policy_numbers(line)
        coverage = guess_coverage(line)
        for policy_number in found:
            if "ACCT" in policy_number:
                continue
            policies.setdefault(policy_number, {
                "policy_number": policy_number,
                "policy_type": coverage or "Needs Review",
                "line_of_business": coverage or "Needs Review",
                "writing_carrier": "",
                "carrier": "",
                "effective_date": extract_first_date(line, 0),
                "expiration_date": extract_first_date(line, 1),
                "claim_count": 0,
                "total_incurred": 0,
            })
            if coverage and policies[policy_number].get("policy_type") == "Needs Review":
                policies[policy_number]["policy_type"] = coverage
                policies[policy_number]["line_of_business"] = coverage

    return list(policies.values())


def extract_first_date(text: str, index: int = 0) -> str:
    dates = re.findall(r"[0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4}", text or "")
    return dates[index] if len(dates) > index else ""


def extract_claims(text: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    claims: List[Dict[str, Any]] = []

    if rows:
        for raw in rows:
            row = normalize_row(raw)
            if not looks_like_claim_row(row):
                continue
            claim = normalize_claim(row)
            claims.append(claim)

    if claims:
        return claims

    # PDF/text fallback. This handles common row layouts where claim number,
    # policy number, dates, status, and money columns are on the same line.
    for line in text.splitlines():
        if not line.strip():
            continue

        cleaned_line = clean_line(line)

        # Skip document header/profile lines so they do not become fake claims.
        if re.search(
            r"^\s*(Policy\s*Number|PolicyNumber|ReportRunDate|Report\s*Run\s*Date|NamedInsured|Named\s+Insured|Page\s+\d+|PolicyTerm)\b",
            cleaned_line,
            flags=re.IGNORECASE,
        ):
            continue

        # Only parse lines that look like actual claim rows.
        if not re.search(
            r"(Claim\s*Number|ClaimNumber|Claim\s*#|CLM\s*#|AU-|GL-|WC-|AUTO|Collision|Property\s+damage)",
            cleaned_line,
            flags=re.IGNORECASE,
        ):
            continue

        if not re.search(r"\$?[0-9][0-9,]*(?:\.\d{2})?", cleaned_line):
            continue

        policy_numbers = [p for p in extract_policy_numbers(cleaned_line) if "ACCT" not in p]
        claim_number = extract_claim_number(cleaned_line)

        if not claim_number:
            continue

        amounts = extract_amounts(cleaned_line)
        paid = amounts[-3] if len(amounts) >= 3 else 0
        reserve = amounts[-2] if len(amounts) >= 2 else 0
        incurred = amounts[-1] if amounts else paid + reserve

        status = (
            "Open"
            if re.search(r"\b(open|pending|active)\b", cleaned_line, re.IGNORECASE)
            else "Closed"
            if re.search(r"\b(closed|close)\b", cleaned_line, re.IGNORECASE)
            else ""
        )

        coverage = guess_coverage(cleaned_line)

        claims.append({
            "claim_number": claim_number,
            "policy_number": policy_numbers[0] if policy_numbers else "",
            "line_of_business": coverage,
            "loss_date": extract_first_date(cleaned_line, 0),
            "reported_date": extract_first_date(cleaned_line, 1),
            "status": status,
            "paid_amount": paid,
            "reserve_amount": reserve,
            "total_incurred": incurred or paid + reserve,
            "description": cleaned_line[:500],
        })

    return claims

def looks_like_claim_row(row: Dict[str, Any]) -> bool:
    keys = set(row.keys())
    has_claim = bool(row.get("claim_number") or row.get("loss_date") or row.get("status"))
    has_money = any(number(row.get(k)) for k in ["paid_amount", "reserve_amount", "total_incurred"])
    has_policy = bool(row.get("policy_number") or row.get("line_of_business"))
    return has_claim and (has_money or has_policy or "claim_number" in keys)


def normalize_claim(row: Dict[str, Any]) -> Dict[str, Any]:
    paid = number(row.get("paid_amount") or row.get("paid"))
    reserve = number(row.get("reserve_amount") or row.get("reserve"))
    incurred = number(row.get("total_incurred") or row.get("incurred")) or paid + reserve

    return {
        "claim_number": str(row.get("claim_number") or "").strip(),
        "policy_number": str(row.get("policy_number") or "").strip().upper(),
        "line_of_business": str(row.get("line_of_business") or row.get("coverage") or "").strip(),
        "loss_date": str(row.get("loss_date") or row.get("date_of_loss") or "").strip(),
        "reported_date": str(row.get("reported_date") or "").strip(),
        "status": str(row.get("status") or "").strip(),
        "paid_amount": paid,
        "reserve_amount": reserve,
        "total_incurred": incurred,
        "claimant": str(row.get("claimant") or "").strip(),
        "description": str(row.get("description") or "").strip(),
    }


def extract_claim_number(line: str) -> str:
    cleaned = clean_line(line)

    # Do not treat policy/header lines as claim rows.
    header_only_patterns = [
        r"^\s*Policy\s*Number\s*:",
        r"^\s*PolicyNumber\s*:",
        r"^\s*ReportRunDate\s*:",
        r"^\s*Report\s*Run\s*Date\s*:",
        r"^\s*NamedInsured\s*:",
        r"^\s*Named\s+Insured\s*:",
        r"^\s*Page\s+\d+",
        r"^\s*PolicyTerm\b",
    ]

    if any(re.search(pattern, cleaned, flags=re.IGNORECASE) for pattern in header_only_patterns):
        return ""

    # Prefer explicit claim labels first.
    explicit_patterns = [
        r"(?:Claim\s*Number|ClaimNumber|Claim\s*#|CLM\s*#|Claim|CLM)\s*[:#\-]?\s*([A-Z]{0,6}-?[0-9][A-Z0-9\-]{4,})",
    ]

    for pattern in explicit_patterns:
        match = re.search(pattern, cleaned, flags=re.IGNORECASE)
        if match:
            value = str(match.group(1) or "").strip().upper()
            if value:
                return value

    # Fallback: claim-like IDs, but avoid plain policy numbers.
    fallback_patterns = [
        r"\b[A-Z]{1,6}-[0-9][A-Z0-9\-]{4,}\b",
        r"\b[0-9]{5,}-[0-9A-Z\-]{3,}\b",
    ]

    for pattern in fallback_patterns:
        match = re.search(pattern, cleaned, flags=re.IGNORECASE)
        if match:
            value = str(match.group(0) or "").strip().upper()
            if value:
                return value

    return ""

def extract_amounts(line: str) -> List[float]:
    values: List[float] = []
    for match in re.findall(r"\$?\(?[0-9][0-9,]*(?:\.\d{2})?\)?", line):
        negative = "(" in match and ")" in match
        value = number(match.replace("(", "").replace(")", ""))
        values.append(-value if negative else value)
    return values


def extract_document_totals(text: str) -> Dict[str, Any]:
    totals: Dict[str, Any] = {}
    for line in text.splitlines():
        lower = line.lower()
        if "total" in lower and "incurred" in lower:
            amounts = extract_amounts(line)
            if amounts:
                totals["total_incurred"] = amounts[-1]
        if "total" in lower and "claims" in lower:
            nums = re.findall(r"\b[0-9]+\b", line)
            if nums:
                totals["claim_count"] = int(nums[-1])
    return totals


def rollup_policy_schedule(policies: List[Dict[str, Any]], claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_policy = {str(p.get("policy_number") or "").strip().upper(): dict(p) for p in policies if p.get("policy_number")}

    for claim in claims:
        policy_number = str(claim.get("policy_number") or "").strip().upper()
        if not policy_number:
            continue
        by_policy.setdefault(policy_number, {
            "policy_number": policy_number,
            "policy_type": claim.get("line_of_business") or "Needs Review",
            "line_of_business": claim.get("line_of_business") or "Needs Review",
            "claim_count": 0,
            "total_incurred": 0,
        })
        by_policy[policy_number]["claim_count"] = int(by_policy[policy_number].get("claim_count") or 0) + 1
        by_policy[policy_number]["total_incurred"] = number(by_policy[policy_number].get("total_incurred")) + number(claim.get("total_incurred"))

    return list(by_policy.values())


def parse_loss_run_upload(filename: str, content: bytes) -> Dict[str, Any]:
    text, rows = read_upload_bytes(filename, content)
    carrier_template = detect_carrier(text)
    profile = extract_profile(text, carrier_template.display_name)
    policies = extract_policy_schedule(text, rows)
    claims = extract_claims(text, rows)
    policies = rollup_policy_schedule(policies, claims)
    document_totals = extract_document_totals(text)
    validation = validate_loss_run_payload(profile, policies, claims, document_totals)

    profile["policies"] = policies
    profile["validation"] = validation

    return {
        "carrier_template": carrier_template.carrier_key,
        "carrier_name": carrier_template.display_name,
        "profile": profile,
        "policies": policies,
        "claims": claims,
        "parsed_claims": claims,
        "document_totals": document_totals,
        "validation": validation,
        "claim_count": len(claims),
        "policy_count": len(policies),
        "total_incurred": validation.get("calculated_total_incurred", 0),
    }