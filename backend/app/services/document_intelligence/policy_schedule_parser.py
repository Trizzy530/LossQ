from __future__ import annotations

import re

from .utils import (
    clean_text,
    date_values,
    money_values,
    normalize_policy_number,
    split_lines,
)


LOB_KEYWORDS = {
    "Commercial Auto": ["commercial auto", "auto", "vehicle", "fleet", "truck"],
    "General Liability": ["general liability", "general liab", "liability", "gl"],
    "Workers Compensation": ["workers comp", "workers compensation", "work comp", "wc"],
    "Property": ["property"],
    "Motor Truck Cargo": ["motor truck cargo", "cargo"],
    "Inland Marine": ["inland marine", "equipment", "marine", "inland"],
    "Umbrella": ["umbrella", "excess"],
}


POLICY_PATTERN = re.compile(
    r"\b[A-Z]{1,6}[-\s]?[A-Z]{1,6}[-\s]?\d{3,8}(?:[-\s]?[A-Z0-9]{1,6})?\b",
    re.I,
)


BAD_POLICY_WORDS = [
    "PAGE",
    "GENERATED",
    "REPORT",
    "VALUATION",
    "TOTAL",
    "TOTALS",
    "SUBTOTAL",
    "SUMMARY",
    "CLAIM",
    "LOSS",
    "RUN",
    "COPY",
    "ACCOUNT",
]


def detect_lob(line: str) -> str:
    lower = clean_text(line).lower()

    for lob, keywords in LOB_KEYWORDS.items():
        if any(keyword in lower for keyword in keywords):
            return lob

    return "Policy"


def is_valid_policy_number(policy_number: str) -> bool:
    policy = normalize_policy_number(policy_number)

    if not policy or len(policy) < 6:
        return False

    if any(word in policy for word in BAD_POLICY_WORDS):
        return False

    if not re.search(r"[A-Z]", policy):
        return False

    if not re.search(r"\d{3,}", policy):
        return False

    if re.match(r"^20\d{2}-PAGE-\d+$", policy):
        return False

    if re.match(r"^PAGE-\d+$", policy):
        return False

    # Avoid obvious claim numbers.
    if re.match(r"^(GL|WC|CA|IM|CG|BI|PD|AL|PROP)-?\d{2,4}-?\d{3,}", policy, re.I):
        return False

    return True


def extract_policy_candidates(line: str) -> list[str]:
    candidates: list[str] = []

    for match in POLICY_PATTERN.findall(line or ""):
        policy = normalize_policy_number(match)

        if is_valid_policy_number(policy):
            candidates.append(policy)

    return candidates


def reconstruct_policy_rows(lines: list[str]) -> list[str]:
    """
    Reconstruct policy schedule rows from PDFs that extract table cells one-per-line.

    Looks for a policy number, then nearby LOB/date/currency/status lines.
    This is structure-based, not carrier-specific.
    """

    rows: list[str] = []
    used_indexes: set[int] = set()

    for index, line in enumerate(lines):
        candidates = extract_policy_candidates(line)

        if not candidates:
            continue

        policy_number = candidates[0]

        # Skip if this policy number appears inside claim detail context.
        before = " ".join(lines[max(0, index - 8):index]).lower()
        if "claim no" in before or "claim detail" in before or "detailed claims" in before:
            continue

        window = lines[index:min(len(lines), index + 8)]
        window_text = " ".join(window)

        lob = detect_lob(window_text)
        dates = date_values(window_text)

        # A policy schedule row should usually have a LOB or dates nearby.
        if lob == "Policy" and len(dates) == 0:
            continue

        rows.append(window_text)
        used_indexes.update(range(index, min(len(lines), index + 8)))

    return rows


def parse_policy_schedule(text: str, profile: dict | None = None) -> list[dict]:
    profile = profile or {}
    lines = split_lines(text)
    policies: list[dict] = []
    seen: set[str] = set()

    reconstructed_rows = reconstruct_policy_rows(lines)

    for row in reconstructed_rows:
        candidates = extract_policy_candidates(row)

        if not candidates:
            continue

        dates = date_values(row)
        amounts = money_values(row)
        lob = detect_lob(row)

        for policy_number in candidates:
            if policy_number in seen:
                continue

            policy = {
                "policy_number": policy_number,
                "policy_type": lob,
                "line_coverage": lob,
                "line_of_business": lob,
                "writing_carrier": profile.get("writing_carrier") or profile.get("carrier_name") or "",
                "carrier": profile.get("carrier_name") or profile.get("writing_carrier") or "",
                "effective_date": dates[0] if len(dates) >= 1 else profile.get("effective_date", ""),
                "expiration_date": dates[1] if len(dates) >= 2 else profile.get("expiration_date", ""),
                "claim_count": 0,
                "total_paid": amounts[-3] if len(amounts) >= 3 else 0,
                "total_reserve": amounts[-2] if len(amounts) >= 2 else 0,
                "total_incurred": amounts[-1] if len(amounts) >= 1 else 0,
                "source_line": row[:700],
            }

            policies.append(policy)
            seen.add(policy_number)

    return policies