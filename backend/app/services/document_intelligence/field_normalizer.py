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
    
    "builders",
    "atlantic",
    "continental",
    "liberty",
    "summit",
    "preferred",
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


def clean_policy_value(value: str) -> str:
    raw = clean_text(value)

    if not raw:
        return ""

    raw = re.split(
        r"\b(?:policy period|effective|expiration|eff date|exp date|carrier|insured|producer|broker|valuation|report date|status|premium|line of business|lob|page)\b",
        raw,
        maxsplit=1,
        flags=re.I,
    )[0]

    raw = raw.strip(" :-|")

    policy = normalize_policy_number(raw)

    if not policy:
        return ""

    if policy in {"LOB", "POLICY", "POLICY-PERIOD", "ACCOUNT"}:
        return ""

    if any(token in policy for token in ["POLICY-PERIOD", "EFF-DATE", "EXP-DATE", "REPORT-DATE", "LINE-OF-BUSINESS"]):
        return ""

    return policy


def clean_named_insured(value: str) -> str:
    cleaned = clean_text(value)

    # Fix OCR/compact text like:
    # NamedInsured: Good Living Developments LLCPolicyNumber: 10050749CA
    cleaned = re.split(
        r"\b(?:Policy\s*Number|PolicyNumber|Policy\s*Term|PolicyTerm|Report\s*Run\s*Date|ReportRunDate|Page\s+\d+|Claim\s+Number|ClaimNumber)\b",
        cleaned,
        maxsplit=1,
        flags=re.I,
    )[0]

    cleaned = cleaned.strip(" :-|")

    return clean_text(cleaned)

