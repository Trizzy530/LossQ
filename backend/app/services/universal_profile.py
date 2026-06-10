"""
LossQ Universal Profile Extractor

Purpose:
- Extract insured/business name, carrier name, policy number, account number,
  effective date, and expiration date from raw loss run text.
- Safely ignores bad label-only values like "Line", "Policy", "Carrier", etc.
"""

import re
from datetime import datetime
from typing import Any, Dict, List


BAD_PROFILE_VALUES = {
    "",
    "line",
    "policy line",
    "policy",
    "account",
    "account number",
    "carrier",
    "carrier name",
    "writing carrier",
    "insured",
    "insured name",
    "business name",
    "named insured",
    "agency",
    "agency name",
    "producer",
    "not set",
    "none",
    "n/a",
    "na",
    "-",
    "--",
}


LABEL_WORDS = [
    "named insured",
    "insured name",
    "insured",
    "business name",
    "account name",
    "carrier name",
    "insurance carrier",
    "writing carrier",
    "carrier",
    "insurer name",
    "insurer",
    "agency name",
    "producing agency",
    "producer name",
    "broker name",
    "agency",
    "producer",
    "broker",
    "account number",
    "account no",
    "customer number",
    "customer no",
    "policy number",
    "policy no",
    "policy #",
    "policy",
    "effective date",
    "policy effective date",
    "eff date",
    "expiration date",
    "policy expiration date",
    "expiry date",
    "exp date",
    "evaluation date",
    "valuation date",
    "report date",
    "claim number",
    "claim no",
    "date of loss",
    "loss date",
    "status",
    "paid",
    "reserve",
    "incurred",
    "total incurred",
]


def clean_value(value: Any) -> str:
    if value is None:
        return ""

    text = str(value).strip()
    text = text.replace("\x00", " ")
    text = re.sub(r"\s+", " ", text)
    text = text.strip(" :-|\t\r\n")

    # Remove trailing field labels accidentally captured from compact text.
    for label in LABEL_WORDS:
        pattern = r"\s+" + re.escape(label) + r"\s*$"
        text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip(" :-|\t\r\n")

    return text


def is_good_value(value: Any, min_len: int = 2) -> bool:
    text = clean_value(value)
    if not text:
        return False

    if text.lower() in BAD_PROFILE_VALUES:
        return False

    if len(text) < min_len:
        return False

    # Reject values that are only labels/headers.
    lowered = text.lower().strip()
    if lowered in LABEL_WORDS:
        return False

    # Reject table header fragments.
    bad_fragments = {
        "loss run",
        "claim",
        "claims",
        "date",
        "effective",
        "expiration",
        "total",
        "open",
        "closed",
    }

    if lowered in bad_fragments:
        return False

    return True


def first_good(*values: Any) -> str:
    for value in values:
        cleaned = clean_value(value)
        if is_good_value(cleaned):
            return cleaned
    return ""


def normalize_date(value: Any) -> str:
    raw = clean_value(value)
    if not raw or raw.lower() in BAD_PROFILE_VALUES:
        return ""

    formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%m/%d/%y",
        "%m-%d-%y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except Exception:
            pass

    # Accept existing ISO-looking values
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw

    return ""


def extract_value_by_label(raw_text: str, labels: List[str], max_len: int = 90) -> str:
    """
    Strong line-first extractor.
    Works best for:
      Insured: ABC Company
      Carrier Name - Travelers
      Policy Number UC-12345
    """

    if not raw_text:
        return ""

    lines = [clean_value(line) for line in raw_text.splitlines()]
    lines = [line for line in lines if line]

    label_pattern = "|".join(re.escape(label) for label in labels)

    # 1. Label and value on the same line
    for line in lines:
        match = re.search(
            rf"^(?:{label_pattern})\s*(?:[:#\-|])?\s+(.{{2,{max_len}}})$",
            line,
            flags=re.IGNORECASE,
        )
        if match:
            value = clean_value(match.group(1))
            if is_good_value(value):
                return value

        match = re.search(
            rf"(?:{label_pattern})\s*(?:[:#\-|])\s*(.{{2,{max_len}}})",
            line,
            flags=re.IGNORECASE,
        )
        if match:
            value = clean_value(match.group(1))
            if is_good_value(value):
                return value

    # 2. Label on one line, value on next line
    for idx, line in enumerate(lines):
        lowered = line.lower().strip(" :-#|")
        if lowered in [label.lower() for label in labels]:
            for next_line in lines[idx + 1 : idx + 4]:
                value = clean_value(next_line)
                if is_good_value(value):
                    return value

    # 3. Compact-text fallback with stop at next known label
    compact = re.sub(r"\s+", " ", raw_text)
    stop_labels = "|".join(re.escape(label) for label in LABEL_WORDS)

    for label in labels:
        pattern = (
            rf"{re.escape(label)}\s*(?:[:#\-|])?\s+"
            rf"(.{{2,{max_len}}}?)(?=\s+(?:{stop_labels})\s*(?:[:#\-|])?|\s{{2,}}|$)"
        )
        match = re.search(pattern, compact, flags=re.IGNORECASE)
        if match:
            value = clean_value(match.group(1))
            if is_good_value(value):
                return value

    return ""


