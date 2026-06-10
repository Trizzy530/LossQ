"""
LossQ Universal Commercial Line-of-Business Intelligence
Phase 3A

Purpose:
- Make LossQ process loss runs for all commercial business types.
- Avoid transportation-only assumptions.
- Detect policy line, claim type, claim category, and underwriting concern.
- Safe helper module: does not touch auth, database, CORS, pricing, or dashboard logic.
"""

import re
from typing import Any, Dict, List, Optional


# ------------------------------------------------------------
# Universal Commercial Line Mapping
# ------------------------------------------------------------

LOB_PREFIX_MAP = {
    # Commercial Auto / Transportation
    "AL": "Commercial Auto",
    "CA": "Commercial Auto",
    "AUTO": "Commercial Auto",
    "BAP": "Commercial Auto",
    "APD": "Commercial Auto Physical Damage",
    "PD": "Commercial Auto Physical Damage",
    "MTC": "Motor Truck Cargo",
    "CG": "Motor Truck Cargo",
    "CARGO": "Motor Truck Cargo",

    # General Liability
    "GL": "General Liability",
    "CGL": "General Liability",
    "LIAB": "General Liability",

    # Workers Compensation
    "WC": "Workers Compensation",
    "WCOMP": "Workers Compensation",
    "WORKCOMP": "Workers Compensation",

    # Property / Package / BOP
    "CP": "Commercial Property",
    "PROP": "Commercial Property",
    "PROPERTY": "Commercial Property",
    "BOP": "Business Owners Policy",
    "PKG": "Commercial Package",

    # Inland Marine
    "IM": "Inland Marine",
    "INLAND": "Inland Marine",

    # Professional Liability / E&O
    "PL": "Professional Liability",
    "PROF": "Professional Liability",
    "EO": "Professional Liability",
    "E&O": "Professional Liability",
    "E_O": "Professional Liability",
    "ERRORS": "Professional Liability",

    # Directors & Officers
    "DO": "Directors & Officers",
    "D&O": "Directors & Officers",
    "D_O": "Directors & Officers",
    "DNO": "Directors & Officers",

    # Employment Practices
    "EP": "Employment Practices Liability",
    "EPL": "Employment Practices Liability",
    "EPLI": "Employment Practices Liability",

    # Cyber
    "CY": "Cyber Liability",
    "CYBER": "Cyber Liability",
    "TECH": "Technology / Cyber Liability",

    # Umbrella / Excess
    "UM": "Umbrella / Excess Liability",
    "UMB": "Umbrella / Excess Liability",
    "XS": "Umbrella / Excess Liability",
    "EXCESS": "Umbrella / Excess Liability",

    # Crime / Fidelity
    "CR": "Crime / Fidelity",
    "CRIME": "Crime / Fidelity",
    "FID": "Crime / Fidelity",

    # Environmental
    "ENV": "Environmental Liability",
    "POLL": "Pollution Liability",
    "POLLUTION": "Pollution Liability",

    # Product Liability
    "PROD": "Product Liability",
    "PRODUCT": "Product Liability",
}


# ------------------------------------------------------------
# Business Type Keywords
# ------------------------------------------------------------

BUSINESS_TYPE_KEYWORDS = {
    "Transportation / Trucking": [
        "trucking", "transport", "freight", "fleet", "driver", "tractor",
        "trailer", "cargo", "delivery", "logistics", "hauling"
    ],
    "Contractor / Construction": [
        "contractor", "construction", "roofing", "plumbing", "electrical",
        "hvac", "carpentry", "renovation", "excavation", "subcontractor"
    ],
    "Restaurant / Hospitality": [
        "restaurant", "bar", "grill", "food", "cafe", "kitchen",
        "hospitality", "hotel", "motel", "catering"
    ],
    "Retail / Storefront": [
        "retail", "store", "shop", "customer", "mall", "merchandise",
        "inventory", "cashier", "sales floor"
    ],
    "Real Estate / Property Owner": [
        "property owner", "real estate", "apartment", "tenant", "landlord",
        "building", "premises", "condo", "hoa", "rental"
    ],
    "Professional Services": [
        "consultant", "advisor", "attorney", "law firm", "accountant",
        "cpa", "engineer", "architect", "professional services"
    ],
    "Healthcare / Medical Office": [
        "medical", "clinic", "doctor", "physician", "dental", "healthcare",
        "patient", "nurse", "therapy"
    ],
    "Technology / SaaS": [
        "software", "saas", "technology", "data", "cyber", "cloud",
        "platform", "application", "breach"
    ],
    "Manufacturing / Warehouse": [
        "manufacturing", "warehouse", "factory", "machine", "equipment",
        "production", "forklift", "assembly"
    ],
    "Staffing / Employment Services": [
        "staffing", "temp", "temporary worker", "employment agency",
        "placement", "workforce"
    ],
}


