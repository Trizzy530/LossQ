from __future__ import annotations

import re

from .policy_schedule_parser import detect_lob
from .utils import (
    clean_text,
    date_values,
    looks_like_header_row,
    looks_like_total_row,
    money_values,
    normalize_claim_number,
    normalize_policy_number,
    split_lines,
)


CLAIM_PATTERN = re.compile(
    r"\b(?:GL|WC|CA|IM|CG|AUTO|AL|BI|PD|PROP)[-\s]?\d{2,4}[-\s]?[A-Z0-9]{3,8}\??\b",
    re.I,
)

POLICY_PATTERN = re.compile(
    r"\b(?:[A-Z]{1,6}[-\s]?[A-Z]{1,6}[-\s]?\d{3,8}(?:[-\s]?[A-Z0-9]{1,6})?|\d{3,8}[-\s]?[A-Z]{1,5}[-\s]?\d{1,6})\b",
    re.I,
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


def extract_claim_number(line: str) -> str:
    matches = CLAIM_PATTERN.findall(line or "")

    if not matches:
        return ""

    return normalize_claim_number(matches[0])


def normalize_compact(value: str) -> str:
    return normalize_policy_number(value).replace("-", "")


def extract_policy_number(line: str, policies: list[dict]) -> str:
    clean_line = clean_text(line)
    compact_line = normalize_compact(clean_line)

    known_policies = [
        normalize_policy_number(policy.get("policy_number"))
        for policy in policies
        if policy.get("policy_number")
    ]

    for policy_number in known_policies:
        if not policy_number:
            continue

        if policy_number in normalize_policy_number(clean_line):
            return policy_number

        if normalize_compact(policy_number) in compact_line:
            return policy_number

    candidates = POLICY_PATTERN.findall(clean_line)

    for candidate in candidates:
        policy_number = normalize_policy_number(candidate)

        if not policy_number:
            continue

        # Skip obvious claim IDs.
        if CLAIM_PATTERN.search(policy_number):
            continue

        if re.search(r"\d{3,}", policy_number):
            return policy_number

    return known_policies[0] if len(known_policies) == 1 else ""


def clean_description(line: str, claim_number: str, policy_number: str) -> str:
    desc = clean_text(line)

    for value in [claim_number, policy_number]:
        if value:
            desc = desc.replace(value, " ")
            desc = desc.replace(value.replace("-", " "), " ")

    desc = re.sub(r"\$?\(?\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?\)?", " ", desc)
    desc = re.sub(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", " ", desc)
    desc = re.sub(r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b", " ", desc)
    desc = re.sub(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b", " ", desc)
    desc = re.sub(r"\s+", " ", desc).strip(" -|")

    return desc[:700]


def line_has_claim_signal(line: str) -> bool:
    if not line:
        return False

    if looks_like_total_row(line) or looks_like_header_row(line):
        return False

    if not CLAIM_PATTERN.search(line):
        return False

    has_money = len(money_values(line)) >= 1
    has_date = len(date_values(line)) >= 1

    return has_money or has_date


def assign_amounts(amounts: list[float]) -> tuple[float, float, float]:
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
    else:
        paid = 0.0
        reserve = 0.0
        incurred = 0.0

    if incurred == 0 and (paid or reserve):
        incurred = paid + reserve

    return paid, reserve, incurred


def parse_claims(
    text: str,
    policies: list[dict] | None = None,
    profile: dict | None = None,
) -> tuple[list[dict], list[dict]]:
    """
    Universal claim row parser V2.

    It is not hardcoded to one carrier or file. It detects:
    - claim IDs by common insurance claim-number patterns
    - dates
    - money columns
    - claim status
    - litigation indicators
    - policy numbers by known policy schedule matching
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
            ignored_rows.append({"reason": "total_or_subtotal_row", "line": line[:700]})
            continue

        if looks_like_header_row(line):
            ignored_rows.append({"reason": "header_row", "line": line[:700]})
            continue

        if not line_has_claim_signal(line):
            continue

        claim_number = extract_claim_number(line)

        if not claim_number:
            ignored_rows.append({"reason": "missing_claim_number", "line": line[:700]})
            continue

        dates = date_values(line)
        amounts = money_values(line)
        paid, reserve, incurred = assign_amounts(amounts)

        policy_number = extract_policy_number(line, policies)

        dedupe_key = f"{claim_number}|{policy_number}|{dates[0] if dates else ''}|{incurred}"

        if dedupe_key in seen:
            ignored_rows.append({"reason": "duplicate_claim_row", "line": line[:700]})
            continue

        seen.add(dedupe_key)

        lob = detect_lob(line)
        status = detect_status(line)
        litigation = detect_litigation(line)

        claim = {
            "claim_number": claim_number,
            "policy_number": policy_number or profile.get("policy_number") or "",
            "line_of_business": lob,
            "claim_type": lob,
            "cause_of_loss": "",
            "claimant_type": "",
            "date_of_loss": dates[0] if len(dates) >= 1 else None,
            "date_reported": dates[1] if len(dates) >= 2 else None,
            "date_closed": None,
            "status": status,
            "description": clean_description(line, claim_number, policy_number),
            "paid_amount": paid,
            "reserve_amount": reserve,
            "total_incurred": incurred,
            "litigation": litigation,
            "litigation_status": "Litigation/Attorney Indicator" if litigation else "",
            "attorney_assigned": litigation,
            "suit_filed": "suit filed" in line.lower() or "lawsuit" in line.lower(),
            "venue_state": "",
            "injury_type": "",
            "flag": "Litigation exposure" if litigation else "",
            "source_line": line[:700],
        }

        claims.append(claim)

    return claims, ignored_rows