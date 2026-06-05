from __future__ import annotations

import re

from .utils import clean_text, find_first, normalize_policy_number, parse_date


def extract_profile(text: str) -> dict:
    """
    Universal profile extraction.

    This does not depend on a specific carrier or test file.
    It looks for common loss-run labels used by carriers, brokers, TPAs, and agencies.
    """

    profile = {
        "business_name": "",
        "carrier_name": "",
        "writing_carrier": "",
        "agency_name": "",
        "account_number": "",
        "customer_number": "",
        "producer_number": "",
        "policy_number": "",
        "effective_date": "",
        "expiration_date": "",
        "evaluation_date": "",
    }

    compact = re.sub(r"\s+", " ", text or " ").strip()

    profile["business_name"] = find_first(
        [
            r"(?:named insured|insured|account name|acct name)\s*[:\-]?\s*([A-Z0-9&.,' /\-]+?)(?:\s+\|\s+|\s+carrier\b|\s+producer\b|\s+broker\b|\s+account\b|\s+valuation\b|\s+policy\b|\n|$)",
            r"(?:insured)\s*[:\-]?\s*([A-Z0-9&.,' /\-]+)",
        ],
        compact,
    )

    profile["carrier_name"] = find_first(
        [
            r"(?:carrier|insurance company|insurer|company)\s*[:\-]?\s*([A-Z0-9&.,' /\-]+?)(?:\s+policy\b|\s+account\b|\s+producer\b|\s+agency\b|\s+valuation\b|\n|$)",
            r"^([A-Z][A-Z0-9&.,' /\-]+(?:INSURANCE|CASUALTY|MUTUAL|COMPANY|CO\.))",
        ],
        compact,
    )

    profile["writing_carrier"] = profile["carrier_name"]

    profile["agency_name"] = find_first(
        [
            r"(?:producer\s*/\s*agency|producer|agency|broker)\s*[:\-]?\s*([A-Z0-9&.,' /\-]+?)(?:\s+account\b|\s+valuation\b|\s+policy\b|\n|$)",
        ],
        compact,
    )

    profile["account_number"] = find_first(
        [
            r"(?:account no\.?|account number|acct no\.?|acct #|risk id|customer number)\s*[:\-]?\s*([A-Z0-9\-]+)",
        ],
        compact,
    )

    profile["customer_number"] = profile["account_number"]

    profile["producer_number"] = find_first(
        [
            r"(?:producer no\.?|producer number|producer #)\s*[:\-]?\s*([A-Z0-9\-]+)",
        ],
        compact,
    )

    profile["policy_number"] = find_first(
        [
            r"(?:policy no\.?|policy number|policy #)\s*[:\-]?\s*([A-Z0-9\-]+)",
        ],
        compact,
    )

    profile["policy_number"] = normalize_policy_number(
        profile["policy_number"] or profile["account_number"]
    )

    valuation = find_first(
        [
            r"(?:valuation date|valuation|as of|valued as of)\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}|\d{1,2}\.\d{1,2}\.\d{2,4})",
            r"(?:report date)\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})",
        ],
        compact,
    )

    profile["evaluation_date"] = parse_date(valuation) or ""

    period_match = re.search(
        r"(?:policy period|period)\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\s*(?:to|\-|\u2013|\u2014)\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})",
        compact,
        re.I,
    )

    if period_match:
        profile["effective_date"] = parse_date(period_match.group(1)) or ""
        profile["expiration_date"] = parse_date(period_match.group(2)) or ""

    for key, value in list(profile.items()):
        profile[key] = clean_text(value)

    return profile