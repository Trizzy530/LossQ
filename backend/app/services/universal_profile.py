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



# LOSSQ_PREMIUM_WORKSHEET_EXTRACTION_V2
# Strengthens extraction from messy premium/exposure worksheets.

def _lossq_find_money_near_label(raw_text, labels):
    text = _lossq_text(raw_text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    money_pattern = r"\$?\s*\d{1,3}(?:,\d{3})*(?:\.\d{2})?|\$?\s*\d+(?:\.\d{2})?"

    for label in labels:
        label_lower = label.lower()

        for line in lines:
            if label_lower in line.lower():
                matches = _lossq_re.findall(money_pattern, line)
                if matches:
                    return _lossq_clean_money(matches[-1])

        for i, line in enumerate(lines):
            if label_lower in line.lower():
                nearby = " ".join(lines[i:i + 4])
                matches = _lossq_re.findall(money_pattern, nearby)
                if matches:
                    return _lossq_clean_money(matches[-1])

    return ""


def _lossq_find_number_near_label(raw_text, labels):
    text = _lossq_text(raw_text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for label in labels:
        label_lower = label.lower()

        for i, line in enumerate(lines):
            if label_lower in line.lower():
                nearby = " ".join(lines[i:i + 3])
                match = _lossq_re.search(r"\b\d+(?:,\d+)?(?:\.\d+)?\b", nearby)
                if match:
                    return match.group(0).replace(",", "")

    return ""


def _lossq_extract_exposure_inputs_v2(raw_text):
    text = _lossq_text(raw_text)

    if not text:
        return {}

    exposure = {}

    exposure["current_premium"] = (
        _lossq_find_money_near_label(text, ["Current Premium", "Expiring Premium", "Annual Premium"])
        or _lossq_clean_money(_lossq_find_labeled_value(text, ["Current Premium", "Expiring Premium", "Annual Premium"]))
    )

    exposure["expiring_premium"] = (
        _lossq_find_money_near_label(text, ["Expiring Premium", "Prior Premium", "Current Term Premium"])
        or _lossq_clean_money(_lossq_find_labeled_value(text, ["Expiring Premium", "Prior Premium", "Current Term Premium"]))
    )

    exposure["target_renewal_premium"] = (
        _lossq_find_money_near_label(text, ["Target Renewal Premium", "Target Premium", "Renewal Target"])
        or _lossq_clean_money(_lossq_find_labeled_value(text, ["Target Renewal Premium", "Target Premium", "Renewal Target"]))
    )

    exposure["payroll"] = (
        _lossq_find_money_near_label(text, ["Payroll", "Estimated Payroll", "Annual Payroll"])
        or _lossq_clean_money(_lossq_find_labeled_value(text, ["Payroll", "Estimated Payroll", "Annual Payroll"]))
    )

    exposure["revenue"] = (
        _lossq_find_money_near_label(text, ["Revenue", "Sales", "Gross Sales", "Annual Revenue", "Receipts"])
        or _lossq_clean_money(_lossq_find_labeled_value(text, ["Revenue", "Sales", "Gross Sales", "Annual Revenue", "Receipts"]))
    )

    exposure["sales"] = exposure.get("revenue") or _lossq_clean_money(_lossq_find_labeled_value(text, ["Sales", "Gross Sales"]))
    exposure["receipts"] = _lossq_clean_money(_lossq_find_labeled_value(text, ["Receipts", "Gross Receipts"]))

    exposure["property_tiv"] = (
        _lossq_find_money_near_label(text, ["Property TIV", "Total Insured Value", "TIV"])
        or _lossq_clean_money(_lossq_find_labeled_value(text, ["Property TIV", "Total Insured Value", "TIV"]))
    )

    exposure["tiv"] = exposure.get("property_tiv") or _lossq_clean_money(_lossq_find_labeled_value(text, ["TIV"]))

    exposure["building_value"] = (
        _lossq_find_money_near_label(text, ["Building Value", "Building Limit"])
        or _lossq_clean_money(_lossq_find_labeled_value(text, ["Building Value", "Building Limit"]))
    )

    exposure["contents_value"] = (
        _lossq_find_money_near_label(text, ["Contents Value", "Business Personal Property", "BPP"])
        or _lossq_clean_money(_lossq_find_labeled_value(text, ["Contents Value", "Business Personal Property", "BPP"]))
    )

    exposure["cargo_limit"] = (
        _lossq_find_money_near_label(text, ["Cargo Limit", "Motor Truck Cargo Limit"])
        or _lossq_find_labeled_value(text, ["Cargo Limit", "Motor Truck Cargo Limit"])
    )

    exposure["umbrella_limit"] = (
        _lossq_find_money_near_label(text, ["Umbrella Limit", "Excess Limit", "Umbrella / Excess Limit"])
        or _lossq_find_labeled_value(text, ["Umbrella Limit", "Excess Limit", "Umbrella / Excess Limit"])
    )

    exposure["employee_count"] = _lossq_find_number_near_label(text, ["Employee Count", "Employees", "Number of Employees"])
    exposure["vehicle_count"] = _lossq_find_number_near_label(text, ["Vehicle Count", "Power Units", "Autos", "Scheduled Autos"])
    exposure["driver_count"] = _lossq_find_number_near_label(text, ["Driver Count", "Drivers", "Number of Drivers"])
    exposure["location_count"] = _lossq_find_number_near_label(text, ["Location Count", "Locations", "Number of Locations"])
    exposure["unit_count"] = _lossq_find_number_near_label(text, ["Unit Count", "Units"])
    exposure["square_footage"] = _lossq_find_number_near_label(text, ["Square Footage", "Sq Ft", "Sq. Ft."])

    exposure["class_code"] = _lossq_find_labeled_value(text, ["Class Code", "Class Codes", "WC Code", "GL Class"])
    exposure["class_codes"] = exposure.get("class_code") or _lossq_find_labeled_value(text, ["Class Codes"])
    exposure["limits"] = _lossq_find_labeled_value(text, ["Policy Limits", "Limits", "Coverage Limit"])
    exposure["coverage_limit"] = exposure.get("limits") or _lossq_find_labeled_value(text, ["Coverage Limit"])
    exposure["deductible"] = _lossq_find_labeled_value(text, ["Deductible"])
    exposure["retention"] = _lossq_find_labeled_value(text, ["Retention", "SIR", "Self Insured Retention"])
    exposure["experience_mod"] = _lossq_find_labeled_value(text, ["Experience Mod", "Experience Modification", "E-Mod", "Mod"])
    exposure["mod"] = exposure.get("experience_mod") or _lossq_find_labeled_value(text, ["Mod"])
    exposure["exposure_change_percent"] = _lossq_find_labeled_value(text, ["Exposure Change %", "Exposure Change", "Projected Change"])
    exposure["exposure_basis"] = _lossq_find_labeled_value(text, ["Exposure Basis", "Rating Basis", "Premium Basis"])

    return {k: v for k, v in exposure.items() if v not in ("", None)}


_lossq_previous_enrich_profile_with_exposure = _lossq_enrich_profile_with_exposure

def _lossq_enrich_profile_with_exposure(raw_text="", profile=None, claims=None, filename=None):
    profile = _lossq_previous_enrich_profile_with_exposure(
        raw_text=raw_text,
        profile=profile,
        claims=claims,
        filename=filename,
    )

    exposure_v2 = _lossq_extract_exposure_inputs_v2(raw_text)

    for key, value in exposure_v2.items():
        if value not in ("", None) and not profile.get(key):
            profile[key] = value

    return profile



# LOSSQ_POLICY_AND_PREMIUM_WORKSHEET_V3
# Dedicated extractor for messy policy schedules and premium/exposure worksheets.

def _lossq_policy_type_from_number(policy_number=""):
    pol = _lossq_text(policy_number).upper()

    if pol.startswith(("BOP", "BUS")):
        return "Businessowners Policy"
    if pol.startswith(("GL", "CGL")):
        return "General Liability"
    if pol.startswith(("WC", "WCP", "WCOMP")):
        return "Workers Compensation"
    if pol.startswith(("AUTO", "BAP", "CA", "AL")):
        return "Commercial Auto"
    if pol.startswith(("PROP", "CP", "CPP")):
        return "Commercial Property"
    if pol.startswith(("CYB", "CYBER")):
        return "Cyber Liability"
    if pol.startswith(("EPL", "EPLI")):
        return "Employment Practices Liability"
    if pol.startswith(("DNO", "DO", "D&O")):
        return "Directors & Officers"
    if pol.startswith(("EO", "E&O", "PROF", "PL")):
        return "Professional Liability"
    if pol.startswith(("IM", "INMAR")):
        return "Inland Marine"
    if pol.startswith(("CARGO", "MTC")):
        return "Motor Truck Cargo"
    if pol.startswith(("UMB", "XS", "EXC")):
        return "Umbrella / Excess"

    return ""


def _lossq_is_bad_policy_number(value):
    pol = _lossq_text(value).upper().replace(" ", "")

    if not pol:
        return True

    bad = {
        "LINE-COVERAGE",
        "LINECOVERAGE",
        "POLICYNUMBER",
        "POLICY-NUMBER",
        "ACCOUNTNUMBER",
        "ACCOUNT-NUMBER",
        "EXPOSUREBASIS",
        "EXPOSURE-BASIS",
        "CURRENT-PREMIUM",
        "EXPIRING-PREMIUM",
    }

    if pol in bad:
        return True

    if "COVERAGE" in pol and "20" not in pol:
        return True

    if len(pol) < 6:
        return True

    return False


def _lossq_find_all_policy_numbers_v3(raw_text):
    text = _lossq_text(raw_text).upper()

    patterns = [
        r"\b(?:BOP|GL|CGL|WC|WCP|WCOMP|AUTO|BAP|CA|AL|PROP|CP|CPP|CYB|CYBER|EPL|EPLI|DNO|DO|EO|PROF|PL|IM|MTC|CARGO|UMB|XS|EXC)[-_ ]?\d{4}[-_ ]?\d{3,8}\b",
        r"\b(?:BOP|GL|CGL|WC|WCP|WCOMP|AUTO|BAP|PROP|CP|CYB|EPLI|DNO|EO|IM|CARGO|UMB|XS)[-_ ][A-Z0-9]{4,12}\b",
    ]

    found = []

    for pattern in patterns:
        for match in _lossq_re.findall(pattern, text):
            policy = _lossq_normalize_policy(match.replace("_", "-"))
            if policy and not _lossq_is_bad_policy_number(policy):
                found.append(policy)

    unique = []
    seen = set()

    for policy in found:
        if policy not in seen:
            seen.add(policy)
            unique.append(policy)

    return unique


def _lossq_find_dates_near_text(value):
    text = _lossq_text(value)

    return _lossq_re.findall(
        r"\b(?:20\d{2}|19\d{2})[-/]\d{1,2}[-/]\d{1,2}\b|\b\d{1,2}[-/]\d{1,2}[-/](?:20\d{2}|19\d{2})\b",
        text,
    )


def _lossq_find_policy_context(raw_text, policy_number):
    text = _lossq_text(raw_text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    normalized_target = _lossq_normalize_policy(policy_number)

    for i, line in enumerate(lines):
        normalized_line = _lossq_normalize_policy(line)
        if normalized_target and normalized_target in normalized_line:
            return " ".join(lines[max(0, i - 4): min(len(lines), i + 5)])

    return ""


def _lossq_profile_carrier(profile=None, raw_text=""):
    profile = profile or {}

    candidates = [
        profile.get("writing_carrier"),
        profile.get("carrier_name"),
        profile.get("carrier"),
        _lossq_clean_carrier_from_text(raw_text),
    ]

    for item in candidates:
        cleaned = _lossq_text(item)
        if cleaned and not _lossq_is_bad_value(cleaned):
            return cleaned

    return ""


def _lossq_extract_policy_schedule_v3(raw_text, claims=None, profile=None):
    text = _lossq_text(raw_text)
    claims = claims or []
    profile = profile or {}

    carrier = _lossq_profile_carrier(profile, text)

    policies = {}

    for policy_number in _lossq_find_all_policy_numbers_v3(text):
        context = _lossq_find_policy_context(text, policy_number)
        lob = _lossq_policy_type_from_number(policy_number) or _lossq_detect_line_of_business(context) or "Commercial Policy"

        dates = _lossq_find_dates_near_text(context)
        effective = dates[0] if len(dates) >= 1 else profile.get("effective_date", "")
        expiration = dates[1] if len(dates) >= 2 else profile.get("expiration_date", "")

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

        if not policy_number or _lossq_is_bad_policy_number(policy_number):
            continue

        lob = (
            claim.get("line_of_business")
            or claim.get("lob")
            or claim.get("coverage")
            or claim.get("claim_type")
            or _lossq_policy_type_from_number(policy_number)
            or "Commercial Policy"
        )

        if policy_number not in policies:
            policies[policy_number] = {
                "policy_type": lob,
                "line_of_business": lob,
                "coverage": lob,
                "policy_number": policy_number,
                "writing_carrier": carrier,
                "carrier": carrier,
                "effective_date": profile.get("effective_date", ""),
                "expiration_date": profile.get("expiration_date", ""),
            }

    return list(policies.values())


def _lossq_extract_premium_worksheet_table_v3(raw_text):
    text = _lossq_text(raw_text)

    if not text:
        return {}

    exposure = {}

    field_map = {
        "current_premium": [
            "current premium",
            "annual premium",
            "expiring premium",
            "total current premium",
        ],
        "expiring_premium": [
            "expiring premium",
            "prior premium",
            "current term premium",
        ],
        "target_renewal_premium": [
            "target renewal premium",
            "target premium",
            "renewal target",
        ],
        "payroll": [
            "payroll",
            "estimated payroll",
            "annual payroll",
        ],
        "revenue": [
            "revenue",
            "sales",
            "gross sales",
            "annual revenue",
            "gross receipts",
            "receipts",
        ],
        "property_tiv": [
            "property tiv",
            "total insured value",
            "tiv",
        ],
        "building_value": [
            "building value",
            "building limit",
        ],
        "contents_value": [
            "contents value",
            "business personal property",
            "bpp",
        ],
        "vehicle_count": [
            "vehicle count",
            "power units",
            "scheduled autos",
            "autos",
        ],
        "driver_count": [
            "driver count",
            "drivers",
        ],
        "employee_count": [
            "employee count",
            "employees",
        ],
        "location_count": [
            "location count",
            "locations",
        ],
        "square_footage": [
            "square footage",
            "sq ft",
            "sq. ft.",
        ],
        "limits": [
            "policy limits",
            "coverage limit",
            "limits",
        ],
        "deductible": [
            "deductible",
        ],
        "retention": [
            "retention",
            "sir",
            "self insured retention",
        ],
        "class_code": [
            "class code",
            "class codes",
            "wc code",
            "gl class",
        ],
        "experience_mod": [
            "experience mod",
            "experience modification",
            "e-mod",
            "mod",
        ],
        "cargo_limit": [
            "cargo limit",
            "motor truck cargo limit",
        ],
        "umbrella_limit": [
            "umbrella limit",
            "excess limit",
        ],
        "exposure_change_percent": [
            "exposure change %",
            "exposure change",
            "projected change",
        ],
        "exposure_basis": [
            "exposure basis",
            "rating basis",
            "premium basis",
        ],
    }

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for key, labels in field_map.items():
        if exposure.get(key):
            continue

        for label in labels:
            label_lower = label.lower()

            for i, line in enumerate(lines):
                lower_line = line.lower()

                if label_lower not in lower_line:
                    continue

                combined = " ".join(lines[i:i + 3])

                if key in {
                    "current_premium",
                    "expiring_premium",
                    "target_renewal_premium",
                    "payroll",
                    "revenue",
                    "property_tiv",
                    "building_value",
                    "contents_value",
                    "cargo_limit",
                    "umbrella_limit",
                }:
                    value = _lossq_find_money_near_label(combined, [label])
                    if not value:
                        money_matches = _lossq_re.findall(r"\$?\s*\d{1,3}(?:,\d{3})+(?:\.\d{2})?|\$?\s*\d+(?:\.\d{2})?", combined)
                        if money_matches:
                            value = _lossq_clean_money(money_matches[-1])
                elif key in {
                    "vehicle_count",
                    "driver_count",
                    "employee_count",
                    "location_count",
                    "square_footage",
                }:
                    number_matches = _lossq_re.findall(r"\b\d+(?:,\d+)?(?:\.\d+)?\b", combined)
                    value = number_matches[-1].replace(",", "") if number_matches else ""
                else:
                    value = ""

                    if ":" in line:
                        value = line.split(":", 1)[1].strip()
                    elif "=" in line:
                        value = line.split("=", 1)[1].strip()
                    elif i + 1 < len(lines):
                        value = lines[i + 1].strip()

                    if _lossq_is_bad_value(value):
                        value = ""

                if value:
                    exposure[key] = value
                    break

            if exposure.get(key):
                break

    if exposure.get("revenue"):
        exposure.setdefault("sales", exposure["revenue"])

    if exposure.get("property_tiv"):
        exposure.setdefault("tiv", exposure["property_tiv"])

    if exposure.get("experience_mod"):
        exposure.setdefault("mod", exposure["experience_mod"])

    if exposure.get("limits"):
        exposure.setdefault("coverage_limit", exposure["limits"])

    return {k: v for k, v in exposure.items() if v not in ("", None)}


_lossq_previous_enrich_profile_with_exposure_v3 = _lossq_enrich_profile_with_exposure

def _lossq_enrich_profile_with_exposure(raw_text="", profile=None, claims=None, filename=None):
    profile = _lossq_previous_enrich_profile_with_exposure_v3(
        raw_text=raw_text,
        profile=profile,
        claims=claims,
        filename=filename,
    )

    worksheet = _lossq_extract_premium_worksheet_table_v3(raw_text)

    for key, value in worksheet.items():
        if value not in ("", None) and not profile.get(key):
            profile[key] = value

    carrier = _lossq_profile_carrier(profile, raw_text)

    if carrier:
        profile["carrier_name"] = carrier
        profile["writing_carrier"] = carrier

    policies_v3 = _lossq_extract_policy_schedule_v3(raw_text, claims=claims, profile=profile)

    if policies_v3:
        profile["policies"] = policies_v3

    if profile.get("policies") and not profile.get("policy_number"):
        profile["policy_number"] = profile["policies"][0].get("policy_number", "")

    return profile



# LOSSQ_VERTICAL_POLICY_WORKSHEET_V4
# Parses messy vertical policy schedules and Field/Value premium worksheets.

def _lossq_v4_clean(value):
    return str(value or "").strip()


def _lossq_v4_money(value):
    return _lossq_clean_money(value)


def _lossq_v4_good_policy(value):
    pol = _lossq_normalize_policy(value)

    if not pol:
        return False

    bad_values = {
        "LINE-COVERAGE",
        "LINECOVERAGE",
        "POLICY",
        "POLICY#",
        "POLICYNUMBER",
        "EXPOSUREBASIS",
        "CURRENTTOTALPREMIUM",
        "EXPIRINGPREMIUM",
        "TARGETRENEWAL",
    }

    if pol in bad_values:
        return False

    prefixes = (
        "GL-", "CGL-", "WC-", "WCP-", "CY-", "CYB-", "CP-", "CPP-", "BOP-",
        "EO-", "E&O-", "IM-", "UMB-", "XS-", "DO-", "DNO-", "EP-", "EPLI-",
        "AUTO-", "BAP-", "CA-", "MTC-", "CARGO-"
    )

    return pol.startswith(prefixes) and len(pol) >= 8


def _lossq_v4_policy_type(policy_number, line_text=""):
    pol = _lossq_normalize_policy(policy_number)
    line = _lossq_v4_clean(line_text).lower()

    if pol.startswith(("GL-", "CGL-")) or "general liability" in line:
        return "General Liability"
    if pol.startswith(("WC-", "WCP-")) or "workers comp" in line:
        return "Workers Compensation"
    if pol.startswith(("CY-", "CYB-")) or "cyber" in line:
        return "Cyber Liability"
    if pol.startswith(("CP-", "CPP-")) or "property" in line:
        return "Commercial Property"
    if pol.startswith("BOP-") or "bop" in line or "package" in line:
        return "Businessowners Policy"
    if pol.startswith(("EO-", "E&O-", "PROF-")) or "professional" in line or "e&o" in line:
        return "Professional Liability"
    if pol.startswith("IM-") or "inland marine" in line:
        return "Inland Marine"
    if pol.startswith(("UMB-", "XS-")) or "umbrella" in line or "excess" in line:
        return "Umbrella / Excess"
    if pol.startswith(("DO-", "DNO-")) or "d&o" in line:
        return "Directors & Officers"
    if pol.startswith(("EP-", "EPLI-")) or "epli" in line or "employment" in line:
        return "Employment Practices Liability"
    if pol.startswith(("AUTO-", "BAP-", "CA-")) or "auto" in line:
        return "Commercial Auto"
    if pol.startswith(("MTC-", "CARGO-")) or "cargo" in line:
        return "Motor Truck Cargo"

    return "Commercial Policy"


def _lossq_v4_parse_vertical_policy_schedule(raw_text, profile=None):
    profile = profile or {}
    text = _lossq_text(raw_text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    carrier_fallback = _lossq_profile_carrier(profile, text)

    policies = []

    for i, line in enumerate(lines):
        if not _lossq_v4_good_policy(line):
            continue

        policy_number = _lossq_normalize_policy(line)

        line_coverage = lines[i + 1] if i + 1 < len(lines) else ""
        carrier = lines[i + 2] if i + 2 < len(lines) else carrier_fallback
        effective = lines[i + 3] if i + 3 < len(lines) else profile.get("effective_date", "")
        expiration = lines[i + 4] if i + 4 < len(lines) else profile.get("expiration_date", "")
        limits = lines[i + 5] if i + 5 < len(lines) else ""
        deductible = lines[i + 6] if i + 6 < len(lines) else ""
        exposure_basis = lines[i + 7] if i + 7 < len(lines) else ""

        if _lossq_is_bad_value(carrier):
            carrier = carrier_fallback

        lob = _lossq_v4_policy_type(policy_number, line_coverage)

        policies.append({
            "policy_type": lob,
            "line_of_business": lob,
            "coverage": line_coverage or lob,
            "policy_number": policy_number,
            "writing_carrier": carrier or carrier_fallback,
            "carrier": carrier or carrier_fallback,
            "effective_date": effective,
            "expiration_date": expiration,
            "limits": limits,
            "coverage_limit": limits,
            "deductible": deductible,
            "retention": deductible,
            "exposure_basis": exposure_basis,
        })

    # De-duplicate while preserving order.
    seen = set()
    cleaned = []

    for item in policies:
        key = item.get("policy_number")
        if not key or key in seen:
            continue
        seen.add(key)
        cleaned.append(item)

    return cleaned


def _lossq_v4_parse_field_value_worksheet(raw_text):
    text = _lossq_text(raw_text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    lower_lines = [line.lower() for line in lines]

    field_labels = {
        "current_premium": ["current total premium", "current premium", "annual premium"],
        "expiring_premium": ["expiring premium", "prior premium"],
        "target_renewal_premium": ["target renewal", "target renewal premium", "target premium"],
        "revenue": ["revenue / sales", "revenue", "gross sales", "sales"],
        "sales": ["revenue / sales", "sales", "gross sales"],
        "payroll": ["payroll", "annual payroll"],
        "vehicle_count": ["vehicle count", "vehicles", "power units"],
        "property_tiv": ["property tiv", "tiv", "total insured value"],
        "tiv": ["property tiv", "tiv", "total insured value"],
        "square_footage": ["square footage", "sq ft", "sq. ft."],
        "cyber_revenue": ["cyber revenue"],
        "professional_revenue": ["professional revenue"],
        "experience_mod": ["experience mod", "e-mod", "mod"],
        "mod": ["experience mod", "e-mod", "mod"],
        "class_code": ["class codes", "class code"],
        "class_codes": ["class codes", "class code"],
        "employee_count": ["employee count", "employees"],
    }

    exposure = {}

    for field, labels in field_labels.items():
        for label in labels:
            for i, lower in enumerate(lower_lines):
                if lower == label or label in lower:
                    # In the messy worksheet, value is usually the next line.
                    value = ""
                    if i + 1 < len(lines):
                        value = lines[i + 1].strip()

                    if not value:
                        continue

                    if field in {
                        "current_premium",
                        "expiring_premium",
                        "target_renewal_premium",
                        "revenue",
                        "sales",
                        "payroll",
                        "property_tiv",
                        "tiv",
                        "cyber_revenue",
                        "professional_revenue",
                    }:
                        value = _lossq_v4_money(value)

                    if field in {"vehicle_count", "square_footage", "employee_count"}:
                        number_match = _lossq_re.search(r"\d[\d,]*(?:\.\d+)?", value)
                        value = number_match.group(0).replace(",", "") if number_match else value

                    if value and not _lossq_is_bad_value(value):
                        exposure[field] = value
                        break

            if exposure.get(field):
                break

    # Additional employee count fallback from comments like "includes 77 employees"
    if not exposure.get("employee_count"):
        match = _lossq_re.search(r"\bincludes\s+(\d+)\s+employees\b", text, flags=_lossq_re.IGNORECASE)
        if match:
            exposure["employee_count"] = match.group(1)

    # Location fallback from "2 locations"
    if not exposure.get("location_count"):
        match = _lossq_re.search(r"\b(\d+)\s+locations?\b", text, flags=_lossq_re.IGNORECASE)
        if match:
            exposure["location_count"] = match.group(1)

    if exposure.get("revenue"):
        exposure.setdefault("receipts", exposure["revenue"])

    return {k: v for k, v in exposure.items() if v not in ("", None)}


_lossq_previous_enrich_profile_with_exposure_v4 = _lossq_enrich_profile_with_exposure

def _lossq_enrich_profile_with_exposure(raw_text="", profile=None, claims=None, filename=None):
    profile = _lossq_previous_enrich_profile_with_exposure_v4(
        raw_text=raw_text,
        profile=profile,
        claims=claims,
        filename=filename,
    )

    text = _lossq_text(raw_text)

    worksheet = _lossq_v4_parse_field_value_worksheet(text)
    for key, value in worksheet.items():
        if value not in ("", None):
            profile[key] = value

    policies = _lossq_v4_parse_vertical_policy_schedule(text, profile=profile)

    if policies:
        profile["policies"] = policies

        # Use account number as account/policy selector when available.
        account_number = profile.get("account_number") or _lossq_find_labeled_value(
            text,
            ["Account Number", "Account No", "Customer Number", "Client Number"]
        )

        if account_number and not _lossq_is_bad_policy_number(account_number):
            profile["account_number"] = account_number
            profile["customer_number"] = profile.get("customer_number") or account_number

        # Never let LINE-COVERAGE become the profile policy number.
        current_policy = _lossq_normalize_policy(profile.get("policy_number"))
        if _lossq_is_bad_policy_number(current_policy):
            profile["policy_number"] = profile.get("account_number") or policies[0].get("policy_number", "")

    carrier = _lossq_profile_carrier(profile, text)
    if carrier:
        profile["carrier_name"] = carrier
        profile["writing_carrier"] = carrier

    return profile

