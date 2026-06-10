"""
LossQ Universal Profile Extractor

Purpose:
- Extract insured/business name, carrier name, policy number, account number,
  effective date, and expiration date from raw loss run text.
- Used as a safe fallback when the main parser saves claims but misses profile header fields.
"""

import re
from datetime import datetime
from typing import Any, Dict, List


def clean_value(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)
    return text.strip(" :-|\t\r\n")


def first_match(text: str, patterns: List[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            value = clean_value(match.group(1))
            if value:
                return value
    return ""


def normalize_date(value: Any) -> str:
    raw = clean_value(value)
    if not raw:
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

    return raw


def extract_universal_profile_from_text(
    raw_text: str,
    existing_profile: Dict[str, Any] | None = None,
    claims: List[Dict[str, Any]] | None = None,
    filename: str = "",
) -> Dict[str, Any]:
    existing_profile = dict(existing_profile or {})
    claims = claims or []

    text = raw_text or ""
    compact = re.sub(r"\s+", " ", text)

    business_name = clean_value(
        existing_profile.get("business_name")
        or existing_profile.get("insured")
        or existing_profile.get("named_insured")
        or existing_profile.get("account_name")
    )

    carrier_name = clean_value(
        existing_profile.get("carrier_name")
        or existing_profile.get("writing_carrier")
        or existing_profile.get("insurance_carrier")
        or existing_profile.get("carrier")
    )

    agency_name = clean_value(
        existing_profile.get("agency_name")
        or existing_profile.get("broker_name")
        or existing_profile.get("producer_name")
        or existing_profile.get("agency")
    )

    account_number = clean_value(
        existing_profile.get("account_number")
        or existing_profile.get("customer_number")
        or existing_profile.get("account_no")
    )

    policy_number = clean_value(
        existing_profile.get("policy_number")
        or existing_profile.get("policy_no")
        or existing_profile.get("policy")
    )

    effective_date = normalize_date(existing_profile.get("effective_date"))
    expiration_date = normalize_date(existing_profile.get("expiration_date"))

    if not business_name:
        business_name = first_match(
            compact,
            [
                r"(?:Named Insured|Insured Name|Insured|Business Name|Account Name)\s*[:#-]\s*([A-Za-z0-9&.,'()/\- ]{3,80})",
                r"(?:Client|Customer)\s*[:#-]\s*([A-Za-z0-9&.,'()/\- ]{3,80})",
            ],
        )

    if not carrier_name:
        carrier_name = first_match(
            compact,
            [
                r"(?:Carrier Name|Insurance Carrier|Writing Carrier|Carrier|Insurer Name|Insurer)\s*[:#-]\s*([A-Za-z0-9&.,'()/\- ]{3,80})",
                r"(?:Company)\s*[:#-]\s*([A-Za-z0-9&.,'()/\- ]{3,80})",
            ],
        )

    if not agency_name:
        agency_name = first_match(
            compact,
            [
                r"(?:Agency Name|Producing Agency|Producer Name|Broker Name|Agency|Producer|Broker)\s*[:#-]\s*([A-Za-z0-9&.,'()/\- ]{3,80})",
            ],
        )

    if not account_number:
        account_number = first_match(
            compact,
            [
                r"(?:Account Number|Account No\.?|Customer Number|Customer No\.?)\s*[:#-]\s*([A-Za-z0-9\-]{3,40})",
            ],
        )

    if not policy_number:
        policy_number = first_match(
            compact,
            [
                r"(?:Policy Number|Policy No\.?|Policy #|Policy)\s*[:#-]\s*([A-Za-z0-9\-]{3,40})",
            ],
        )

    if not effective_date:
        effective_date = normalize_date(
            first_match(
                compact,
                [
                    r"(?:Effective Date|Policy Effective Date|Eff Date)\s*[:#-]\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4}|[0-9]{4}-[0-9]{2}-[0-9]{2})",
                ],
            )
        )

    if not expiration_date:
        expiration_date = normalize_date(
            first_match(
                compact,
                [
                    r"(?:Expiration Date|Policy Expiration Date|Expiry Date|Exp Date)\s*[:#-]\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4}|[0-9]{4}-[0-9]{2}-[0-9]{2})",
                ],
            )
        )

    for claim in claims:
        if not business_name:
            business_name = clean_value(
                claim.get("business_name")
                or claim.get("insured_name")
                or claim.get("named_insured")
                or claim.get("account_name")
            )

        if not carrier_name:
            carrier_name = clean_value(
                claim.get("carrier_name")
                or claim.get("writing_carrier")
                or claim.get("insurance_carrier")
                or claim.get("carrier")
            )

        if not policy_number:
            policy_number = clean_value(
                claim.get("policy_number")
                or claim.get("policy_no")
                or claim.get("policy")
            )

        if business_name and carrier_name and policy_number:
            break

    if not policy_number and account_number:
        policy_number = account_number

    profile = dict(existing_profile)
    profile["business_name"] = business_name or existing_profile.get("business_name") or ""
    profile["carrier_name"] = carrier_name or existing_profile.get("carrier_name") or ""
    profile["writing_carrier"] = (
        existing_profile.get("writing_carrier")
        or carrier_name
        or existing_profile.get("carrier_name")
        or ""
    )
    profile["agency_name"] = agency_name or existing_profile.get("agency_name") or ""
    profile["account_number"] = account_number or existing_profile.get("account_number") or policy_number or ""
    profile["customer_number"] = (
        existing_profile.get("customer_number")
        or account_number
        or policy_number
        or ""
    )
    profile["policy_number"] = policy_number or existing_profile.get("policy_number") or ""
    profile["effective_date"] = effective_date or existing_profile.get("effective_date") or ""
    profile["expiration_date"] = expiration_date or existing_profile.get("expiration_date") or ""

    return profile