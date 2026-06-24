
"""
LOSSQ_CANADA_LOSS_RUN_SUPPORT_V1

Isolated Canadian loss run normalization helpers.

This module does not replace the core parser. It provides optional helpers for:
- Canadian provinces / territories
- CAD currency indicators
- Canadian postal codes
- Canadian date formats
- Canadian insurance line names
- Canadian carrier / broker terminology

Design rule:
Keep these helpers additive and safe. Do not hardcode insureds, carriers, policies,
or claim numbers. Do not alter unrelated parser behavior.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any


CANADIAN_PROVINCES = {
    "AB": "Alberta",
    "ALBERTA": "Alberta",
    "BC": "British Columbia",
    "B.C.": "British Columbia",
    "BRITISH COLUMBIA": "British Columbia",
    "MB": "Manitoba",
    "MANITOBA": "Manitoba",
    "NB": "New Brunswick",
    "NEW BRUNSWICK": "New Brunswick",
    "NL": "Newfoundland and Labrador",
    "NF": "Newfoundland and Labrador",
    "NEWFOUNDLAND": "Newfoundland and Labrador",
    "NEWFOUNDLAND AND LABRADOR": "Newfoundland and Labrador",
    "NS": "Nova Scotia",
    "NOVA SCOTIA": "Nova Scotia",
    "NT": "Northwest Territories",
    "NWT": "Northwest Territories",
    "NORTHWEST TERRITORIES": "Northwest Territories",
    "NU": "Nunavut",
    "NUNAVUT": "Nunavut",
    "ON": "Ontario",
    "ONTARIO": "Ontario",
    "PE": "Prince Edward Island",
    "PEI": "Prince Edward Island",
    "P.E.I.": "Prince Edward Island",
    "PRINCE EDWARD ISLAND": "Prince Edward Island",
    "QC": "Quebec",
    "PQ": "Quebec",
    "QUEBEC": "Quebec",
    "QUÉBEC": "Quebec",
    "SK": "Saskatchewan",
    "SASKATCHEWAN": "Saskatchewan",
    "YT": "Yukon",
    "YK": "Yukon",
    "YUKON": "Yukon",
}

PROVINCE_TO_CODE = {
    "Alberta": "AB",
    "British Columbia": "BC",
    "Manitoba": "MB",
    "New Brunswick": "NB",
    "Newfoundland and Labrador": "NL",
    "Nova Scotia": "NS",
    "Northwest Territories": "NT",
    "Nunavut": "NU",
    "Ontario": "ON",
    "Prince Edward Island": "PE",
    "Quebec": "QC",
    "Saskatchewan": "SK",
    "Yukon": "YT",
}

CANADA_POSTAL_RE = re.compile(r"\b([ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z])\s?-?\s?(\d[ABCEGHJ-NPRSTV-Z]\d)\b", re.I)

CANADIAN_TERMS = [
    "canada",
    "canadian",
    "province",
    "territory",
    "postal code",
    "brokerage",
    "insurance broker",
    "insurer",
    "underwriter",
    "policy no",
    "policy number",
    "cad",
    "ca$",
    "c$",
    "wsib",
    "worksafebc",
    "wcb",
    "cnesst",
    "icbc",
    "fsra",
]

CANADIAN_LINE_MAP = {
    "cgl": "General Liability",
    "commercial general liability": "General Liability",
    "general liability": "General Liability",
    "liability": "General Liability",
    "automobile": "Commercial Auto",
    "auto": "Commercial Auto",
    "commercial automobile": "Commercial Auto",
    "fleet automobile": "Commercial Auto",
    "fleet auto": "Commercial Auto",
    "garage automobile": "Garage",
    "garage auto": "Garage",
    "property": "Commercial Property",
    "commercial property": "Commercial Property",
    "building and contents": "Commercial Property",
    "building & contents": "Commercial Property",
    "boiler and machinery": "Equipment Breakdown",
    "boiler & machinery": "Equipment Breakdown",
    "equipment breakdown": "Equipment Breakdown",
    "crime": "Crime",
    "fidelity": "Crime",
    "cyber": "Cyber",
    "cyber liability": "Cyber",
    "privacy breach": "Cyber",
    "professional liability": "Professional Liability",
    "errors and omissions": "Professional Liability",
    "e&o": "Professional Liability",
    "directors and officers": "D&O",
    "d&o": "D&O",
    "employment practices liability": "EPLI",
    "epli": "EPLI",
    "umbrella": "Umbrella",
    "excess liability": "Umbrella",
    "cargo": "Cargo",
    "transit": "Cargo",
    "inland marine": "Inland Marine",
    "contractors equipment": "Inland Marine",
    "wrap-up liability": "Wrap-Up Liability",
    "wrap up liability": "Wrap-Up Liability",
    "workers compensation": "Workers Compensation",
    "workers comp": "Workers Compensation",
    "wcb": "Workers Compensation",
    "wsib": "Workers Compensation",
    "worksafebc": "Workers Compensation",
    "cnesst": "Workers Compensation",
}

BROKER_TERMS = {
    "broker": "broker",
    "brokerage": "broker",
    "insurance broker": "broker",
    "producer": "broker",
    "agent": "broker",
}

CARRIER_TERMS = {
    "carrier": "carrier",
    "insurer": "carrier",
    "insurance company": "carrier",
    "underwriter": "carrier",
    "company": "carrier",
}


def clean_text(value: Any) -> str:
    return str(value or "").replace("\u00a0", " ").strip()


def compact_text(value: Any) -> str:
    return re.sub(r"\s+", " ", clean_text(value))


def normalize_canadian_postal_code(value: Any) -> str:
    raw = compact_text(value).upper()
    match = CANADA_POSTAL_RE.search(raw)
    if not match:
        return ""
    return f"{match.group(1).upper()} {match.group(2).upper()}"


def normalize_canadian_province(value: Any) -> dict[str, str]:
    raw = compact_text(value)
    if not raw:
        return {"province": "", "province_code": ""}

    key = raw.upper().replace(".", "")
    province = CANADIAN_PROVINCES.get(key)

    if not province:
        for candidate, mapped in CANADIAN_PROVINCES.items():
            candidate_clean = candidate.replace(".", "")
            if re.search(rf"\b{re.escape(candidate_clean)}\b", key):
                province = mapped
                break

    if not province:
        return {"province": "", "province_code": ""}

    return {
        "province": province,
        "province_code": PROVINCE_TO_CODE.get(province, ""),
    }


def canadian_context_score(*values: Any) -> int:
    joined = " ".join(compact_text(v).lower() for v in values if v is not None)
    if not joined:
        return 0

    score = 0

    if CANADA_POSTAL_RE.search(joined):
        score += 3

    for term in CANADIAN_TERMS:
        if term in joined:
            score += 1

    for key in CANADIAN_PROVINCES:
        if re.search(rf"\b{re.escape(key.lower().replace('.', ''))}\b", joined.replace(".", "")):
            score += 1

    if re.search(r"\b(cad|ca\$|c\$)\b", joined):
        score += 2

    return score


def is_canadian_loss_run(*values: Any) -> bool:
    return canadian_context_score(*values) >= 2


def normalize_canadian_currency(value: Any) -> dict[str, Any]:
    raw = compact_text(value)
    if not raw:
        return {"amount": None, "currency": "", "raw": ""}

    currency = ""
    upper = raw.upper()

    if "CAD" in upper or "CA$" in upper or "C$" in upper:
        currency = "CAD"

    cleaned = upper
    cleaned = cleaned.replace("CAD", "")
    cleaned = cleaned.replace("CA$", "")
    cleaned = cleaned.replace("C$", "")
    cleaned = cleaned.replace("$", "")
    cleaned = cleaned.replace(",", "")
    cleaned = cleaned.strip()

    # French-style Canadian money can appear as 1 234,56.
    # If a comma is decimal and there is no dot, handle before comma removal above.
    french_raw = upper.replace("CAD", "").replace("CA$", "").replace("C$", "").replace("$", "").strip()
    if "," in french_raw and "." not in french_raw:
        french_number = french_raw.replace(" ", "").replace(",", ".")
        try:
            return {"amount": float(french_number), "currency": currency or "CAD", "raw": raw}
        except Exception:
            pass

    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return {"amount": None, "currency": currency, "raw": raw}

    try:
        amount = float(match.group(0))
    except Exception:
        amount = None

    return {"amount": amount, "currency": currency, "raw": raw}


def normalize_canadian_date(value: Any, prefer_canadian: bool = True) -> str:
    raw = compact_text(value)
    if not raw:
        return ""

    candidates = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d/%m/%Y" if prefer_canadian else "%m/%d/%Y",
        "%d-%m-%Y" if prefer_canadian else "%m-%d-%Y",
        "%d/%m/%y" if prefer_canadian else "%m/%d/%y",
        "%d-%m-%y" if prefer_canadian else "%m-%d-%y",
        "%b %d %Y",
        "%B %d %Y",
        "%d %b %Y",
        "%d %B %Y",
    ]

    for fmt in candidates:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except Exception:
            continue

    # Handle ISO-ish date inside longer text.
    match = re.search(r"\b(20\d{2}|19\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", raw)
    if match:
        yyyy, mm, dd = match.groups()
        try:
            return datetime(int(yyyy), int(mm), int(dd)).date().isoformat()
        except Exception:
            pass

    # Handle Canadian dd/mm/yyyy in longer text.
    match = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})\b", raw)
    if match:
        a, b, c = match.groups()
        year = int(c) + 2000 if len(c) == 2 else int(c)
        day = int(a)
        month = int(b)

        if prefer_canadian:
            try:
                return datetime(year, month, day).date().isoformat()
            except Exception:
                pass

    return raw


def normalize_canadian_line_name(value: Any) -> str:
    raw = compact_text(value)
    if not raw:
        return ""

    key = raw.lower().replace(".", "").strip()

    if key in CANADIAN_LINE_MAP:
        return CANADIAN_LINE_MAP[key]

    for candidate, mapped in CANADIAN_LINE_MAP.items():
        if re.search(rf"\b{re.escape(candidate)}\b", key):
            return mapped

    return raw


def normalize_canadian_terminology_key(value: Any) -> str:
    raw = compact_text(value).lower()
    if not raw:
        return ""

    normalized = re.sub(r"[^a-z0-9]+", " ", raw).strip()

    if normalized in BROKER_TERMS:
        return "broker"
    if normalized in CARRIER_TERMS:
        return "carrier"

    if "broker" in normalized or "brokerage" in normalized:
        return "broker"
    if "insurer" in normalized or "underwriter" in normalized or "insurance company" in normalized:
        return "carrier"

    return normalized


def enhance_claim_for_canada(claim: dict[str, Any], source_text: str = "") -> dict[str, Any]:
    if not isinstance(claim, dict):
        return claim

    context_values = [source_text] + list(claim.values())
    if not is_canadian_loss_run(*context_values):
        return claim

    enhanced = dict(claim)
    enhanced["country"] = enhanced.get("country") or "Canada"
    enhanced["currency"] = enhanced.get("currency") or "CAD"

    province_source = (
        enhanced.get("jurisdiction_state")
        or enhanced.get("jurisdiction")
        or enhanced.get("state")
        or enhanced.get("province")
        or source_text
    )
    province_data = normalize_canadian_province(province_source)
    if province_data["province_code"]:
        enhanced["jurisdiction_state"] = enhanced.get("jurisdiction_state") or province_data["province_code"]
        enhanced["province"] = enhanced.get("province") or province_data["province"]
        enhanced["province_code"] = enhanced.get("province_code") or province_data["province_code"]

    if enhanced.get("line_of_business"):
        enhanced["line_of_business"] = normalize_canadian_line_name(enhanced.get("line_of_business"))

    for amount_key in ["paid_amount", "reserve_amount", "total_incurred", "paid", "reserve", "incurred"]:
        parsed = normalize_canadian_currency(enhanced.get(amount_key))
        if parsed["amount"] is not None:
            enhanced[amount_key] = parsed["amount"]
            enhanced["currency"] = parsed["currency"] or enhanced.get("currency") or "CAD"

    for date_key in ["date_of_loss", "date_reported", "date_closed", "loss_date", "reported_date", "closed_date"]:
        if enhanced.get(date_key):
            enhanced[date_key] = normalize_canadian_date(enhanced.get(date_key), prefer_canadian=True)

    return enhanced


def enhance_profile_for_canada(profile: dict[str, Any], source_text: str = "") -> dict[str, Any]:
    if not isinstance(profile, dict):
        return profile

    context_values = [source_text] + list(profile.values())
    if not is_canadian_loss_run(*context_values):
        return profile

    enhanced = dict(profile)
    enhanced["country"] = enhanced.get("country") or "Canada"
    enhanced["currency"] = enhanced.get("currency") or "CAD"

    postal_source = (
        enhanced.get("postal_code")
        or enhanced.get("zip")
        or enhanced.get("zip_code")
        or enhanced.get("address")
        or source_text
    )
    postal_code = normalize_canadian_postal_code(postal_source)
    if postal_code:
        enhanced["postal_code"] = postal_code

    province_source = (
        enhanced.get("province")
        or enhanced.get("state")
        or enhanced.get("jurisdiction")
        or enhanced.get("address")
        or source_text
    )
    province_data = normalize_canadian_province(province_source)
    if province_data["province_code"]:
        enhanced["province"] = enhanced.get("province") or province_data["province"]
        enhanced["province_code"] = enhanced.get("province_code") or province_data["province_code"]
        enhanced["state"] = enhanced.get("state") or province_data["province_code"]

    for key in ["carrier", "carrier_name", "writing_carrier", "insurer", "underwriter"]:
        if enhanced.get(key) and normalize_canadian_terminology_key(key) == "carrier":
            enhanced["carrier_name"] = enhanced.get("carrier_name") or enhanced.get(key)

    for key in ["broker", "brokerage", "producer", "agent", "producing_agency"]:
        if enhanced.get(key) and normalize_canadian_terminology_key(key) == "broker":
            enhanced["producing_agency"] = enhanced.get("producing_agency") or enhanced.get(key)

    for date_key in ["effective_date", "expiration_date", "evaluation_date", "valuation_date"]:
        if enhanced.get(date_key):
            enhanced[date_key] = normalize_canadian_date(enhanced.get(date_key), prefer_canadian=True)

    return enhanced
