from __future__ import annotations

import re

from .utils import clean_text, find_first, normalize_policy_number, parse_date, split_lines


BAD_PROFILE_VALUES = {
    "",
    "/ Co.",
    "/ Co",
    "Carrier / Co.",
    "Carrier / Co",
    "Co.",
    "Co",
    "LOB",
    "Policy #",
    "Policy",
    "Eff Date",
    "Exp Date",
    "Status",
}


CARRIER_WORDS = [
    "insurance",
    "ins.",
    "ins ",
    "mutual",
    "casualty",
    "indemnity",
    "risk",
    "assurance",
    "underwriters",
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
    "berkley",
    "cna",
    "zurich",
    "chubb",
    "aig",
    "hanover",
]


def is_bad_profile_value(value: str) -> bool:
    cleaned = clean_text(value)

    if cleaned in BAD_PROFILE_VALUES:
        return True

    lower = cleaned.lower()

    if lower in {v.lower() for v in BAD_PROFILE_VALUES}:
        return True

    if lower.startswith("carrier / co"):
        return True

    if lower in {"carrier", "writing carrier", "company", "co"}:
        return True

    return False


def looks_like_carrier_name(value: str) -> bool:
    cleaned = clean_text(value)

    if is_bad_profile_value(cleaned):
        return False

    lower = cleaned.lower()

    if len(cleaned) < 4:
        return False

    if any(word in lower for word in CARRIER_WORDS):
        return True

    if len(cleaned.split()) >= 2 and not any(
        bad in lower
        for bad in [
            "insured",
            "producer",
            "broker",
            "account",
            "valuation",
            "schedule",
            "policy",
            "claim",
            "loss run",
            "generated",
            "page",
            "detailed",
        ]
    ):
        return True

    return False


def carrier_from_policy_schedule(text: str) -> str:
    lines = split_lines(text)
    in_schedule = False

    for index, line in enumerate(lines):
        lower = line.lower()

        if "schedule of policies" in lower or "policy schedule" in lower:
            in_schedule = True
            continue

        if "detailed claims" in lower or "claim detail" in lower or "claim no" in lower:
            in_schedule = False

        if not in_schedule:
            continue

        if re.search(r"\b[A-Z]{1,6}[-\s]?[A-Z]{1,6}[-\s]?\d{3,8}(?:[-\s]?[A-Z0-9]{1,6})?\b", line, re.I):
            for back in range(index - 1, max(-1, index - 8), -1):
                candidate = clean_text(lines[back])
                if looks_like_carrier_name(candidate):
                    return candidate

    return ""


def extract_profile(text: str) -> dict:
    business_name = find_first(
        [
            r"\bInsured\s*:\s*([^|\n]+)",
            r"\bNamed Insured\s*[:\-]?\s*([^\n|]+)",
            r"\bAccount Name\s*[:\-]?\s*([^\n|]+)",
            r"\bACCT NAME\s*[:\-]?\s*([^\n|]+)",
        ],
        text,
    )

    agency_name = find_first(
        [
            r"\bProducer/Broker\s*:\s*([^\n]+?)(?:\s+Account\s+No|\s+Account\s+#|\n|$)",
            r"\bProducer\s*:\s*([^\n]+)",
            r"\bBroker\s*:\s*([^\n]+)",
            r"\bAgency\s*:\s*([^\n]+)",
        ],
        text,
    )

    account_number = find_first(
        [
            r"\bAccount\s+No\.?\s*:\s*([A-Z0-9\-]+)",
            r"\bAccount\s+#\s*:\s*([A-Z0-9\-]+)",
            r"\bCustomer\s+No\.?\s*:\s*([A-Z0-9\-]+)",
            r"\bRisk\s+ID\s*[:\-]?\s*([A-Z0-9\-]+)",
        ],
        text,
    )

    explicit_carrier = find_first(
        [
            r"\bWriting Carrier\s*:\s*([^\n|]+)",
            r"\bCarrier Name\s*:\s*([^\n|]+)",
            r"\bInsurance Carrier\s*:\s*([^\n|]+)",
            r"\bCarrier\s*:\s*([^\n|]+)",
        ],
        text,
    )

    schedule_carrier = carrier_from_policy_schedule(text)

    carrier_name = explicit_carrier if not is_bad_profile_value(explicit_carrier) else ""
    if not carrier_name:
        carrier_name = schedule_carrier

    policy_number = find_first(
        [
            r"\bPolicy\s*(?:Number|No\.?|#)\s*:\s*([A-Z0-9\-\s]+)",
            r"\bPolicy\s*#\s*([A-Z0-9\-\s]+)",
        ],
        text,
    )

    if is_bad_profile_value(policy_number):
        policy_number = ""

    effective_date_raw = find_first(
        [
            r"\bEffective Date\s*:\s*([0-9/\-.]+)",
            r"\bEff Date\s*:\s*([0-9/\-.]+)",
            r"\bPolicy Period\s*:\s*([0-9/\-.]+)\s*(?:to|-)",
        ],
        text,
    )

    expiration_date_raw = find_first(
        [
            r"\bExpiration Date\s*:\s*([0-9/\-.]+)",
            r"\bExp Date\s*:\s*([0-9/\-.]+)",
            r"\bPolicy Period\s*:\s*[0-9/\-.]+\s*(?:to|-)\s*([0-9/\-.]+)",
        ],
        text,
    )

    evaluation_date_raw = find_first(
        [
            r"\bValuation Date\s*:\s*([0-9/\-.]+)",
            r"\bVALUATION\s*[:\-]?\s*([0-9/\-.]+)",
            r"\bAs Of\s*:\s*([0-9/\-.]+)",
        ],
        text,
    )

    return {
        "business_name": clean_text(business_name),
        "carrier_name": clean_text(carrier_name),
        "writing_carrier": clean_text(carrier_name),
        "agency_name": clean_text(agency_name),
        "account_number": clean_text(account_number),
        "customer_number": clean_text(account_number),
        "producer_number": "",
        "policy_number": normalize_policy_number(policy_number),
        "effective_date": parse_date(effective_date_raw) or "",
        "expiration_date": parse_date(expiration_date_raw) or "",
        "evaluation_date": parse_date(evaluation_date_raw) or "",
    }
