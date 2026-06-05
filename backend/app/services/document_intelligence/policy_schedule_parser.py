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
    r"\b(?:[A-Z]{1,6}[-\s]?[A-Z]{1,6}[-\s]?\d{3,8}(?:[-\s]?[A-Z0-9]{1,6})?|\d{3,8}[-\s]?[A-Z]{1,5}[-\s]?\d{1,6})\b",
    re.I,
)


def detect_lob(line: str) -> str:
    lower = clean_text(line).lower()

    for lob, keywords in LOB_KEYWORDS.items():
        if any(keyword in lower for keyword in keywords):
            return lob

    return "Policy"


def looks_like_policy_schedule_row(line: str) -> bool:
    lower = clean_text(line).lower()

    if not line:
        return False

    if "claim no" in lower or "claim number" in lower or "claim id" in lower:
        return False

    if "detailed claims" in lower or "claim detail" in lower:
        return False

    has_policy_like_value = bool(POLICY_PATTERN.search(line))
    has_lob = detect_lob(line) != "Policy"
    has_date = len(date_values(line)) >= 1
    has_schedule_words = any(
        word in lower
        for word in [
            "carrier",
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

    return has_policy_like_value and (has_lob or has_date or has_schedule_words)


def extract_policy_candidates(line: str) -> list[str]:
    candidates = []

    for match in POLICY_PATTERN.findall(line or ""):
        policy = normalize_policy_number(match)

        if not policy:
            continue

        # Avoid obvious claim numbers.
        if re.match(r"^(GL|WC|CA|IM|CG|BI|PD|AL|PROP)-?\d{2,4}-?\d{3,}", policy, re.I):
            continue

        # Avoid carrier abbreviations without enough numeric content.
        if not re.search(r"\d{3,}", policy):
            continue

        candidates.append(policy)

    return candidates


def parse_policy_schedule(text: str, profile: dict | None = None) -> list[dict]:
    """
    Universal policy schedule parser V2.

    This parser is intentionally structural, not carrier-specific.
    It looks for policy-number-like values inside rows that also contain
    line of business, date, schedule, payroll/sales/unit, or carrier context.
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
        policies.append(
            {
                "policy_number": normalize_policy_number(profile.get("policy_number")),
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