
# LOSSQ_MARKET_INTELLIGENCE_SERVICE_V1
"""
Universal LossQ market intelligence service.

Purpose:
- Detect country / market context
- Normalize exposure terminology
- Normalize State / Province / Postal Code logic
- Normalize carrier names
- Normalize line of business codes and terminology
- Provide narrative localization context

Important:
This file must stay universal.
Do not hardcode one customer, one brokerage, one demo file, or one prospect.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


CANADIAN_PROVINCES: Dict[str, Dict[str, str]] = {
    "ON": {"name": "Ontario", "regulator": "FSRA"},
    "BC": {"name": "British Columbia", "regulator": "BCFSA"},
    "AB": {"name": "Alberta", "regulator": "AIC"},
    "QC": {"name": "Quebec", "regulator": "AMF"},
    "MB": {"name": "Manitoba", "regulator": "Insurance Council of Manitoba"},
    "SK": {"name": "Saskatchewan", "regulator": "Insurance Councils of Saskatchewan"},
    "NS": {"name": "Nova Scotia", "regulator": "Nova Scotia Superintendent of Insurance"},
    "NB": {"name": "New Brunswick", "regulator": "FCNB"},
    "PE": {"name": "Prince Edward Island", "regulator": "PEI Superintendent of Insurance"},
    "NL": {"name": "Newfoundland and Labrador", "regulator": "Digital Government and Service NL"},
    "YT": {"name": "Yukon", "regulator": "Yukon Superintendent of Insurance"},
    "NT": {"name": "Northwest Territories", "regulator": "NWT Superintendent of Insurance"},
    "NU": {"name": "Nunavut", "regulator": "Nunavut Superintendent of Insurance"},
}

CANADIAN_PROVINCE_ALIASES: Dict[str, str] = {
    "ontario": "ON", "on": "ON",
    "britishcolumbia": "BC", "bc": "BC",
    "alberta": "AB", "ab": "AB",
    "quebec": "QC", "québec": "QC", "qc": "QC",
    "manitoba": "MB", "mb": "MB",
    "saskatchewan": "SK", "sk": "SK",
    "novascotia": "NS", "ns": "NS",
    "newbrunswick": "NB", "nb": "NB",
    "princeedwardisland": "PE", "pei": "PE", "pe": "PE",
    "newfoundland": "NL", "newfoundlandandlabrador": "NL", "nl": "NL",
    "yukon": "YT", "yt": "YT",
    "northwestterritories": "NT", "nt": "NT",
    "nunavut": "NU", "nu": "NU",
}

CANADIAN_POSTAL_PREFIX_PROVINCE: Dict[str, str] = {
    "A": "NL", "B": "NS", "C": "PE", "E": "NB",
    "G": "QC", "H": "QC", "J": "QC",
    "K": "ON", "L": "ON", "M": "ON", "N": "ON", "P": "ON",
    "R": "MB", "S": "SK", "T": "AB", "V": "BC",
    "X": "NT", "Y": "YT",
}

EXPOSURE_ALIASES: Dict[str, str] = {
    # Payroll / WC / Canadian terms
    "payroll": "payroll",
    "annualpayroll": "payroll",
    "grosspayroll": "payroll",
    "estimatedpayroll": "payroll",
    "remuneration": "payroll",
    "wages": "payroll",
    "insurableearnings": "payroll",
    "assessablepayroll": "payroll",

    # Revenue / sales / Canadian terms
    "revenue": "revenue",
    "annualrevenue": "revenue",
    "grossrevenue": "revenue",
    "grosssales": "revenue",
    "sales": "revenue",
    "turnover": "revenue",
    "receipts": "receipts",
    "grossreceipts": "receipts",

    # Fleet / auto
    "vehiclecount": "vehicle_count",
    "vehicles": "vehicle_count",
    "autos": "vehicle_count",
    "scheduledautos": "vehicle_count",
    "ownedautos": "vehicle_count",
    "fleetunits": "vehicle_count",
    "powerunits": "vehicle_count",
    "fleet": "vehicle_count",
    "fleetsize": "vehicle_count",

    "drivercount": "driver_count",
    "drivers": "driver_count",
    "listeddrivers": "driver_count",
    "operators": "driver_count",
    "operatorcount": "driver_count",

    # Property
    "propertytiv": "property_tiv",
    "tiv": "property_tiv",
    "totalinsuredvalue": "property_tiv",
    "totalinsurablevalue": "property_tiv",
    "statementofvalues": "property_tiv",
    "sov": "property_tiv",
    "locationtiv": "property_tiv",
    "buildingandcontents": "property_tiv",

    "buildingvalue": "building_value",
    "buildinglimit": "building_value",
    "buildingsuminsured": "building_value",
    "contentsvalue": "contents_value",
    "contentslimit": "contents_value",
    "businesspersonalproperty": "contents_value",
    "bpp": "contents_value",
    "stockandequipment": "contents_value",

    # Geography
    "state": "state",
    "primarystate": "state",
    "jurisdiction": "state",
    "province": "state",
    "provincecode": "state",
    "territory": "state",
    "riskprovince": "state",

    "postalcode": "postal_code",
    "postcode": "postal_code",
    "zip": "zip_code",
    "zipcode": "zip_code",

    # Premium
    "currentpremium": "current_premium",
    "annualpremium": "current_premium",
    "writtenpremium": "current_premium",
    "policypremium": "current_premium",
    "termpremium": "current_premium",
    "inforcepremium": "current_premium",
    "expiringpremium": "expiring_premium",
    "priorpremium": "expiring_premium",
    "previoustermpremium": "expiring_premium",
    "targetrenewalpremium": "target_renewal_premium",
    "renewaltargetpremium": "target_renewal_premium",

    # Limits
    "policylimits": "limits",
    "limitofliability": "limits",
    "coveragelimit": "coverage_limit",
    "deductible": "deductible",
    "retention": "retention",
    "sir": "retention",
    "selfinsuredretention": "retention",
    "umbrellalimit": "umbrella_limit",
    "excesslimit": "umbrella_limit",
    "cargolimit": "cargo_limit",
}

MONEY_FIELDS = {
    "current_premium", "expiring_premium", "target_renewal_premium",
    "payroll", "revenue", "sales", "receipts",
    "property_tiv", "building_value", "contents_value",
    "limits", "coverage_limit", "deductible", "retention",
    "umbrella_limit", "cargo_limit",
}

COUNT_FIELDS = {
    "employee_count", "vehicle_count", "driver_count",
    "location_count", "unit_count", "square_footage",
}

CANADIAN_CARRIER_ALIASES: Dict[str, str] = {
    "intact": "Intact Insurance",
    "intactfinancial": "Intact Insurance",
    "intactfinancialcorporation": "Intact Insurance",
    "rsa": "Intact Insurance",
    "rsacanada": "Intact Insurance",

    "aviva": "Aviva Canada",
    "avivacanada": "Aviva Canada",

    "wawanesa": "Wawanesa Mutual",
    "wawanesamutual": "Wawanesa Mutual",

    "northbridge": "Northbridge Financial",
    "northbridgefinancial": "Northbridge Financial",

    "definity": "Definity / Economical",
    "economical": "Definity / Economical",
    "economicalinsurance": "Definity / Economical",

    "cooperators": "Co-operators",
    "thecooperators": "Co-operators",

    "lloyds": "Lloyd's Canada",
    "lloydscanada": "Lloyd's Canada",

    "chubb": "Chubb Canada",
    "chubbcanada": "Chubb Canada",

    "zurich": "Zurich Canada",
    "zurichcanada": "Zurich Canada",

    "cna": "CNA Canada",
    "cnacanada": "CNA Canada",

    "gore": "Gore Mutual",
    "goremutual": "Gore Mutual",

    "heartland": "Heartland Farm Mutual",
    "heartlandfarmmutual": "Heartland Farm Mutual",
}

IBC_LINE_CODE_MAP: Dict[str, str] = {
    "20": "Commercial Property",
    "21": "General Liability",
    "22": "Commercial Auto",
    "23": "Marine",
    "24": "Aircraft",
    "25": "Boiler & Machinery",
    "30": "Surety",
    "36": "Professional Liability",
    "38": "Cyber",
}

LOB_ALIASES: Dict[str, str] = {
    "cgl": "General Liability",
    "commercialgeneralliability": "General Liability",
    "generalliability": "General Liability",
    "liability": "General Liability",

    "commercialauto": "Commercial Auto",
    "businessauto": "Commercial Auto",
    "fleetauto": "Commercial Auto",
    "fleetautomobile": "Commercial Auto",
    "automobile": "Commercial Auto",
    "fleet": "Commercial Auto",

    "workerscompensation": "Workers Compensation",
    "workerscomp": "Workers Compensation",
    "wc": "Workers Compensation",
    "wcb": "Workers Compensation",
    "wsib": "Workers Compensation",
    "worksafebc": "Workers Compensation",
    "cnesst": "Workers Compensation",

    "commercialproperty": "Commercial Property",
    "property": "Commercial Property",
    "bop": "Property / Package",
    "package": "Property / Package",

    "errorsandomissions": "Professional Liability",
    "eo": "Professional Liability",
    "eando": "Professional Liability",
    "professionalliability": "Professional Liability",

    "cyber": "Cyber",
    "cyberliability": "Cyber",

    "umbrella": "Umbrella / Excess",
    "excess": "Umbrella / Excess",
    "excessliability": "Umbrella / Excess",

    "cargo": "Cargo / Inland Marine",
    "inlandmarine": "Cargo / Inland Marine",
    "marinecargo": "Cargo / Inland Marine",
}



# LOSSQ_MARKET_INTELLIGENCE_FRENCH_ALIASES_V1
EXPOSURE_ALIASES.update({
    "primeactuelle": "current_premium",
    "primeannuelle": "current_premium",
    "primeexpirante": "expiring_premium",
    "primeciblederenouvellement": "target_renewal_premium",
    "chiffredaffaires": "revenue",
    "revenuannuel": "revenue",
    "ventesbrutes": "revenue",
    "recettesbrutes": "receipts",
    "paieassurable": "payroll",
    "masse salariale": "payroll",
    "massesalariale": "payroll",
    "remuneration": "payroll",
    "rémunération": "payroll",
    "nombredemployes": "employee_count",
    "nombredemployés": "employee_count",
    "employes": "employee_count",
    "employés": "employee_count",
    "vehicules": "vehicle_count",
    "véhicules": "vehicle_count",
    "vehiculesconducteurs": "vehicle_count",
    "véhiculesconducteurs": "vehicle_count",
    "conducteurs": "driver_count",
    "operateurs": "driver_count",
    "opérateurs": "driver_count",
    "sov": "property_tiv",
    "valeurtotaleassuree": "property_tiv",
    "valeurtotaleassurée": "property_tiv",
    "valeurassuree": "property_tiv",
    "valeurassurée": "property_tiv",
    "valeurdubâtiment": "building_value",
    "valeurdubatiment": "building_value",
    "valeurducontenu": "contents_value",
    "biensmeubles": "contents_value",
    "province": "state",
    "territoire": "state",
    "codepostal": "postal_code",
    "devise": "currency",
})

LOB_ALIASES.update({
    "responsabilitecivilecommerciale": "General Liability",
    "responsabilitécivilecommerciale": "General Liability",
    "responsabilitecivile": "General Liability",
    "responsabilitécivile": "General Liability",
    "bienscommerciaux": "Commercial Property",
    "proprietecommerciale": "Commercial Property",
    "propriétécommerciale": "Commercial Property",
    "automobilecommerciale": "Commercial Auto",
    "flotteautomobile": "Commercial Auto",
    "indemnisationdestravailleurs": "Workers Compensation",
    "accidentsdutravail": "Workers Compensation",
    "erreursetomissions": "Professional Liability",
    "responsabiliteprofessionnelle": "Professional Liability",
    "responsabilitéprofessionnelle": "Professional Liability",
    "cyberresponsabilite": "Cyber",
    "cyberresponsabilité": "Cyber",
    "responsabilitelieealalcool": "Liquor Liability",
    "responsabilitéliéeàlalcool": "Liquor Liability",
    "interruptiondesaffaires": "Business Interruption",
    "assuranceexcedentaire": "Umbrella / Excess",
    "assuranceexcédentaire": "Umbrella / Excess",
})

def lossq_market_clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\ufeff", "").strip())


def lossq_market_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", lossq_market_clean(value).lower())


def lossq_market_money(value: Any) -> str:
    text = lossq_market_clean(value)
    if not text:
        return ""

    text = re.sub(r"(?i)\b(?:cad|cdn|cnd|usd)\b", "", text)
    text = (
        text.replace("CA$", "")
        .replace("C$", "")
        .replace("US$", "")
        .replace("$", "")
        .replace(",", "")
        .strip()
    )

    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return match.group(0) if match else ""


def lossq_market_count(value: Any) -> str:
    text = lossq_market_clean(value).replace(",", "")
    match = re.search(r"\d+", text)
    return match.group(0) if match else ""


def lossq_detect_currency(raw_text: Any = "", profile_data: Optional[Dict[str, Any]] = None) -> str:
    profile_data = profile_data or {}
    text = " ".join([
        lossq_market_clean(raw_text),
        " ".join(lossq_market_clean(v) for v in profile_data.values() if not isinstance(v, (dict, list))),
    ]).lower()

    if re.search(r"\b(?:cad|cdn|cnd)\b", text) or "ca$" in text or "c$" in text:
        return "CAD"

    if re.search(r"\b(?:usd|us dollars?)\b", text) or "us$" in text:
        return "USD"

    return ""


def lossq_detect_language(raw_text: Any = "") -> str:
    text = lossq_market_clean(raw_text).lower()

    french_terms = [
        "numéro de sinistre",
        "date de survenance",
        "date de déclaration",
        "montant payé",
        "provision",
        "responsabilité civile",
        "biens commerciaux",
        "ouvert",
        "fermé",
    ]

    return "fr" if any(term in text for term in french_terms) else "en"


def lossq_detect_canadian_province(value: Any) -> str:
    text = lossq_market_clean(value)
    key = lossq_market_key(text)

    if key in CANADIAN_PROVINCE_ALIASES:
        return CANADIAN_PROVINCE_ALIASES[key]

    postal = text.upper().replace(" ", "")
    if re.match(r"^[A-Z]\d[A-Z]\d[A-Z]\d$", postal):
        return CANADIAN_POSTAL_PREFIX_PROVINCE.get(postal[:1], "")

    return ""


def lossq_detect_country(profile_data: Optional[Dict[str, Any]] = None, raw_text: Any = "") -> str:
    profile_data = profile_data or {}

    combined = " ".join([
        lossq_market_clean(raw_text),
        " ".join(lossq_market_clean(v) for v in profile_data.values() if not isinstance(v, (dict, list))),
    ]).lower()

    canada_signals = [
        "canada", "cad", "ca$", "c$", "postal code", "province", "territory",
        "wsib", "wcb", "worksafebc", "cnesst",
        "fsra", "bcfsa", "aic", "amf",
        "intact", "aviva canada", "wawanesa", "northbridge", "definity",
    ]

    if any(signal in combined for signal in canada_signals):
        return "Canada"

    full_text = " ".join([combined, lossq_market_clean(raw_text)])
    if re.search(r"\b[A-Z]\d[A-Z][ -]?\d[A-Z]\d\b", full_text, re.I):
        return "Canada"

    for key in ("state", "province", "province_code", "postal_code", "postcode"):
        if lossq_detect_canadian_province(profile_data.get(key)):
            return "Canada"

    us_signals = ["united states", "usa", "usd", "zip code", "naic"]
    if any(signal in combined for signal in us_signals):
        return "United States"

    return ""


def lossq_normalize_carrier(value: Any) -> str:
    key = lossq_market_key(value)

    if key in CANADIAN_CARRIER_ALIASES:
        return CANADIAN_CARRIER_ALIASES[key]

    return lossq_market_clean(value)


def lossq_normalize_line_of_business(value: Any) -> str:
    clean = lossq_market_clean(value)
    key = lossq_market_key(clean)

    if key in LOB_ALIASES:
        return LOB_ALIASES[key]

    ibc_match = re.search(r"\bIBC\s*[-:]?\s*(\d{2})\b", clean, re.I)
    if ibc_match:
        return IBC_LINE_CODE_MAP.get(ibc_match.group(1), clean)

    if re.fullmatch(r"\d{2}", clean):
        return IBC_LINE_CODE_MAP.get(clean, clean)

    return clean


def lossq_state_province_context(region_code: Any) -> Dict[str, Any]:
    code = lossq_market_clean(region_code).upper()

    if code in CANADIAN_PROVINCES:
        province = CANADIAN_PROVINCES[code]
        return {
            "country": "Canada",
            "region_code": code,
            "region_name": province["name"],
            "regulator": province["regulator"],
            "field_label": "State / Province",
            "postal_label": "Postal Code",
            "currency": "CAD",
            "date_format": "DD/MM/YYYY",
            "broker_term": "broker",
            "regulatory_phrase": "provincial statutory requirements",
        }

    return {
        "country": "United States",
        "region_code": code,
        "region_name": code,
        "regulator": "State-based insurance department",
        "field_label": "State",
        "postal_label": "ZIP Code",
        "currency": "USD",
        "date_format": "MM/DD/YYYY",
        "broker_term": "agent or broker",
        "regulatory_phrase": "state regulatory requirements",
    }


def lossq_narrative_localization_context(country: str, region_code: str = "", language: str = "en") -> Dict[str, Any]:
    region_context = lossq_state_province_context(region_code)
    country_clean = lossq_market_clean(country).lower()

    if country_clean == "canada":
        return {
            "country": "Canada",
            "currency": "CAD",
            "geography_label": "State / Province",
            "postal_label": "Postal Code",
            "date_format": "DD/MM/YYYY",
            "language": language or "en",
            "regulator": region_context.get("regulator", ""),
            "broker_term": "broker",
            "submission_phrase": "renewal submission",
            "general_liability_term": "Commercial General Liability",
            "include_french_summary": bool(region_code.upper() == "QC" or language == "fr"),
        }

    return {
        "country": "United States",
        "currency": "USD",
        "geography_label": "State",
        "postal_label": "ZIP Code",
        "date_format": "MM/DD/YYYY",
        "language": language or "en",
        "regulator": region_context.get("regulator", ""),
        "broker_term": "agent or broker",
        "submission_phrase": "renewal submission",
        "general_liability_term": "General Liability",
        "include_french_summary": False,
    }


def lossq_apply_exposure_aliases(profile_data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(profile_data, dict):
        return profile_data

    sources = [profile_data]

    for nested_key in ("exposure_inputs", "exposures", "rating_basis", "risk_details"):
        nested = profile_data.get(nested_key)
        if isinstance(nested, dict):
            sources.append(nested)

    for source in sources:
        for key, value in list(source.items()):
            mapped = EXPOSURE_ALIASES.get(lossq_market_key(key))
            if mapped and value not in (None, "") and not lossq_market_clean(profile_data.get(mapped)):
                profile_data[mapped] = value

    return profile_data


def lossq_split_vehicle_driver_counts(profile_data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(profile_data, dict):
        return profile_data

    combined = lossq_market_clean(
        profile_data.get("vehicle_count")
        or profile_data.get("fleet_size")
        or profile_data.get("fleet")
        or ""
    )

    if combined:
        vehicle_match = re.search(r"(\d+)\s*(?:vehicles?|autos?|scheduled autos?|power units?|fleet units?)", combined, re.I)
        driver_match = re.search(r"(\d+)\s*(?:drivers?|operators?)", combined, re.I)

        if vehicle_match:
            profile_data["vehicle_count"] = vehicle_match.group(1)

        if driver_match:
            profile_data["driver_count"] = driver_match.group(1)

    return profile_data


def lossq_normalize_market_profile(profile_data: Optional[Dict[str, Any]] = None, raw_text: Any = "") -> Dict[str, Any]:
    profile_data = dict(profile_data or {})

    profile_data = lossq_apply_exposure_aliases(profile_data)

    # Split combined fleet wording before count cleaning.
    profile_data = lossq_split_vehicle_driver_counts(profile_data)

    for field in MONEY_FIELDS:
        if profile_data.get(field) not in (None, ""):
            cleaned = lossq_market_money(profile_data.get(field))
            if cleaned:
                profile_data[field] = cleaned

    for field in COUNT_FIELDS:
        if profile_data.get(field) not in (None, ""):
            cleaned = lossq_market_count(profile_data.get(field))
            if cleaned:
                profile_data[field] = cleaned

    country = lossq_detect_country(profile_data, raw_text)
    currency = lossq_detect_currency(raw_text, profile_data) or ("CAD" if country == "Canada" else "USD" if country == "United States" else "")
    language = lossq_detect_language(raw_text)

    province = (
        lossq_detect_canadian_province(profile_data.get("postal_code"))
        or lossq_detect_canadian_province(profile_data.get("postcode"))
        or lossq_detect_canadian_province(profile_data.get("province"))
        or lossq_detect_canadian_province(profile_data.get("province_code"))
        or lossq_detect_canadian_province(profile_data.get("state"))
    )

    if province:
        profile_data["state"] = province
        profile_data["province"] = province
        profile_data["province_code"] = province

    carrier_value = (
        profile_data.get("carrier_name")
        or profile_data.get("writing_carrier")
        or profile_data.get("insurer")
        or profile_data.get("carrier")
    )
    normalized_carrier = lossq_normalize_carrier(carrier_value)
    if normalized_carrier:
        profile_data["carrier_name"] = normalized_carrier
        profile_data["writing_carrier"] = normalized_carrier

    if profile_data.get("line_of_business"):
        profile_data["line_of_business"] = lossq_normalize_line_of_business(profile_data.get("line_of_business"))

    policy_lines: List[str] = []
    for row in profile_data.get("policies") or profile_data.get("policy_schedule") or []:
        if not isinstance(row, dict):
            continue

        line = lossq_normalize_line_of_business(
            row.get("line_of_business")
            or row.get("policy_type")
            or row.get("coverage")
            or row.get("line")
        )

        if line and line not in policy_lines:
            policy_lines.append(line)

    if len(policy_lines) > 1:
        profile_data["line_of_business"] = "Multi-line: " + ", ".join(policy_lines)
        profile_data["primary_line_of_business"] = profile_data["line_of_business"]
    elif len(policy_lines) == 1:
        profile_data["line_of_business"] = policy_lines[0]
        profile_data["primary_line_of_business"] = policy_lines[0]

    region_code = province or lossq_market_clean(profile_data.get("state")).upper()
    region_context = lossq_state_province_context(region_code)
    narrative_context = lossq_narrative_localization_context(country, region_code, language)

    profile_data["market_context"] = {
        "country": country,
        "currency": currency,
        "language": language,
        "region_code": region_code,
        "region_context": region_context,
        "narrative_localization": narrative_context,
    }

    # Future database fields. These are safe to ignore until schema supports them.
    profile_data.setdefault("market_country", country)
    profile_data.setdefault("market_region_code", region_code)
    profile_data.setdefault("market_currency", currency)
    profile_data.setdefault("market_language", language)
    profile_data.setdefault("market_regulator", region_context.get("regulator"))
    profile_data.setdefault("market_date_format", region_context.get("date_format"))

    return profile_data


def lossq_market_intelligence_summary(profile_data: Optional[Dict[str, Any]] = None, raw_text: Any = "") -> Dict[str, Any]:
    normalized = lossq_normalize_market_profile(profile_data, raw_text)
    context = normalized.get("market_context") or {}
    region_context = context.get("region_context") or {}

    return {
        "country": context.get("country"),
        "currency": context.get("currency"),
        "language": context.get("language"),
        "region_code": context.get("region_code"),
        "regulator": region_context.get("regulator"),
        "date_format": region_context.get("date_format"),
        "field_label": region_context.get("field_label"),
        "postal_label": region_context.get("postal_label"),
        "line_of_business": normalized.get("line_of_business"),
        "carrier_name": normalized.get("carrier_name"),
        "state": normalized.get("state"),
        "province": normalized.get("province"),
        "vehicle_count": normalized.get("vehicle_count"),
        "driver_count": normalized.get("driver_count"),
        "property_tiv": normalized.get("property_tiv"),
        "payroll": normalized.get("payroll"),
        "revenue": normalized.get("revenue"),
        "market_context": context,
    }
