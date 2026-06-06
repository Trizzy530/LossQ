from __future__ import annotations

import re

from .utils import clean_text, date_values, normalize_policy_number, split_lines


LOB_KEYWORDS = {
    "Commercial Auto": ["commercial auto", "business auto", "auto", "vehicle", "fleet", "truck"],
    "General Liability": ["general liability", "general liab", "liability", "gl"],
    "Workers Compensation": ["workers compensation", "workers comp", "work comp", "wc"],
    "Motor Truck Cargo": ["motor truck cargo", "cargo"],
    "Inland Marine": ["inland marine", "equipment", "marine", "inland"],
    "Property": ["property package", "property"],
    "Umbrella": ["umbrella", "excess"],
}

POLICY_PATTERN = re.compile(
    r"\b[A-Z]{2,8}[-\s]?[A-Z]{1,6}[-\s]?\d{3,8}(?:[-\s]?[A-Z0-9]{1,6})?\b",
    re.I,
)


def detect_lob(text: str) -> str:
    lower = clean_text(text).lower()
    for lob, keywords in LOB_KEYWORDS.items():
        if any(keyword in lower for keyword in keywords):
            return lob
    return "Policy"


def is_valid_policy_number(value: str) -> bool:
    policy = normalize_policy_number(value)

    if not policy or len(policy) < 6:
        return False

    if policy in {"LOB", "POLICY", "ACCOUNT"}:
        return False

    if policy.startswith("QC-"):
        return False

    if re.search(r"(PAGE|GENERATED|REPORT|TOTAL|SUBTOTAL|SUMMARY|CLAIM|LOSS|COPY)", policy):
        return False

    if re.match(r"^(GL|WC|CA|IM|CG|AUTO|AL|BI|PD|PROP)-?\d{2,4}-?\d{3,}", policy, re.I):
        return False

    if not re.search(r"[A-Z]", policy) or not re.search(r"\d{3,}", policy):
        return False

    return True


def extract_policy_number(line: str) -> str:
    for match in POLICY_PATTERN.findall(line or ""):
        policy = normalize_policy_number(match)
        if is_valid_policy_number(policy):
            return policy
    return ""


def looks_like_carrier_name(value: str) -> bool:
    cleaned = clean_text(value)
    lower = cleaned.lower()

    if not cleaned or cleaned in {"Carrier / Co.", "/ Co.", "Policy #", "Policy Number", "LOB", "Eff Date", "Exp Date", "Status"}:
        return False

    if any(
        bad in lower
        for bad in [
            "schedule",
            "policy",
            "claim",
            "loss run",
            "generated",
            "page",
            "detailed",
            "expired",
            "active",
            "sales",
            "payroll",
            "units",
            "equip",
        ]
    ):
        return False

    carrier_words = [
        "insurance",
        "ins.",
        "mutual",
        "casualty",
        "western",
        "harbor",
        "builders",
        "atlantic",
        "continental",
        "liberty",
        "summit",
        "travelers",
        "hartford",
        "progressive",
        "national general",
        "preferred",
        "berkley",
        "cna",
        "zurich",
        "chubb",
        "aig",
        "hanover",
    ]

    return any(word in lower for word in carrier_words) or len(cleaned.split()) >= 2


def nearest_carrier_before(lines: list[str], index: int) -> str:
    for back in range(index - 1, max(-1, index - 8), -1):
        candidate = clean_text(lines[back])
        if looks_like_carrier_name(candidate):
            return candidate
    return ""


def parse_policy_schedule(text: str, profile: dict | None = None) -> list[dict]:
    profile = profile or {}
    lines = split_lines(text)

    policies: list[dict] = []
    seen: set[str] = set()

    in_schedule = False
    index = 0

    while index < len(lines):
        line = lines[index]
        lower = line.lower()

        if "policy schedule" in lower or "schedule of policies" in lower:
            in_schedule = True
            index += 1
            continue

        if "claim summary" in lower or "detailed claims" in lower or "claim detail" in lower or "claim no" in lower or "claim #" in lower:
            in_schedule = False

        if not in_schedule:
            index += 1
            continue

        policy_number = extract_policy_number(line)

        if not policy_number:
            index += 1
            continue

        window = lines[index:min(index + 7, len(lines))]
        row_text = " ".join(window)

        lob = detect_lob(row_text)
        dates = date_values(row_text)
        carrier_name = nearest_carrier_before(lines, index) or profile.get("writing_carrier") or profile.get("carrier_name") or ""

        if lob == "Policy" and len(dates) == 0:
            index += 1
            continue

        if policy_number not in seen:
            policies.append(
                {
                    "policy_number": policy_number,
                    "policy_type": lob,
                    "line_coverage": lob,
                    "line_of_business": lob,
                    "writing_carrier": carrier_name,
                    "carrier": carrier_name,
                    "effective_date": dates[0] if len(dates) >= 1 else profile.get("effective_date", ""),
                    "expiration_date": dates[1] if len(dates) >= 2 else profile.get("expiration_date", ""),
                    "claim_count": 0,
                    "total_paid": 0,
                    "total_reserve": 0,
                    "total_incurred": 0,
                    "source_line": row_text[:700],
                }
            )
            seen.add(policy_number)

        index += 1

    return policies
