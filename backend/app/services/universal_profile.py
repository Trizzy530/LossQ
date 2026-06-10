"""
LossQ Universal Profile Extractor

Strict fallback extractor for account/profile fields.
Prevents bad values like:
- Name
- Line
- Policy Line
- Carrier Name
- Line of Business Business Type DOL
"""

import re
from datetime import datetime
from typing import Any, Dict, List


BAD_VALUES = {
    "line-of-business",
    "line of business",
    "line-of-business business type dol",
    "line of business business type dol",
    "business-type",
    "dol",
    "line-of-business line",
    "line of business line",

    "",
    "name",
    "line",
    "policy",
    "policy line",
    "line of business",
    "business type",
    "business type dol",
    "line of business business type dol",
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


FIELD_LABELS = [
    "named insured",
    "insured name",
    "business name",
    "account name",
    "client name",
    "customer name",
    "carrier name",
    "insurance carrier",
    "writing carrier",
    "insurer name",
    "agency name",
    "producing agency",
    "producer name",
    "broker name",
    "account number",
    "account no",
    "customer number",
    "customer no",
    "policy number",
    "policy no",
    "policy #",
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
    "line of business",
    "business type",
]


def clean_value(value: Any) -> str:
    if value is None:
        return ""

    text = str(value).replace("\x00", " ").strip()
    text = re.sub(r"\s+", " ", text)
    text = text.strip(" :-#|\t\r\n")

    return text


def is_good_value(value: Any, min_len: int = 2) -> bool:
    text = clean_value(value)
    lowered = text.lower()

    if not text:
        return False

    if lowered in BAD_VALUES:
        return False

    if lowered in FIELD_LABELS:
        return False

    if len(text) < min_len:
        return False

    # Reject values that are only column/header words.
    if re.fullmatch(
        r"(name|line|business|type|dol|policy|carrier|insured|account)([\s\-]+(name|line|business|type|dol|policy|carrier|insured|account))*",
        lowered,
    ):
        return False

    # Reject table/header fragments being mistaken as real values.
    bad_contains = [
        "line-of-business",
        "line of business",
        "business type",
        "business-type",
        "claim number",
        "date of loss",
        "total incurred",
        "policy line",
    ]

    if any(item in lowered for item in bad_contains):
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

    if not raw or raw.lower() in BAD_VALUES:
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

    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw

    return ""


def extract_labeled_value(raw_text: str, labels: List[str], max_len: int = 80) -> str:
    """
    Strict label extractor.

    Accepts:
      Insured Name: ABC Company
      Carrier Name - Travelers
      Policy Number: GL-12345

    Also accepts:
      Insured Name
      ABC Company

    Rejects:
      Insured Name
      Carrier Name
      Policy Line
    """

    if not raw_text:
        return ""

    lines = [clean_value(line) for line in raw_text.splitlines()]
    lines = [line for line in lines if line]

    # Sort longest labels first so "Insured Name" wins before "Name".
    labels_sorted = sorted(labels, key=len, reverse=True)

    # 1. Same-line label with required separator.
    for line in lines:
        for label in labels_sorted:
            pattern = rf"^{re.escape(label)}\s*[:#\-|]\s*(.{{2,{max_len}}})$"
            match = re.search(pattern, line, flags=re.IGNORECASE)
            if match:
                value = clean_value(match.group(1))
                if is_good_value(value):
                    return value

    # 2. Label on one line, value on following line.
    normalized_labels = {label.lower().strip() for label in labels_sorted}

    for idx, line in enumerate(lines):
        lowered = line.lower().strip(" :-#|")

        if lowered in normalized_labels:
            for next_line in lines[idx + 1 : idx + 4]:
                value = clean_value(next_line)

                # Do not accept another field label as the value.
                if value.lower() in FIELD_LABELS or value.lower() in BAD_VALUES:
                    continue

                if is_good_value(value):
                    return value

    return ""


def extract_policy_number(raw_text: str, existing: Any = None, claims: List[Dict[str, Any]] | None = None) -> str:
    existing_value = clean_value(existing)

    if is_good_value(existing_value, min_len=4):
        return existing_value

    claims = claims or []

    for claim in claims:
        value = first_good(
            claim.get("policy_number"),
            claim.get("policy_no"),
            claim.get("policy"),
        )
        if value and is_good_value(value, min_len=4):
            return value

    value = extract_labeled_value(
        raw_text,
        ["Policy Number", "Policy No.", "Policy No", "Policy #"],
        max_len=50,
    )

    if value and is_good_value(value, min_len=4):
        return value

    # Last resort: policy-like pattern.
    patterns = [
        r"\b([A-Z]{2,8}-[A-Z0-9]{2,12}-[A-Z0-9]{2,12}(?:-[A-Z0-9]{1,12})?)\b",
        r"\b([A-Z]{2,8}\d{4,})\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, raw_text or "", flags=re.IGNORECASE)
        if match:
            found = clean_value(match.group(1)).upper()
            if is_good_value(found, min_len=4):
                return found

    return ""


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
    )

    agency_name = first_good(
        existing_profile.get("agency_name"),
        existing_profile.get("broker_name"),
        existing_profile.get("producer_name"),
    )

    if not business_name:
        business_name = extract_labeled_value(
            raw_text,
            [
                "Named Insured",
                "Insured Name",
                "Business Name",
                "Account Name",
                "Client Name",
                "Customer Name",
            ],
        )

    if not carrier_name:
        carrier_name = extract_labeled_value(
            raw_text,
            [
                "Carrier Name",
                "Insurance Carrier",
                "Writing Carrier",
                "Insurer Name",
            ],
        )

    if not agency_name:
        agency_name = extract_labeled_value(
            raw_text,
            [
                "Agency Name",
                "Producing Agency",
                "Producer Name",
                "Broker Name",
            ],
        )

    policy_number = extract_policy_number(
        raw_text,
        existing=existing_profile.get("policy_number")
        or existing_profile.get("policy_no")
        or existing_profile.get("policy"),
        claims=claims,
    )

    account_number = first_good(
        existing_profile.get("account_number"),
        existing_profile.get("customer_number"),
        extract_labeled_value(
            raw_text,
            [
                "Account Number",
                "Account No.",
                "Account No",
                "Customer Number",
                "Customer No.",
                "Customer No",
            ],
            max_len=50,
        ),
        policy_number,
    )

    effective_date = normalize_date(
        existing_profile.get("effective_date")
        or extract_labeled_value(
            raw_text,
            ["Effective Date", "Policy Effective Date", "Eff Date"],
            max_len=25,
        )
    )

    expiration_date = normalize_date(
        existing_profile.get("expiration_date")
        or extract_labeled_value(
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
    profile["policy_number"] = policy_number or account_number or ""
    profile["account_number"] = account_number or policy_number or ""
    profile["customer_number"] = first_good(existing_profile.get("customer_number"), account_number, policy_number)
    profile["effective_date"] = effective_date or ""
    profile["expiration_date"] = expiration_date or ""

    return profile

# LOSSQ_UNIVERSAL_EXPOSURE_ENRICHMENT_V1
# Adds premium worksheet, exposure basis, clean carrier, and multi-policy schedule enrichment
# without disrupting the existing universal profile extractor.

import re as _lossq_re


_LOSSQ_BAD_PROFILE_VALUES = {
    "",
    "carrier",
    "writing carrier",
    "carrier name",
    "exposure basis",
    "premium worksheet",
    "rating basis",
    "current premium",
    "expiring premium",
    "target renewal premium",
    "line coverage",
    "line-of-business",
    "line of business",
    "policy schedule",
    "coverage schedule",
    "policy number",
    "policy no",
    "policy",
    "insured",
    "named insured",
    "business name",
    "claim number",
    "date of loss",
    "total incurred",
}


_LOSSQ_LOB_KEYWORDS = {
    "Commercial Auto": ["commercial auto", "business auto", "auto liability", "bap", "vehicle", "fleet"],
    "General Liability": ["general liability", "gl", "cgl", "premises", "operations"],
    "Workers Compensation": ["workers compensation", "workers comp", "wc", "w/c", "work comp"],
    "Commercial Property": ["commercial property", "property", "building", "contents", "bpp", "tiv"],
    "Businessowners Policy": ["businessowners", "business owner", "bop"],
    "Cyber Liability": ["cyber", "privacy", "network security"],
    "Professional Liability": ["professional liability", "errors and omissions", "e&o", "eo"],
    "Employment Practices Liability": ["employment practices", "epli"],
    "Directors & Officers": ["directors", "officers", "d&o", "do liability"],
    "Inland Marine": ["inland marine", "equipment floater", "installation floater"],
    "Motor Truck Cargo": ["motor truck cargo", "cargo"],
    "Umbrella / Excess": ["umbrella", "excess"],
}


def _lossq_text(value):
    return str(value or "").strip()


def _lossq_is_bad_value(value):
    clean = _lossq_text(value).lower()
    clean = clean.replace(":", "").replace("-", " ").strip()

    if clean in _LOSSQ_BAD_PROFILE_VALUES:
        return True

    if len(clean) < 2:
        return True

    bad_contains = [
        "exposure basis",
        "premium worksheet",
        "rating basis",
        "line coverage",
        "line-of-business",
        "line of business",
        "policy schedule",
        "coverage schedule",
        "claim number",
        "date of loss",
        "total incurred",
    ]

    return any(item in clean for item in bad_contains)


def _lossq_clean_money(value):
    raw = _lossq_text(value)
    cleaned = _lossq_re.sub(r"[^0-9.\-]", "", raw)
    return cleaned.strip()


def _lossq_normalize_policy(value):
    return _lossq_text(value).upper().replace(" ", "").strip()


def _lossq_find_labeled_value(raw_text, labels, max_len=140):
    text = _lossq_text(raw_text)
    if not text:
        return ""

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for label in labels:
        safe = _lossq_re.escape(label)

        patterns = [
            rf"{safe}\s*[:=]\s*([^\n\r|]+)",
            rf"{safe}\s+([^\n\r|]+)",
        ]

        for pattern in patterns:
            match = _lossq_re.search(pattern, text, flags=_lossq_re.IGNORECASE)
            if match:
                value = _lossq_text(match.group(1))
                value = value.split("  ")[0].strip()
                if value and len(value) <= max_len and not _lossq_is_bad_value(value):
                    return value

        for i, line in enumerate(lines):
            if label.lower() in line.lower():
                possible_values = []

                if ":" in line:
                    possible_values.append(line.split(":", 1)[1].strip())
                if "=" in line:
                    possible_values.append(line.split("=", 1)[1].strip())

                if i + 1 < len(lines):
                    possible_values.append(lines[i + 1].strip())

                for value in possible_values:
                    value = _lossq_text(value)
                    if value and len(value) <= max_len and not _lossq_is_bad_value(value):
                        return value

    return ""


def _lossq_detect_line_of_business(text):
    haystack = _lossq_text(text).lower()

    for lob, needles in _LOSSQ_LOB_KEYWORDS.items():
        if any(needle in haystack for needle in needles):
            return lob

    return ""


def _lossq_clean_carrier_from_text(raw_text):
    labels = [
        "Writing Carrier",
        "Issuing Carrier",
        "Carrier Name",
        "Carrier",
        "Insurer",
        "Insurance Company",
        "Company Name",
        "Market",
    ]

    value = _lossq_find_labeled_value(raw_text, labels, max_len=100)

    if value and not _lossq_is_bad_value(value):
        return value

    return ""


def _lossq_extract_exposure_inputs(raw_text):
    text = _lossq_text(raw_text)
    if not text:
        return {}

    exposure = {
        "current_premium": _lossq_clean_money(
            _lossq_find_labeled_value(text, ["Current Premium", "Annual Premium", "Premium"])
        ),
        "expiring_premium": _lossq_clean_money(
            _lossq_find_labeled_value(text, ["Expiring Premium", "Prior Premium", "Current Term Premium"])
        ),
        "target_renewal_premium": _lossq_clean_money(
            _lossq_find_labeled_value(text, ["Target Renewal Premium", "Target Premium", "Renewal Target"])
        ),
        "exposure_basis": _lossq_find_labeled_value(text, ["Exposure Basis", "Rating Basis", "Premium Basis"]),
        "payroll": _lossq_clean_money(
            _lossq_find_labeled_value(text, ["Payroll", "Estimated Payroll", "Annual Payroll"])
        ),
        "revenue": _lossq_clean_money(
            _lossq_find_labeled_value(text, ["Revenue", "Sales", "Gross Sales", "Annual Revenue"])
        ),
        "sales": _lossq_clean_money(
            _lossq_find_labeled_value(text, ["Sales", "Gross Sales"])
        ),
        "receipts": _lossq_clean_money(
            _lossq_find_labeled_value(text, ["Receipts", "Gross Receipts"])
        ),
        "employee_count": _lossq_find_labeled_value(text, ["Employee Count", "Employees", "Number of Employees"]),
        "vehicle_count": _lossq_find_labeled_value(text, ["Vehicle Count", "Power Units", "Autos", "Scheduled Autos"]),
        "driver_count": _lossq_find_labeled_value(text, ["Driver Count", "Drivers", "Number of Drivers"]),
        "property_tiv": _lossq_clean_money(
            _lossq_find_labeled_value(text, ["Property TIV", "TIV", "Total Insured Value"])
        ),
        "tiv": _lossq_clean_money(
            _lossq_find_labeled_value(text, ["TIV", "Total Insured Value"])
        ),
        "building_value": _lossq_clean_money(
            _lossq_find_labeled_value(text, ["Building Value", "Building Limit"])
        ),
        "contents_value": _lossq_clean_money(
            _lossq_find_labeled_value(text, ["Contents Value", "Business Personal Property", "BPP"])
        ),
        "square_footage": _lossq_find_labeled_value(text, ["Square Footage", "Sq Ft", "Sq. Ft."]),
        "location_count": _lossq_find_labeled_value(text, ["Location Count", "Locations", "Number of Locations"]),
        "unit_count": _lossq_find_labeled_value(text, ["Unit Count", "Units"]),
        "class_code": _lossq_find_labeled_value(text, ["Class Code", "Class Codes", "WC Code", "GL Class"]),
        "class_codes": _lossq_find_labeled_value(text, ["Class Codes", "Class Code", "WC Code", "GL Class"]),
        "limits": _lossq_find_labeled_value(text, ["Policy Limits", "Limits", "Coverage Limit"]),
        "coverage_limit": _lossq_find_labeled_value(text, ["Coverage Limit", "Policy Limits", "Limits"]),
        "deductible": _lossq_find_labeled_value(text, ["Deductible"]),
        "retention": _lossq_find_labeled_value(text, ["Retention", "SIR", "Self Insured Retention"]),
        "cargo_limit": _lossq_find_labeled_value(text, ["Cargo Limit", "Motor Truck Cargo Limit"]),
        "umbrella_limit": _lossq_find_labeled_value(text, ["Umbrella Limit", "Excess Limit", "Umbrella / Excess Limit"]),
        "experience_mod": _lossq_find_labeled_value(text, ["Experience Mod", "Experience Modification", "E-Mod", "Mod"]),
        "mod": _lossq_find_labeled_value(text, ["Experience Mod", "E-Mod", "Mod"]),
        "exposure_change_percent": _lossq_find_labeled_value(text, ["Exposure Change %", "Exposure Change", "Projected Change"]),
    }

    return {
        key: value
        for key, value in exposure.items()
        if value not in ("", None)
    }


def _lossq_extract_policy_schedule(raw_text, claims=None):
    text = _lossq_text(raw_text)
    claims = claims or []

    policies = {}
    policy_pattern = r"\b[A-Z]{2,}[A-Z0-9]*[- ][A-Z0-9][-A-Z0-9]{3,}\b"

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for i, line in enumerate(lines):
        found = _lossq_re.findall(policy_pattern, line.upper())
        if not found:
            continue

        nearby = " ".join(lines[max(0, i - 2): min(len(lines), i + 3)])
        lob = _lossq_detect_line_of_business(nearby) or _lossq_detect_line_of_business(line) or "Policy"

        carrier = _lossq_clean_carrier_from_text(nearby) or _lossq_clean_carrier_from_text(text)

        effective = ""
        expiration = ""

        date_matches = _lossq_re.findall(r"\b(?:20\d{2}|19\d{2})[-/]\d{1,2}[-/]\d{1,2}\b|\b\d{1,2}[-/]\d{1,2}[-/](?:20\d{2}|19\d{2})\b", nearby)
        if len(date_matches) >= 1:
            effective = date_matches[0]
        if len(date_matches) >= 2:
            expiration = date_matches[1]

        for pol in found:
            policy_number = _lossq_normalize_policy(pol)
            if not policy_number:
                continue

            policies[policy_number] = {
                "policy_type": lob,
                "line_of_business": lob,
                "coverage": lob,
                "policy_number": policy_number,
                "writing_carrier": carrier,
                "carrier": carrier,
                "effective_date": effective,
                "expiration_date": expiration,
            }

    for claim in claims:
        policy_number = _lossq_normalize_policy(
            claim.get("policy_number")
            or claim.get("policyNumber")
            or claim.get("policy_no")
            or claim.get("policy")
        )

        if not policy_number:
            continue

        lob = (
            claim.get("line_of_business")
            or claim.get("lob")
            or claim.get("coverage")
            or claim.get("claim_type")
            or "Policy"
        )

        if policy_number not in policies:
            policies[policy_number] = {
                "policy_type": lob,
                "line_of_business": lob,
                "coverage": lob,
                "policy_number": policy_number,
                "writing_carrier": "",
                "carrier": "",
                "effective_date": "",
                "expiration_date": "",
            }
        else:
            if not policies[policy_number].get("line_of_business"):
                policies[policy_number]["line_of_business"] = lob
            if not policies[policy_number].get("coverage"):
                policies[policy_number]["coverage"] = lob

    return list(policies.values())


def _lossq_merge_policies(existing, extracted):
    existing = existing if isinstance(existing, list) else []
    extracted = extracted if isinstance(extracted, list) else []

    merged = {}

    for item in existing + extracted:
        if not isinstance(item, dict):
            continue

        key = _lossq_normalize_policy(item.get("policy_number") or item.get("policy") or item.get("number"))

        if not key:
            key = _lossq_text(item.get("line_of_business") or item.get("coverage") or item.get("policy_type")).upper()

        if not key:
            continue

        current = merged.get(key, {})
        next_item = {**current}

        for field, value in item.items():
            if value not in ("", None) and not next_item.get(field):
                next_item[field] = value

        merged[key] = next_item

    return list(merged.values())


def _lossq_enrich_profile_with_exposure(raw_text="", profile=None, claims=None, filename=None):
    profile = dict(profile or {})
    claims = claims or []

    exposure = _lossq_extract_exposure_inputs(raw_text)

    for key, value in exposure.items():
        if value not in ("", None) and not profile.get(key):
            profile[key] = value

    clean_carrier = _lossq_clean_carrier_from_text(raw_text)

    current_carrier = profile.get("carrier_name") or profile.get("writing_carrier") or ""

    if clean_carrier and (_lossq_is_bad_value(current_carrier) or not current_carrier):
        profile["carrier_name"] = clean_carrier
        profile["writing_carrier"] = clean_carrier
    else:
        if _lossq_is_bad_value(profile.get("carrier_name")):
            profile["carrier_name"] = ""
        if _lossq_is_bad_value(profile.get("writing_carrier")):
            profile["writing_carrier"] = profile.get("carrier_name") or ""

    extracted_policies = _lossq_extract_policy_schedule(raw_text, claims)
    profile["policies"] = _lossq_merge_policies(profile.get("policies"), extracted_policies)

    if not profile.get("policy_number") and profile["policies"]:
        profile["policy_number"] = profile["policies"][0].get("policy_number", "")

    if not profile.get("account_number"):
        account_number = _lossq_find_labeled_value(
            raw_text,
            ["Account Number", "Account No", "Customer Number", "Client Number"],
        )
        if account_number:
            profile["account_number"] = account_number

    if not profile.get("customer_number") and profile.get("account_number"):
        profile["customer_number"] = profile["account_number"]

    return profile


try:
    _lossq_original_extract_universal_profile_from_text = extract_universal_profile_from_text

    def extract_universal_profile_from_text(raw_text="", existing_profile=None, claims=None, filename=None, *args, **kwargs):
        base_profile = _lossq_original_extract_universal_profile_from_text(
            raw_text=raw_text,
            existing_profile=existing_profile,
            claims=claims,
            filename=filename,
            *args,
            **kwargs,
        )

        return _lossq_enrich_profile_with_exposure(
            raw_text=raw_text,
            profile=base_profile,
            claims=claims,
            filename=filename,
        )

except NameError:
    pass

