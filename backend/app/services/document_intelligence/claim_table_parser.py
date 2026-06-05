from __future__ import annotations

import re

from .policy_schedule_parser import detect_lob
from .utils import (
    CLAIM_RE,
    clean_text,
    date_values,
    looks_like_header_row,
    looks_like_total_row,
    money_values,
    normalize_claim_number,
    normalize_policy_number,
    split_lines,
)


CLAIM_PATTERN = CLAIM_RE


def detect_status(text: str) -> str:
    lower = clean_text(text).lower()

    if "closed" in lower or "resolved" in lower:
        return "Closed"

    if "open" in lower or "pending" in lower or "reopened" in lower:
        return "Open"

    return "Open"


def detect_litigation(text: str) -> bool:
    lower = clean_text(text).lower()

    if any(
        phrase in lower
        for phrase in [
            "no litigation",
            "closed no litigation",
            "litigation no",
            "no attorney",
            "no attorney involvement",
        ]
    ):
        return False

    return any(
        term in lower
        for term in ["litigation", "litigated", "attorney", "suit filed", "lawsuit", "represented"]
    )


def extract_claim_number(text: str) -> str:
    match = CLAIM_PATTERN.search(text or "")
    return normalize_claim_number(match.group(0)) if match else ""


def policy_lob_from_number(policy_number: str, policies: list[dict]) -> str:
    normalized = normalize_policy_number(policy_number)

    for policy in policies:
        if normalize_policy_number(policy.get("policy_number")) == normalized:
            return (
                policy.get("line_of_business")
                or policy.get("line_coverage")
                or policy.get("policy_type")
                or ""
            )

    return ""


def extract_policy_number(text: str, policies: list[dict]) -> str:
    compact_row = normalize_policy_number(text).replace("-", "")

    sorted_policies = sorted(
        [
            normalize_policy_number(policy.get("policy_number"))
            for policy in policies
            if policy.get("policy_number")
        ],
        key=len,
        reverse=True,
    )

    for policy_number in sorted_policies:
        if not policy_number:
            continue

        if policy_number in normalize_policy_number(text):
            return policy_number

        if policy_number.replace("-", "") in compact_row:
            return policy_number

    return ""


def assign_amounts(amounts: list[float]) -> tuple[float, float, float]:
    """
    Financial Column Mapping Engine V3.

    Standard order:
    Paid | Reserve | Total Incurred
    """

    if len(amounts) >= 3:
        return amounts[-3], amounts[-2], amounts[-1]

    if len(amounts) == 2:
        return amounts[-2], 0.0, amounts[-1]

    if len(amounts) == 1:
        return amounts[-1], 0.0, amounts[-1]

    return 0.0, 0.0, 0.0


def clean_description(row: str, claim_number: str, policy_number: str) -> str:
    desc = clean_text(row)

    for value in [claim_number, policy_number]:
        if value:
            desc = desc.replace(value, " ")
            desc = desc.replace(value.replace("-", " "), " ")

    desc = re.sub(r"\$[\s]*\d[\d,]*(?:\.\d{1,2})?", " ", desc)
    desc = re.sub(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", " ", desc)
    desc = re.sub(r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b", " ", desc)
    desc = re.sub(r"\b(CLOSED|OPEN|PENDING|RESOLVED)\*?\b", " ", desc, flags=re.I)
    desc = re.sub(r"\s+", " ", desc).strip(" -|")

    return desc[:700]


def is_claim_start(line: str) -> bool:
    return bool(CLAIM_PATTERN.search(line or ""))


def row_has_complete_financial_columns(row: str) -> bool:
    return len(money_values(row)) >= 3


def reconstruct_claim_rows(lines: list[str]) -> tuple[list[str], list[dict]]:
    rows: list[str] = []
    ignored_rows: list[dict] = []

    in_claims = False
    index = 0

    while index < len(lines):
        line = lines[index]
        lower = line.lower()

        if "detailed claims" in lower or "claim detail" in lower or "claim no" in lower:
            in_claims = True
            index += 1
            continue

        if "underwriter note" in lower or "carrier comments" in lower or "renewal signal" in lower:
            in_claims = False

        if looks_like_total_row(line) or looks_like_header_row(line):
            ignored_rows.append({"reason": "total_header_or_subtotal_row", "line": line[:700]})
            index += 1
            continue

        if not in_claims:
            index += 1
            continue

        if not is_claim_start(line):
            index += 1
            continue

        parts = [line]
        index += 1

        while index < len(lines):
            next_line = lines[index]
            next_lower = next_line.lower()

            if is_claim_start(next_line):
                break

            if "underwriter note" in next_lower or "carrier comments" in next_lower or "renewal signal" in next_lower:
                break

            if looks_like_total_row(next_line):
                ignored_rows.append({"reason": "total_or_subtotal_row", "line": next_line[:700]})
                break

            parts.append(next_line)
            joined = " ".join(parts)

            if row_has_complete_financial_columns(joined):
                index += 1
                break

            index += 1

        rows.append(" ".join(parts))

    return rows, ignored_rows


def parse_claims(
    text: str,
    policies: list[dict] | None = None,
    profile: dict | None = None,
) -> tuple[list[dict], list[dict]]:
    policies = policies or []
    profile = profile or {}

    lines = split_lines(text)
    rows, ignored_rows = reconstruct_claim_rows(lines)

    claims: list[dict] = []
    seen: set[str] = set()

    for row in rows:
        claim_number = extract_claim_number(row)

        if not claim_number:
            ignored_rows.append({"reason": "missing_claim_number", "line": row[:700]})
            continue

        if claim_number in seen:
            ignored_rows.append({"reason": "duplicate_claim_row", "line": row[:700]})
            continue

        dates = date_values(row)
        amounts = money_values(row)

        if len(dates) == 0 and len(amounts) < 2:
            ignored_rows.append({"reason": "insufficient_claim_context", "line": row[:700]})
            continue

        paid, reserve, incurred = assign_amounts(amounts)
        policy_number = extract_policy_number(row, policies)
        status = detect_status(row)
        litigation = detect_litigation(row)
        policy_lob = policy_lob_from_number(policy_number, policies)
        lob = policy_lob or detect_lob(row)

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
            "description": clean_description(row, claim_number, policy_number),
            "paid_amount": paid,
            "reserve_amount": reserve,
            "total_incurred": incurred,
            "litigation": litigation,
            "litigation_status": "Litigation/Attorney Indicator" if litigation else "",
            "attorney_assigned": litigation,
            "suit_filed": "suit filed" in row.lower() or "lawsuit" in row.lower(),
            "venue_state": "",
            "injury_type": "",
            "flag": "Litigation exposure" if litigation else "",
            "source_line": row[:700],
        }

        claims.append(claim)
        seen.add(claim_number)

    return claims, ignored_rows