# ------------------------------------------------------------
# Claim Category Keywords
# ------------------------------------------------------------

CLAIM_CATEGORY_KEYWORDS = {
    "Bodily Injury": [
        "bodily injury", "injury", "injured", "fall", "slip", "trip",
        "fracture", "sprain", "strain", "medical", "hospital"
    ],
    "Property Damage": [
        "property damage", "damage", "water", "fire", "smoke", "wind",
        "hail", "theft", "vandalism", "collision", "vehicle damage"
    ],
    "Workers Compensation Injury": [
        "workers comp", "employee injury", "lost time", "medical only",
        "strain", "sprain", "back injury", "shoulder", "knee", "work injury"
    ],
    "Professional Error / E&O": [
        "error", "omission", "negligence", "missed deadline", "professional",
        "malpractice", "advice", "consulting", "design error"
    ],
    "Employment Practices": [
        "wrongful termination", "harassment", "discrimination", "retaliation",
        "wage", "employment", "hostile work environment"
    ],
    "Cyber Incident": [
        "cyber", "breach", "ransomware", "phishing", "data loss",
        "business interruption", "privacy", "network"
    ],
    "Management Liability": [
        "director", "officer", "shareholder", "fiduciary", "securities",
        "mismanagement", "board"
    ],
    "Cargo / Inland Marine": [
        "cargo", "freight", "load", "shipment", "tools", "equipment",
        "inland marine", "transit"
    ],
    "Product / Completed Operations": [
        "product", "completed operations", "defect", "installation",
        "workmanship", "completed work"
    ],
    "Crime / Theft": [
        "crime", "employee theft", "dishonesty", "fraud", "embezzlement",
        "forgery", "theft"
    ],
}


# ------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------

def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _upper_clean(value: Any) -> str:
    return _clean_text(value).upper()


def _combined_claim_text(claim: Dict[str, Any]) -> str:
    fields = [
        "claim_number",
        "policy_number",
        "line_of_business",
        "lob",
        "coverage",
        "claim_type",
        "description",
        "loss_description",
        "cause_of_loss",
        "business_name",
        "insured_name",
        "carrier_name",
    ]

    parts: List[str] = []
    for field in fields:
        value = claim.get(field)
        if value:
            parts.append(str(value))

    return " ".join(parts).lower()


def extract_claim_prefix(claim_number: Any) -> Optional[str]:
    """
    Pulls a likely prefix from claim numbers such as:
    GL-12345
    WC12345
    CA 998877
    CYBER-2024-0001
    PL/44551
    """
    raw = _upper_clean(claim_number)
    if not raw:
        return None

    raw = raw.replace("/", "-").replace("_", "-").replace(" ", "-")

    # First token before dash
    first_token = raw.split("-")[0].strip()
    first_token = re.sub(r"[^A-Z&]", "", first_token)

    if first_token in LOB_PREFIX_MAP:
        return first_token

    # Try first 2 to 5 letters
    letters = re.sub(r"[^A-Z&]", "", raw)
    for size in [5, 4, 3, 2]:
        possible = letters[:size]
        if possible in LOB_PREFIX_MAP:
            return possible

    return None


