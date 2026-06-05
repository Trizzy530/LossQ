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
    "General Liability": ["general liability", "general liab", "liability", "gl", "premises"],
    "Workers Compensation": ["workers comp", "workers compensation", "work comp", "wc"],
    "Property": ["property"],
    "Motor Truck Cargo": ["motor truck cargo", "cargo"],
    "Inland Marine": ["inland marine", "equipment", "marine"],
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
]


def detect_lob(line: str) -> str:
    lower = clean_text(line).lower()

    for lob, keywords in LOB_KEYWORDS.items():
        if any(keyword in lower for keyword in keywords):
            return lob

    return "Policy"


def is_valid_policy_number(policy_number: str) -> bool:
    policy = normalize_policy_number(policy_number)

    if not policy:
        return False

    if len(policy) < 6:
        return False

    if any(word in policy for word in BAD_POLICY_WORDS):
        return False

    # Must contain letters and at least 3 digits.
    if not re.search(r"[A-Z]", policy):
        return False

    if not re.search(r"\d{3,}", policy):
        return False

    # Avoid pure date/page-looking values.
    if re.match(r"^20\d{2}-PAGE-\d+$", policy):
        return False

    if re.match(r"^PAGE-\d+$", policy):
        return False

    # Avoid obvious claim numbers.
    if re.match(r"^(GL|WC|CA|IM|CG|BI|PD|AL|PROP)-?\d{2,4}-?\d{3,}", policy, re.I):
        return False

    return True


def looks_like_policy_schedule_row(line: str) -> bool:
    lower = clean_text(line).lower()

    if not line:
        return False

    hard_excludes = [
        "generated:",
        "page ",
        "claim no",
        "claim number",
        "claim id",
        "detailed claims",
        "claim detail",
        "date of loss",
        "total claims",
        "open claims",
        "closed claims",
        "litigation",
        "underwriter note",
        "carrier comments",
        "renewal signal",
        "fax received",
    ]

    if any(term in lower for term in hard_excludes):
        return False

    candidates = extract_policy_candidates(line)
    if not candidates:
        return False

    has_lob = detect_lob(line) != "Policy"
    has_date = len(date_values(line)) >= 1
    has_schedule_words = any(
        word in lower
        for word in [
            "policy",
            "coverage",
            "lob",
            "effective",
            "expiration",
            "expired",
            "active",
            "sales",
            "payroll",
            "units",
            "equip",
        ]
    )

    return has_lob or has_date or has_schedule_words


def extract_policy_candidates(line: str) -> list[str]:
    candidates: list[str] = []

    for match in POLICY_PATTERN.findall(line or ""):
        policy = normalize_policy_number(match)

        if is_valid_policy_number(policy):
            candidates.append(policy)

    return candidates


def parse_policy_schedule(text: str, profile: dict | None = None) -> list[dict]:
    """
    Universal policy schedule parser V3.

    Detects policy schedule rows while rejecting headers, page numbers,
    dates, claim rows, subtotal rows, report text, and OCR noise.
    """

    profile = profile or {}
    lines = split_lines(text)
    policies: list[dict] = []
    seen: set[str] = set()

    for line in lines:
        if not looks_like_policy_schedule_row(line):
            continue

        candidates = extract_policy_candidates(line)
        if not candidates:
            continue

        dates = date_values(line)
        amounts = money_values(line)
        lob = detect_lob(line)

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
                "source_line": line[:700],
            }

            policies.append(policy)
            seen.add(policy_number)

    if not policies and profile.get("policy_number"):
        fallback_policy = normalize_policy_number(profile.get("policy_number"))

        if is_valid_policy_number(fallback_policy):
            policies.append(
                {
                    "policy_number": fallback_policy,
                    "policy_type": "Policy",
                    "line_coverage": "Policy",
                    "line_of_business": "Policy",
                    "writing_carrier": profile.get("writing_carrier") or profile.get("carrier_name") or "",
                    "carrier": profile.get("carrier_name") or profile.get("writing_carrier") or "",
                    "effective_date": profile.get("effective_date", ""),
                    "expiration_date": profile.get("expiration_date", ""),
                    "claim_count": 0,
                    "total_paid": 0,
                    "total_reserve": 0,
                    "total_incurred": 0,
                    "source_line": "Fallback from profile",
                }
            )

    return policies