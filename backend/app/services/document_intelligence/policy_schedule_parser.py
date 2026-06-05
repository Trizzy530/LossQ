from __future__ import annotations

import re

from .utils import (
    clean_text,
    date_values,
    money_values,
    normalize_policy_number,
    POLICY_RE,
    split_lines,
)


LOB_KEYWORDS = {
    "commercial auto": ["commercial auto", "auto", "vehicle", "fleet"],
    "general liability": ["general liability", "gl", "premises"],
    "workers comp": ["workers comp", "workers compensation", "wc", "work comp"],
    "property": ["property"],
    "cargo": ["cargo", "motor truck cargo"],
    "inland marine": ["inland marine", "equipment"],
    "umbrella": ["umbrella", "excess"],
}


def detect_lob(line: str) -> str:
    lower = clean_text(line).lower()

    for lob, keywords in LOB_KEYWORDS.items():
        if any(keyword in lower for keyword in keywords):
            return lob.title()

    return "Policy"


def parse_policy_schedule(text: str, profile: dict | None = None) -> list[dict]:
    """
    Universal policy schedule parser.

    It detects rows that contain:
    - policy number
    - line/coverage signal
    - effective and expiration dates when available
    - optional paid/reserve/incurred values
    """

    profile = profile or {}
    lines = split_lines(text)
    policies: list[dict] = []
    seen: set[str] = set()

    for line in lines:
        lower = line.lower()

        if "claim no" in lower or "claim number" in lower or "claim id" in lower:
            continue

        if not any(keyword in lower for keyword in ["policy", "coverage", "lob", "carrier", "effective", "expiration", "expired", "active", "auto", "liability", "comp", "cargo", "marine"]):
            continue

        candidates = POLICY_RE.findall(line)
        if not candidates:
            continue

        dates = date_values(line)
        amounts = money_values(line)

        for raw_policy in candidates:
            policy_number = normalize_policy_number(raw_policy)

            if not policy_number or len(policy_number) < 5:
                continue

            # Avoid treating claim numbers as policies in schedule context.
            if re.match(r"^(GL|WC|CA|IM|CG|AUTO)-?\d{2,4}-?\d{3,}", policy_number, re.I):
                continue

            if policy_number in seen:
                continue

            lob = detect_lob(line)

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
                "source_line": line[:600],
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