def detect_line_of_business(claim: Dict[str, Any]) -> str:
    """
    Detect line of business from claim fields, claim number prefixes, policy number,
    coverage text, and description.
    """

    # 1. Existing explicit values should win if useful
    explicit_values = [
        claim.get("line_of_business"),
        claim.get("lob"),
        claim.get("coverage"),
        claim.get("policy_type"),
    ]

    for value in explicit_values:
        text = _upper_clean(value)
        if not text:
            continue

        normalized = re.sub(r"[^A-Z&]", "", text)

        if text in LOB_PREFIX_MAP:
            return LOB_PREFIX_MAP[text]

        if normalized in LOB_PREFIX_MAP:
            return LOB_PREFIX_MAP[normalized]

        for key, lob_name in LOB_PREFIX_MAP.items():
            if key in text:
                return lob_name

    # 2. Claim number prefix
    prefix = extract_claim_prefix(claim.get("claim_number"))
    if prefix:
        return LOB_PREFIX_MAP.get(prefix, "Unknown / Other Commercial Line")

    # 3. Policy number prefix
    prefix = extract_claim_prefix(claim.get("policy_number"))
    if prefix:
        return LOB_PREFIX_MAP.get(prefix, "Unknown / Other Commercial Line")

    # 4. Keyword scan across all text
    text = _combined_claim_text(claim)

    keyword_lob_rules = [
        ("Cyber Liability", ["cyber", "breach", "ransomware", "phishing", "data loss"]),
        ("Professional Liability", ["errors and omissions", "e&o", "professional liability", "negligence", "malpractice"]),
        ("Directors & Officers", ["directors", "officers", "d&o", "board", "shareholder"]),
        ("Employment Practices Liability", ["epli", "wrongful termination", "harassment", "discrimination"]),
        ("Workers Compensation", ["workers comp", "employee injury", "lost time", "medical only"]),
        ("Commercial Property", ["property", "building", "fire", "water damage", "wind", "hail"]),
        ("General Liability", ["general liability", "premises", "slip and fall", "bodily injury"]),
        ("Motor Truck Cargo", ["cargo", "freight", "shipment", "load"]),
        ("Commercial Auto", ["auto", "vehicle", "collision", "driver", "truck", "tractor", "trailer"]),
        ("Inland Marine", ["inland marine", "equipment", "tools", "contractor equipment"]),
        ("Umbrella / Excess Liability", ["umbrella", "excess"]),
    ]

    for lob_name, keywords in keyword_lob_rules:
        if any(keyword in text for keyword in keywords):
            return lob_name

    return "Unknown / Other Commercial Line"


def detect_business_type(claim: Dict[str, Any]) -> str:
    text = _combined_claim_text(claim)

    for business_type, keywords in BUSINESS_TYPE_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return business_type

    lob = detect_line_of_business(claim)

    if lob in ["Commercial Auto", "Motor Truck Cargo", "Commercial Auto Physical Damage"]:
        return "Transportation / Trucking"
    if lob in ["Professional Liability"]:
        return "Professional Services"
    if lob in ["Commercial Property", "Business Owners Policy", "Commercial Package"]:
        return "General Commercial Business"
    if lob in ["Cyber Liability", "Technology / Cyber Liability"]:
        return "Technology / SaaS"
    if lob in ["Workers Compensation"]:
        return "Employer / Workforce Exposure"

    return "General Commercial Business"


def detect_claim_category(claim: Dict[str, Any]) -> str:
    text = _combined_claim_text(claim)

    for category, keywords in CLAIM_CATEGORY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return category

    lob = detect_line_of_business(claim)

    if lob == "Commercial Auto":
        return "Auto Liability / Physical Damage"
    if lob == "General Liability":
        return "General Liability Claim"
    if lob == "Workers Compensation":
        return "Workers Compensation Injury"
    if lob == "Commercial Property":
        return "Commercial Property Loss"
    if lob == "Professional Liability":
        return "Professional Error / E&O"
    if lob == "Cyber Liability":
        return "Cyber Incident"
    if lob == "Employment Practices Liability":
        return "Employment Practices"
    if lob == "Directors & Officers":
        return "Management Liability"
    if lob in ["Motor Truck Cargo", "Inland Marine"]:
        return "Cargo / Inland Marine"

    return "Other Commercial Claim"


def detect_underwriting_concerns(claim: Dict[str, Any]) -> List[str]:
    concerns: List[str] = []

    text = _combined_claim_text(claim)
    lob = detect_line_of_business(claim)
    category = detect_claim_category(claim)

    total_incurred = _safe_float(
        claim.get("total_incurred")
        or claim.get("incurred")
        or claim.get("total")
        or claim.get("amount")
    )
    reserve = _safe_float(
        claim.get("reserve")
        or claim.get("outstanding_reserve")
        or claim.get("case_reserve")
    )

    status = _clean_text(claim.get("status")).lower()

    if total_incurred >= 100000:
        concerns.append("Large loss severity")

    if total_incurred >= 50000:
        concerns.append("Material claim severity")

    if reserve >= 25000:
        concerns.append("Open reserve concern")

    if "open" in status:
        concerns.append("Open claim requires underwriting review")

    if any(word in text for word in ["litigation", "lawsuit", "attorney", "suit", "legal"]):
        concerns.append("Litigation exposure")

    if lob == "Commercial Auto":
        if any(word in text for word in ["collision", "driver", "rear-end", "intersection", "vehicle"]):
            concerns.append("Auto liability frequency/severity exposure")

    if lob == "General Liability":
        if any(word in text for word in ["slip", "fall", "premises", "customer", "bodily injury"]):
            concerns.append("Premises liability exposure")
        if any(word in text for word in ["completed operations", "installation", "workmanship"]):
            concerns.append("Completed operations exposure")

    if lob == "Workers Compensation":
        if any(word in text for word in ["lost time", "indemnity", "return to work"]):
            concerns.append("Lost-time workers compensation exposure")
        if any(word in text for word in ["strain", "sprain", "back", "shoulder", "knee"]):
            concerns.append("Employee injury pattern")

    if lob == "Commercial Property":
        if any(word in text for word in ["fire", "water", "wind", "hail", "cat", "theft"]):
            concerns.append("Property loss exposure")

    if lob == "Professional Liability":
        if any(word in text for word in ["error", "omission", "negligence", "malpractice", "missed deadline"]):
            concerns.append("Professional negligence / E&O exposure")

    if lob == "Cyber Liability":
        if any(word in text for word in ["breach", "ransomware", "phishing", "business interruption"]):
            concerns.append("Cyber event severity exposure")

    if lob == "Employment Practices Liability":
        concerns.append("Employment practices litigation exposure")

    if lob == "Directors & Officers":
        concerns.append("Management liability exposure")

    if not concerns:
        concerns.append(f"{category} requires standard underwriting review")

    # Remove duplicates while preserving order
    unique: List[str] = []
    for concern in concerns:
        if concern not in unique:
            unique.append(concern)

    return unique


