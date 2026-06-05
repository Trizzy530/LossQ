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


def detect_status(text: str) -> str:
    lower = clean_text(text).lower()

    if "closed" in lower or "resolved" in lower:
        return "Closed"

    if "open" in lower or "pending" in lower or "reopened" in lower:
        return "Open"

    return "Open"


def detect_litigation(text: str) -> bool:
    lower = clean_text(text).lower()

    no_litigation_phrases = [
        "no litigation",
        "litigation no",
        "no litigated",
        "no attorney",
        "no attorney involvement",
    ]

    if any(phrase in lower for phrase in no_litigation_phrases):
        return False

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


def extract_claim_number(text: str) -> str:
    matches = CLAIM_PATTERN.findall(text or "")

    if not matches:
        return ""

    return normalize_claim_number(matches[0])


def normalize_compact(value: str) -> str:
    return normalize_policy_number(value).replace("-", "")


def extract_policy_number(text: str, policies: list[dict]) -> str:
    clean = clean_text(text)
    compact = normalize_compact(clean)

    known_policies = [
        normalize_policy_number(policy.get("policy_number"))
        for policy in policies
        if policy.get("policy_number")
    ]

    for policy_number in known_policies:
        if not policy_number:
            continue

        if policy_number in normalize_policy_number(clean):
            return policy_number

        if normalize_compact(policy_number) in compact:
            return policy_number

    return ""


def clean_description(row: str, claim_number: str, policy_number: str) -> str:
    desc = clean_text(row)

    for value in [claim_number, policy_number]:
        if value:
            desc = desc.replace(value, " ")
            desc = desc.replace(value.replace("-", " "), " ")

    desc = re.sub(r"\$?\(?\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?\)?", " ", desc)
    desc = re.sub(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", " ", desc)
    desc = re.sub(r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b", " ", desc)
    desc = re.sub(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b", " ", desc)
    desc = re.sub(r"\b(CLOSED|OPEN|PENDING|RESOLVED)\*?\b", " ", desc, flags=re.I)
    desc = re.sub(r"\s+", " ", desc).strip(" -|")

    return desc[:700]


def assign_amounts(amounts: list[float]) -> tuple[float, float, float]:
    """
    Use the last three money values as paid/reserve/incurred.
    This avoids accidentally using claim number or policy number digits.
    """

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


def reconstruct_claim_rows(lines: list[str]) -> tuple[list[str], list[dict]]:
    """
    Reconstruct claim table rows from PDFs that extract each table cell as a new line.

    Starts when a claim number appears, then gathers nearby policy/date/description/status/money
    lines until the next claim number or subtotal/total section.
    """

    rows: list[str] = []
    ignored_rows: list[dict] = []

    index = 0

    while index < len(lines):
        line = lines[index]

        if looks_like_total_row(line):
            ignored_rows.append({"reason": "total_or_subtotal_row", "line": line[:700]})
            index += 1
            continue

        if looks_like_header_row(line):
            ignored_rows.append({"reason": "header_row", "line": line[:700]})
            index += 1
            continue

        if not CLAIM_PATTERN.search(line):
            index += 1
            continue

        # Ignore policy schedule values that are not real claim numbers.
        claim_number = extract_claim_number(line)
        if not claim_number:
            index += 1
            continue

        parts = [line]
        index += 1

        while index < len(lines):
            next_line = lines[index]

            if looks_like_total_row(next_line):
                ignored_rows.append({"reason": "total_or_subtotal_row", "line": next_line[:700]})
                break

            if CLAIM_PATTERN.search(next_line):
                break

            parts.append(next_line)

            # Most claim rows should have at least 3 money values by the end.
            joined = " ".join(parts)
            if len(money_values(joined)) >= 3 and detect_status(joined) in ["Closed", "Open"]:
                # Continue a little only if next lines look like money/noise, otherwise stop.
                if index + 1 < len(lines) and not CLAIM_PATTERN.search(lines[index + 1]):
                    lookahead = clean_text(lines[index + 1]).lower()
                    if not any(token in lookahead for token in ["$", "0.00", "closed", "open"]):
                        pass
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
    reconstructed_rows, ignored_rows = reconstruct_claim_rows(lines)

    claims: list[dict] = []
    seen_claim_numbers: set[str] = set()

    for row in reconstructed_rows:
        if looks_like_total_row(row) or looks_like_header_row(row):
            ignored_rows.append({"reason": "non_claim_row", "line": row[:700]})
            continue

        claim_number = extract_claim_number(row)

        if not claim_number:
            ignored_rows.append({"reason": "missing_claim_number", "line": row[:700]})
            continue

        # If this is a duplicate supplement row, skip it.
        if claim_number in seen_claim_numbers:
            ignored_rows.append({"reason": "duplicate_claim_row", "line": row[:700]})
            continue

        dates = date_values(row)
        amounts = money_values(row)

        # A real claim row needs claim number + date or money.
        if len(dates) == 0 and len(amounts) < 2:
            ignored_rows.append({"reason": "insufficient_claim_row_context", "line": row[:700]})
            continue

        paid, reserve, incurred = assign_amounts(amounts)
        policy_number = extract_policy_number(row, policies)
        lob = detect_lob(row)
        status = detect_status(row)
        litigation = detect_litigation(row)

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
        seen_claim_numbers.add(claim_number)

    return claims, ignored_rows