def extract_policy_like_value(raw_text: str, existing: Any = None, claims: List[Dict[str, Any]] | None = None) -> str:
    existing_clean = clean_value(existing)
    if is_good_value(existing_clean, min_len=3) and existing_clean.lower() != "line":
        return existing_clean

    claims = claims or []

    for claim in claims:
        value = first_good(
            claim.get("policy_number"),
            claim.get("policy_no"),
            claim.get("policy"),
        )
        if value and value.lower() != "line":
            return value

    value = extract_value_by_label(
        raw_text,
        ["Policy Number", "Policy No.", "Policy No", "Policy #"],
        max_len=45,
    )

    if value and value.lower() != "line":
        return value

    # Last resort: find obvious policy-like numbers.
    patterns = [
        r"\b([A-Z]{2,6}[-][A-Z0-9]{2,10}[-][A-Z0-9]{2,15}(?:[-][A-Z0-9]{1,10})?)\b",
        r"\b([A-Z]{2,8}[-]\d{4,}[-]\d{1,})\b",
        r"\b([A-Z]{2,8}\d{4,})\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, raw_text or "", flags=re.IGNORECASE)
        if match:
            found = clean_value(match.group(1)).upper()
            if is_good_value(found, min_len=4) and found.lower() != "line":
                return found

    return ""


def extract_account_like_value(raw_text: str, existing: Any = None, policy_number: str = "") -> str:
    existing_clean = clean_value(existing)
    if is_good_value(existing_clean, min_len=3) and existing_clean.lower() != "line":
        return existing_clean

    value = extract_value_by_label(
        raw_text,
        ["Account Number", "Account No.", "Account No", "Customer Number", "Customer No.", "Customer No"],
        max_len=45,
    )

    if value and value.lower() != "line":
        return value

    return policy_number or ""


def extract_universal_profile_from_text(
    raw_text: str,
    existing_profile: Dict[str, Any] | None = None,
    claims: List[Dict[str, Any]] | None = None,
    filename: str = "",
) -> Dict[str, Any]:
    existing_profile = dict(existing_profile or {})
    claims = claims or []
    raw_text = raw_text or ""

    business_name = first_good(
        existing_profile.get("business_name"),
        existing_profile.get("insured"),
        existing_profile.get("named_insured"),
        existing_profile.get("account_name"),
    )

    carrier_name = first_good(
        existing_profile.get("carrier_name"),
        existing_profile.get("writing_carrier"),
        existing_profile.get("insurance_carrier"),
        existing_profile.get("carrier"),
    )

    agency_name = first_good(
        existing_profile.get("agency_name"),
        existing_profile.get("broker_name"),
        existing_profile.get("producer_name"),
        existing_profile.get("agency"),
    )

    effective_date = normalize_date(existing_profile.get("effective_date"))
    expiration_date = normalize_date(existing_profile.get("expiration_date"))

    if not business_name:
        business_name = extract_value_by_label(
            raw_text,
            ["Named Insured", "Insured Name", "Insured", "Business Name", "Account Name", "Client", "Customer"],
        )

    if not carrier_name:
        carrier_name = extract_value_by_label(
            raw_text,
            ["Carrier Name", "Insurance Carrier", "Writing Carrier", "Carrier", "Insurer Name", "Insurer"],
        )

    if not agency_name:
        agency_name = extract_value_by_label(
            raw_text,
            ["Agency Name", "Producing Agency", "Producer Name", "Broker Name", "Agency", "Producer", "Broker"],
        )

    policy_number = extract_policy_like_value(
        raw_text,
        existing=existing_profile.get("policy_number")
        or existing_profile.get("policy_no")
        or existing_profile.get("policy"),
        claims=claims,
    )

    account_number = extract_account_like_value(
        raw_text,
        existing=existing_profile.get("account_number")
        or existing_profile.get("customer_number")
        or existing_profile.get("account_no"),
        policy_number=policy_number,
    )

    if not effective_date:
        effective_date = normalize_date(
            extract_value_by_label(
                raw_text,
                ["Effective Date", "Policy Effective Date", "Eff Date"],
                max_len=25,
            )
        )

    if not expiration_date:
        expiration_date = normalize_date(
            extract_value_by_label(
                raw_text,
                ["Expiration Date", "Policy Expiration Date", "Expiry Date", "Exp Date"],
                max_len=25,
            )
        )

    for claim in claims:
        if not business_name:
            business_name = first_good(
                claim.get("business_name"),
                claim.get("insured_name"),
                claim.get("named_insured"),
                claim.get("account_name"),
            )

        if not carrier_name:
            carrier_name = first_good(
                claim.get("carrier_name"),
                claim.get("writing_carrier"),
                claim.get("insurance_carrier"),
                claim.get("carrier"),
            )

        if not policy_number:
            policy_number = first_good(
                claim.get("policy_number"),
                claim.get("policy_no"),
                claim.get("policy"),
            )

        if business_name and carrier_name and policy_number:
            break

    profile = dict(existing_profile)
    profile["business_name"] = business_name or ""
    profile["carrier_name"] = carrier_name or ""
    profile["writing_carrier"] = first_good(existing_profile.get("writing_carrier"), carrier_name)
    profile["agency_name"] = agency_name or ""
    profile["account_number"] = account_number or policy_number or ""
    profile["customer_number"] = first_good(existing_profile.get("customer_number"), account_number, policy_number)
    profile["policy_number"] = policy_number or account_number or ""
    profile["effective_date"] = effective_date or ""
    profile["expiration_date"] = expiration_date or ""

    return profile