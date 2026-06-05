from __future__ import annotations

import re
from .utils import compact_spaces, normalize_date


def _label_value(text: str, labels: list[str], stop_labels: list[str] | None = None) -> str:
    stop_labels = stop_labels or [
        "carrier", "producer", "agency", "account", "policy", "valuation", "report", "effective", "expiration", "named insured", "insured"
    ]
    for label in labels:
        pattern = rf"{label}\s*[:\-]?\s*(.+)"
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        value = compact_spaces(match.group(1))
        # Stop when another label begins on the same line.
        for stop in stop_labels:
            if stop.lower() == label.lower().strip("\\b"):
                continue
            split = re.split(rf"\s+{stop}\s*[:\-]", value, flags=re.IGNORECASE)
            if split:
                value = compact_spaces(split[0])
        return value.strip(" |")
    return ""


def extract_profile(text: str, policies: list[dict] | None = None) -> dict:
    lines = [compact_spaces(line) for line in (text or "").splitlines() if compact_spaces(line)]
    joined = "\n".join(lines)
    first_50 = "\n".join(lines[:50])

    insured = _label_value(
        first_50,
        [r"\bNamed Insured\b", r"\bInsured\b", r"\bAccount Name\b", r"\bAcct Name\b"],
        ["carrier", "producer", "agency", "account no", "valuation", "dba", "risk id"]
    )
    if "|" in insured:
        insured = insured.split("|")[0].strip()

    dba = ""
    dba_match = re.search(r"DBA(?: names seen)?\s*[:\-]?\s*([^\n|]+(?:/[^\n]+)?)", first_50, re.IGNORECASE)
    if dba_match:
        dba = compact_spaces(dba_match.group(1))

    carrier = _label_value(first_50, [r"\bCarrier\b", r"\bInsurance Carrier\b", r"\bCompany\b"], ["producer", "agency", "account", "policy", "valuation"])
    agency = _label_value(first_50, [r"\bProducer\s*/\s*Agency\b", r"\bProducer/Broker\b", r"\bProducer\b", r"\bAgency\b", r"\bBroker\b"], ["account", "valuation", "carrier", "policy"])

    account = ""
    for pattern in [r"Account\s*(?:Number|No\.?|#)?\s*[:\-]?\s*([A-Z0-9][A-Z0-9\- ]{3,30})", r"Risk\s*ID\s*[:\-]?\s*([A-Z0-9][A-Z0-9\- ]{3,30})"]:
        m = re.search(pattern, first_50, re.IGNORECASE)
        if m:
            account = compact_spaces(m.group(1)).split()[0]
            break

    valuation = ""
    m = re.search(r"Valuation(?: Date)?\s*[:\-]?\s*([0-9./\-]{6,10})", first_50, re.IGNORECASE)
    if m:
        valuation = normalize_date(m.group(1))

    effective_date = ""
    expiration_date = ""
    m = re.search(r"Policy Period\s*[:\-]?\s*([0-9./\-]{6,10})\s*(?:-|to|through)\s*([0-9./\-]{6,10})", first_50, re.IGNORECASE)
    if m:
        effective_date = normalize_date(m.group(1))
        expiration_date = normalize_date(m.group(2))

    policy_number = account
    if policies:
        # Use account number as the account key, but keep policies separately.
        policy_number = account or policies[0].get("policy_number", "")
        if not effective_date:
            effective_date = policies[0].get("effective_date", "") or ""
        if not expiration_date:
            expiration_date = policies[0].get("expiration_date", "") or ""
        if not carrier:
            carrier = policies[0].get("carrier") or policies[0].get("writing_carrier") or ""

    return {
        "business_name": insured or dba or "Business Name Needs Review",
        "dba_name": dba,
        "carrier_name": carrier or "Carrier Needs Review",
        "writing_carrier": carrier or "Carrier Needs Review",
        "agency_name": agency or "Agency Needs Review",
        "account_number": account or policy_number or "Account Needs Review",
        "customer_number": account or policy_number or "Account Needs Review",
        "policy_number": policy_number or account or "Policy Needs Review",
        "effective_date": effective_date,
        "expiration_date": expiration_date,
        "evaluation_date": valuation,
    }