def extract_compressed_named_insured(text: str) -> str:
    """
    Handles compressed carrier text like:
    ReportRunDate:April 17, 2026NamedInsured: Good Living Developments LLCPolicyNumber: 10050749CA
    """
    if not text:
        return ""

    patterns = [
        r"NamedInsured\s*:\s*(.*?)(?:PolicyNumber|Policy Number|PolicyNo|Policy No|ReportRunDate|Report Run Date|Page\s+\d+|$)",
        r"Named Insured\s*:\s*(.*?)(?:Policy Number|PolicyNumber|PolicyNo|Policy No|Report Run Date|Page\s+\d+|$)",
        r"Insured\s*:\s*(.*?)(?:Policy Number|PolicyNumber|PolicyNo|Policy No|Report Run Date|Page\s+\d+|$)",
        r"Account Name\s*:\s*(.*?)(?:Policy Number|PolicyNumber|PolicyNo|Policy No|Report Run Date|Page\s+\d+|$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            value = match.group(1).strip()
            value = re.sub(r"\s+", " ", value)
            value = re.sub(r"Policy\s*Number.*$", "", value, flags=re.IGNORECASE).strip()
            value = re.sub(r"PolicyNumber.*$", "", value, flags=re.IGNORECASE).strip()
            value = re.sub(r"Report\s*Run\s*Date.*$", "", value, flags=re.IGNORECASE).strip()
            value = re.sub(r"Page\s+\d+.*$", "", value, flags=re.IGNORECASE).strip()
            return clean_named_insured(value)

    return ""


def carrier_from_policy_schedule(text: str) -> str:
    lines = split_lines(text)
    in_schedule = False

    for index, line in enumerate(lines):
        lower = line.lower()

        if "schedule of policies" in lower or "policy schedule" in lower:
            in_schedule = True
            continue

        if "claim summary" in lower or "detailed claims" in lower or "claim detail" in lower or "claim no" in lower or "claim #" in lower:
            in_schedule = False

        if not in_schedule:
            continue

        if re.search(r"\b[A-Z]{1,8}[-\s]?[A-Z]{1,8}[-\s]?\d{3,8}(?:[-\s]?[A-Z0-9]{1,8})?\b", line, re.I):
            for back in range(index - 1, max(-1, index - 8), -1):
                candidate = clean_text(lines[back])
                if looks_like_carrier_name(candidate):
                    return candidate

    return ""


def extract_first_schedule_policy(text: str) -> str:
    lines = split_lines(text)
    in_schedule = False

    for line in lines:
        lower = line.lower()

        if "schedule of policies" in lower or "policy schedule" in lower:
            in_schedule = True
            continue

        if "claim summary" in lower or "detailed claims" in lower or "claim detail" in lower or "claim no" in lower or "claim #" in lower:
            in_schedule = False

        if not in_schedule:
            continue

        match = re.search(r"\b[A-Z]{1,8}[-\s]?[A-Z]{1,8}[-\s]?\d{3,8}(?:[-\s]?[A-Z0-9]{1,8})?\b", line, re.I)
        if match:
            policy = clean_policy_value(match.group(0))
            if policy:
                return policy

    return ""


def extract_policy_period(text: str) -> tuple[str, str]:
    patterns = [
        r"Policy\s*Term\s*Claims\s*([0-9/.\-]+)\s*[-–]\s*([0-9/.\-]+)",
        r"PolicyTerm\s*Claims\s*([0-9/.\-]+)\s*[-–]\s*([0-9/.\-]+)",
        r"Policy\s*Period\s*[:\-]?\s*([0-9/.\-]+)\s*(?:to|[-–])\s*([0-9/.\-]+)",
        r"PolicyPeriod\s*[:\-]?\s*([0-9/.\-]+)\s*(?:to|[-–])\s*([0-9/.\-]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text or "", re.I)
        if match:
            return parse_date(match.group(1)) or "", parse_date(match.group(2)) or ""

    return "", ""


def extract_profile(text: str) -> dict:
    business_name_raw = find_first(
        [
            r"\bNamed\s*Insured\s*:\s*([^|\n]+)",
            r"\bNamedInsured\s*:\s*([^|\n]+)",
            r"\bInsured\s*:\s*([^|\n]+)",
            r"\bAccount Name\s*[:\-]?\s*([^\n|]+)",
            r"\bACCT NAME\s*[:\-]?\s*([^\n|]+)",
        ],
        text,
    )

    business_name = clean_named_insured(business_name_raw)
   
    if not business_name:
        business_name = extract_compressed_named_insured(text)

    agency_name = find_first(
        [
            r"\bProducer/Agency\s*:\s*([^\n]+)",
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

    raw_policy_number = find_first(
        [
            r"\bPolicy\s*(?:Number|No\.?|#)\s*:\s*([^\n|]+)",
            r"\bPolicyNumber\s*:\s*([A-Z0-9\-]+)",
            r"\bPolicy\s*#\s*([^\n|]+)",
        ],
        text,
    )

    policy_number = clean_policy_value(raw_policy_number)

    if not policy_number:
        policy_number = extract_first_schedule_policy(text)

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

    period_effective, period_expiration = extract_policy_period(text)

    if not effective_date_raw and period_effective:
        effective_date = period_effective
    else:
        effective_date = parse_date(effective_date_raw) or period_effective or ""

    if not expiration_date_raw and period_expiration:
        expiration_date = period_expiration
    else:
        expiration_date = parse_date(expiration_date_raw) or period_expiration or ""

    evaluation_date_raw = find_first(
        [
            r"\bReport\s*Run\s*Date\s*:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
            r"\bReportRunDate\s*:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
            r"\bValuation Date\s*:\s*([0-9/\-.]+)",
            r"\bReport Date\s*:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
            r"\bVALUATION\s*[:\-]?\s*([0-9/\-.]+)",
            r"\bAs Of\s*:\s*([0-9/\-.]+)",
        ],
        text,
    )

    return {
        "business_name": business_name,
        "carrier_name": clean_text(carrier_name),
        "writing_carrier": clean_text(carrier_name),
        "agency_name": clean_text(agency_name),
        "account_number": clean_text(account_number),
        "customer_number": clean_text(account_number),
        "producer_number": "",
        "policy_number": policy_number,
        "effective_date": effective_date,
        "expiration_date": expiration_date,
        "evaluation_date": parse_date(evaluation_date_raw) or "",
    }