def enrich_claim_with_universal_lob(claim: Dict[str, Any]) -> Dict[str, Any]:
    """
    Adds universal commercial insurance intelligence to a claim dictionary.
    This is safe to call on every parsed claim.
    """

    if claim is None:
        claim = {}

    enriched = dict(claim)

    line_of_business = detect_line_of_business(enriched)
    business_type = detect_business_type(enriched)
    claim_category = detect_claim_category(enriched)
    concerns = detect_underwriting_concerns(enriched)

    enriched["line_of_business"] = line_of_business
    enriched["lob"] = line_of_business
    enriched["business_type"] = business_type
    enriched["claim_category"] = claim_category
    enriched["underwriting_concerns"] = concerns

    return enriched


def enrich_claims_with_universal_lob(claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Enriches a list of parsed claims.
    """

    if not claims:
        return []

    enriched_claims: List[Dict[str, Any]] = []

    for claim in claims:
        try:
            enriched_claims.append(enrich_claim_with_universal_lob(claim))
        except Exception:
            # Never let universal LOB detection break upload processing.
            fallback = dict(claim or {})
            fallback["line_of_business"] = fallback.get("line_of_business") or "Unknown / Other Commercial Line"
            fallback["lob"] = fallback.get("lob") or fallback["line_of_business"]
            fallback["business_type"] = fallback.get("business_type") or "General Commercial Business"
            fallback["claim_category"] = fallback.get("claim_category") or "Other Commercial Claim"
            fallback["underwriting_concerns"] = fallback.get("underwriting_concerns") or [
                "Claim requires standard underwriting review"
            ]
            enriched_claims.append(fallback)

    return enriched_claims


def summarize_lob_mix(claims: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Creates a summary of lines of business and business types found in the uploaded loss run.
    """

    summary: Dict[str, Any] = {
        "line_of_business_counts": {},
        "business_type_counts": {},
        "claim_category_counts": {},
        "dominant_line_of_business": "Unknown / Other Commercial Line",
        "dominant_business_type": "General Commercial Business",
    }

    if not claims:
        return summary

    enriched_claims = enrich_claims_with_universal_lob(claims)

    for claim in enriched_claims:
        lob = claim.get("line_of_business") or "Unknown / Other Commercial Line"
        business_type = claim.get("business_type") or "General Commercial Business"
        category = claim.get("claim_category") or "Other Commercial Claim"

        summary["line_of_business_counts"][lob] = summary["line_of_business_counts"].get(lob, 0) + 1
        summary["business_type_counts"][business_type] = summary["business_type_counts"].get(business_type, 0) + 1
        summary["claim_category_counts"][category] = summary["claim_category_counts"].get(category, 0) + 1

    if summary["line_of_business_counts"]:
        summary["dominant_line_of_business"] = max(
            summary["line_of_business_counts"],
            key=summary["line_of_business_counts"].get,
        )

    if summary["business_type_counts"]:
        summary["dominant_business_type"] = max(
            summary["business_type_counts"],
            key=summary["business_type_counts"].get,
        )

    return summary


def _safe_float(value: Any) -> float:
    if value is None:
        return 0.0

    try:
        cleaned = str(value)
        cleaned = cleaned.replace("$", "")
        cleaned = cleaned.replace(",", "")
        cleaned = cleaned.replace("(", "-")
        cleaned = cleaned.replace(")", "")
        cleaned = cleaned.strip()

        if cleaned == "":
            return 0.0

        return float(cleaned)
    except Exception:
        return 0.0