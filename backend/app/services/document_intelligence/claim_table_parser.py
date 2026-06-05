from __future__ import annotations

import re

from .policy_schedule_parser import detect_lob
from .utils import (
    CLAIM_RE,
    POLICY_RE,
    clean_text,
    date_values,
    line_has_claim_signal,
    looks_like_header_row,
    looks_like_total_row,
    money_values,
    normalize_claim_number,
    normalize_policy_number,
    split_lines,
)


def detect_status(line: str) -> str:
    lower = clean_text(line).lower()

    if "closed" in lower or "resolved" in lower:
        return "Closed"

    if "open" in lower or "pending" in lower or "reopened" in lower:
        return "Open"

    return "Open"


def detect_litigation(line: str) -> bool:
    lower = clean_text(line).lower()
    return any(
        term in lower
        for term in [
            "litigation",
            "litigated",
            "attorney",
            "suit filed",
            "lawsuit",
            "represented",
        ]
    )


def clean_description(line: str, claim_number: str, policy_number: str) -> str:
    desc = clean_text(line)

    if claim_number:
        desc = desc.replace(claim_number, "")
        desc = desc.replace(claim_number.replace("-", " "), "")

    if policy_number:
        desc = desc.replace(policy_number, "")
        desc = desc.replace(policy_number.replace("-", " "), "")

    desc = re.sub(r"\$?\(?\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?\)?", " ", desc)
    desc = re.sub(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", " ", desc)
    desc = re.sub(r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b", " ", desc)
    desc = re.sub(r"\s+", " ", desc).strip(" -|")

    return desc[:700]


def extract_claim_number(line: str) -> str:
    matches = CLAIM_RE.findall(line or "")

    if not matches:
        return ""

    # Prefer values that look like normal claim IDs and not policy IDs.
    for match in matches:
        normalized = normalize_claim_number(match)
        if re.match(r"^(GL|WC|CA|IM|CG|AUTO|AL|BI|PD|PROP)[-\dA-Z]+", normalized, re.I):
            return normalized

    return normalize_claim_number(matches[0])


def extract_policy_number(line: str, policies: list[dict]) -> str:
    known_policies = [
        normalize_policy_number(policy.get("policy_number"))
        for policy in policies
        if policy.get("policy_number")
    ]

    normalized_line = normalize_policy_number(line)

    for policy_number in known_policies:
        if policy_number and policy_number in normalized_line:
            return policy_number

    candidates = POLICY_RE.findall(line or "")

    for candidate in candidates:
        policy_number = normalize_policy_number(candidate)

        # Skip obvious claim-number patterns.
        if re.match(r"^(GL|WC|CA|IM|CG|AUTO)-?\d{2,4}-?\d{3,}", policy_number, re.I):
            continue

        if policy_number:
            return policy_number

    return known_policies[0] if len(known_policies) == 1 else ""


def parse_claims(text: str, policies: list[dict] | None = None, profile: dict | None = None) -> tuple[list[dict], list[dict]]:
    """
    Universal claim row parser.

    It detects claims using structural signals:
    - claim number pattern
    - date of loss
    - money columns
    - policy number when available
    - status/litigation text
    """

    policies = policies or []
    profile = profile or {}
    lines = split_lines(text)
    claims: list[dict] = []
    ignored_rows: list[dict] = []
    seen: set[str] = set()

    for line in lines:
        if not line:
            continue

        if looks_like_total_row(line):
            ignored_rows.append({"reason": "total_or_subtotal_row", "line": line[:600]})
            continue

        if looks_like_header_row(line):
            ignored_rows.append({"reason": "header_row", "line": line[:600]})
            continue

        if not line_has_claim_signal(line):
            continue

        claim_number = extract_claim_number(line)

        if not claim_number:
            ignored_rows.append({"reason": "missing_claim_number", "line": line[:600]})
            continue

        dates = date_values(line)
        amounts = money_values(line)

        paid = 0.0
        reserve = 0.0
        incurred = 0.0

        if len(amounts) >= 3:
            paid = amounts[-3]
            reserve = amounts[-2]
            incurred = amounts[-1]
        elif len(amounts) == 2:
            paid = amounts[-2]
            reserve = 0.0
            incurred = amounts[-1]
        elif len(amounts) == 1:
            paid = amounts[-1]
            reserve = 0.0
            incurred = amounts[-1]

        if incurred == 0 and (paid or reserve):
            incurred = paid + reserve

        policy_number = extract_policy_number(line, policies)

        dedupe_key = f"{claim_number}|{policy_number}|{dates[0] if dates else ''}|{incurred}"

        if dedupe_key in seen:
            ignored_rows.append({"reason": "duplicate_claim_row", "line": line[:600]})
            continue

        seen.add(dedupe_key)

        line_of_business = detect_lob(line)

        claim = {
            "claim_number": claim_number,
            "policy_number": policy_number or profile.get("policy_number") or "",
            "line_of_business": line_of_business,
            "claim_type": line_of_business,
            "cause_of_loss": "",
            "claimant_type": "",
            "date_of_loss": dates[0] if len(dates) >= 1 else None,
            "date_reported": dates[1] if len(dates) >= 2 else None,
            "date_closed": None,
            "status": detect_status(line),
            "description": clean_description(line, claim_number, policy_number),
            "paid_amount": paid,
            "reserve_amount": reserve,
            "total_incurred": incurred,
            "litigation": detect_litigation(line),
            "litigation_status": "Litigation/Attorney Indicator" if detect_litigation(line) else "",
            "attorney_assigned": detect_litigation(line),
            "suit_filed": "suit filed" in line.lower() or "lawsuit" in line.lower(),
            "venue_state": "",
            "injury_type": "",
            "flag": "",
            "source_line": line[:700],
        }

        claims.append(claim)

    return claims, ignored_rows