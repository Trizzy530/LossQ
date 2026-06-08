from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional


POLICY_RE = re.compile(r"\b([A-Z]{2,5}-[A-Z]{2,5}-\d{5,}-\d{2})\b", re.IGNORECASE)
MONEY_RE = re.compile(r"\$?\s*[-(]?\d[\d,]*\.?\d{0,2}\)?")
DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")
CLAIM_RE = re.compile(r"\b([A-Z]{1,5}-\d{2,4}-[A-Z0-9]{3,}|\b[A-Z]{2,5}-\d{2}-\d{4,})\b", re.IGNORECASE)

LOB_BY_POLICY_PREFIX = {
    "AL": "Commercial Auto",
    "AUTO": "Commercial Auto",
    "CA": "Commercial Auto",
    "BA": "Commercial Auto",
    "GL": "General Liability",
    "WC": "Workers Comp",
    "CG": "Motor Truck Cargo",
    "CARGO": "Motor Truck Cargo",
    "MTC": "Motor Truck Cargo",
}

LOB_ALIASES = {
    "auto liability": "Commercial Auto",
    "commercial auto": "Commercial Auto",
    "automobile liability": "Commercial Auto",
    "general liability": "General Liability",
    "workers comp": "Workers Comp",
    "workers compensation": "Workers Comp",
    "worker compensation": "Workers Comp",
    "motor truck cargo": "Motor Truck Cargo",
    "cargo": "Motor Truck Cargo",
}


def _clean(value: Any) -> str:
    return str(value or "").replace("\x7f", "").strip()


def _norm_space(value: Any) -> str:
    return re.sub(r"\s+", " ", _clean(value)).strip()


def _money(value: Any) -> float:
    text = _clean(value)
    if not text or text in {"-", "--"}:
        return 0.0

    negative = text.startswith("(") and text.endswith(")")
    text = text.replace("$", "").replace(",", "").replace("(", "").replace(")", "").strip()

    try:
        number = float(text)
        return -number if negative else number
    except Exception:
        return 0.0


def _date(value: Any) -> Optional[str]:
    text = _clean(value)
    if not text or text == "-":
        return None

    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except Exception:
            pass

    return None


def _lines(raw_text: str) -> List[str]:
    return [_norm_space(line) for line in str(raw_text or "").splitlines() if _norm_space(line)]


def _line_after_label(lines: List[str], label_patterns: List[str]) -> str:
    for index, line in enumerate(lines):
        lowered = line.lower().strip(" :")
        for pattern in label_patterns:
            if lowered == pattern.lower().strip(" :") or lowered.startswith(pattern.lower().strip(" :") + ":"):
                inline = line.split(":", 1)[1].strip() if ":" in line else ""
                if inline:
                    return inline

                for candidate in lines[index + 1 : index + 5]:
                    candidate_clean = _norm_space(candidate)
                    if not candidate_clean:
                        continue
                    # Skip obvious labels.
                    if candidate_clean.lower().strip(" :") in {
                        "account #",
                        "account number",
                        "writing carrier",
                        "carrier",
                        "agency",
                        "report / valuation",
                        "valuation date",
                    }:
                        continue
                    return candidate_clean
    return ""


def _detect_carrier(lines: List[str]) -> str:
    carrier = _line_after_label(lines, ["Writing Carrier", "Carrier", "Insurer", "Insurance Company"])
    if carrier:
        return carrier

    # Many carrier PDFs place the carrier name in the top header before any labels.
    for line in lines[:12]:
        if re.search(r"\b(insurance|mutual|casualty|indemnity|underwriters|carrier)\b", line, re.IGNORECASE):
            if not re.search(r"loss run|claim detail|valuation|page \d", line, re.IGNORECASE):
                return line

    carrier_equals = re.search(r"carrier\s*=\s*([^|\n\r]+)", "\n".join(lines), flags=re.IGNORECASE)
    if carrier_equals:
        return _norm_space(carrier_equals.group(1))

    return ""


def _detect_business_name(lines: List[str]) -> str:
    return _line_after_label(
        lines,
        [
            "Named Insured",
            "Insured",
            "Business Name",
            "Account Name",
            "Named Insured Name",
        ],
    )


def _policy_prefix(policy_number: Any) -> str:
    policy = _clean(policy_number).upper()
    match = re.match(r"[A-Z]+-([A-Z]+)-", policy)
    if match:
        return match.group(1)
    parts = policy.split("-")
    return parts[0] if parts else ""


def _claim_prefix(claim_number: Any) -> str:
    claim = _clean(claim_number).upper()
    parts = claim.split("-")
    return parts[0] if parts else ""


def _lob_from_text(value: Any, fallback_policy: Any = "") -> str:
    text = _clean(value).lower()
    for key, lob in LOB_ALIASES.items():
        if key in text:
            return lob

    prefix = _policy_prefix(fallback_policy)
    return LOB_BY_POLICY_PREFIX.get(prefix, "Unknown")


def _extract_policy_schedule(lines: List[str], carrier: str) -> List[Dict[str, Any]]:
    policies: Dict[str, Dict[str, Any]] = {}

    # Table style:
    # Auto Liability
    # GP-AL-240177-01
    # 10/01/2024
    # 10/01/2025
    # 3
    # $136,250.87
    for index, line in enumerate(lines):
        policy_match = POLICY_RE.search(line)
        if not policy_match:
            continue

        policy_number = policy_match.group(1).upper()
        previous = lines[index - 1] if index > 0 else ""
        lob = _lob_from_text(previous, policy_number)

        # If the source line itself is pipe-delimited, the LOB is usually before the policy number.
        if "|" in line:
            lob = _lob_from_text(line.split(policy_number, 1)[0], policy_number)

        effective_date = ""
        expiration_date = ""
        claim_count = 0
        total_incurred = 0.0

        lookahead = lines[index + 1 : index + 8]
        date_values = [item for item in lookahead if DATE_RE.fullmatch(item)]
        if len(date_values) >= 1:
            effective_date = _date(date_values[0]) or ""
        if len(date_values) >= 2:
            expiration_date = _date(date_values[1]) or ""

        for item in lookahead:
            if re.fullmatch(r"\d{1,4}", item):
                try:
                    claim_count = int(item)
                    break
                except Exception:
                    pass

        money_values = [_money(item) for item in lookahead if "$" in item]
        if money_values:
            total_incurred = money_values[-1]

        existing = policies.get(policy_number, {})
        policies[policy_number] = {
            "policy_number": policy_number,
            "policy_type": lob if lob != "Unknown" else existing.get("policy_type") or "Unknown",
            "line_coverage": lob if lob != "Unknown" else existing.get("line_coverage") or "Unknown",
            "line_of_business": lob if lob != "Unknown" else existing.get("line_of_business") or "Unknown",
            "writing_carrier": carrier or existing.get("writing_carrier") or "",
            "carrier": carrier or existing.get("carrier") or "",
            "effective_date": effective_date or existing.get("effective_date") or "",
            "expiration_date": expiration_date or existing.get("expiration_date") or "",
            "claim_count": claim_count or existing.get("claim_count") or 0,
            "total_paid": existing.get("total_paid", 0),
            "total_reserve": existing.get("total_reserve", 0),
            "total_incurred": total_incurred or existing.get("total_incurred") or 0,
            "source_line": line,
        }

    return list(policies.values())


def _build_policy_map(policies: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    mapping: Dict[str, Dict[str, str]] = {}

    for policy in policies or []:
        policy_number = _clean(policy.get("policy_number")).upper()
        if not policy_number:
            continue

        prefix = _policy_prefix(policy_number)
        lob = _clean(policy.get("line_of_business") or policy.get("policy_type") or policy.get("line_coverage"))
        if not lob or lob == "Unknown":
            lob = LOB_BY_POLICY_PREFIX.get(prefix, "Unknown")

        mapping[prefix] = {
            "policy_number": policy_number,
            "line_of_business": lob,
            "policy_type": lob,
        }

    return mapping


def _extract_claims_from_multiline_rows(lines: List[str], policy_map: Dict[str, Dict[str, str]]) -> List[Dict[str, Any]]:
    claims: List[Dict[str, Any]] = []
    index = 0

    while index < len(lines) - 8:
        policy_line = lines[index]
        claim_line = lines[index + 1]

        policy_match = POLICY_RE.fullmatch(policy_line)
        claim_match = CLAIM_RE.fullmatch(claim_line)

        if not policy_match or not claim_match:
            index += 1
            continue

        policy_number = policy_match.group(1).upper()
        claim_number = claim_match.group(1).upper()

        dol = lines[index + 2] if index + 2 < len(lines) else ""
        rpt = lines[index + 3] if index + 3 < len(lines) else ""
        closed = lines[index + 4] if index + 4 < len(lines) else ""
        status = lines[index + 5] if index + 5 < len(lines) else ""
        description = lines[index + 6] if index + 6 < len(lines) else ""
        paid = lines[index + 7] if index + 7 < len(lines) else ""
        reserve = lines[index + 8] if index + 8 < len(lines) else ""
        incurred = lines[index + 9] if index + 9 < len(lines) else ""

        if not DATE_RE.fullmatch(dol) or not DATE_RE.fullmatch(rpt):
            index += 1
            continue

        if not re.search(r"\b(open|closed|pending|reopened)\b", status, re.IGNORECASE):
            index += 1
            continue

        if "$" not in paid or "$" not in reserve or "$" not in incurred:
            index += 1
            continue

        prefix = _claim_prefix(claim_number)
        mapped = policy_map.get(prefix, {})
        lob = mapped.get("line_of_business") or _lob_from_text("", policy_number)

        paid_amount = _money(paid)
        reserve_amount = _money(reserve)
        total_incurred = _money(incurred)

        claims.append(
            {
                "claim_number": claim_number,
                "policy_number": mapped.get("policy_number") or policy_number,
                "line_of_business": lob,
                "claim_type": lob,
                "cause_of_loss": "",
                "claimant_type": "",
                "date_of_loss": _date(dol),
                "loss_date": _date(dol),
                "date_reported": _date(rpt),
                "reported_date": _date(rpt),
                "date_closed": _date(closed),
                "status": "Open" if status.lower().startswith(("open", "pending", "reopened")) else "Closed",
                "description": description,
                "paid_amount": paid_amount,
                "paid": paid_amount,
                "reserve_amount": reserve_amount,
                "reserve": reserve_amount,
                "total_incurred": total_incurred,
                "total_amount": total_incurred,
                "litigation": bool(re.search(r"litigat|attorney|suit", description, re.IGNORECASE)),
                "litigation_status": "Litigation/Attorney Indicator"
                if re.search(r"litigat|attorney|suit", description, re.IGNORECASE)
                else "",
                "attorney_assigned": bool(re.search(r"attorney", description, re.IGNORECASE)),
                "suit_filed": bool(re.search(r"suit", description, re.IGNORECASE)),
                "flag": "Litigation exposure" if re.search(r"litigat|attorney|suit", description, re.IGNORECASE) else "",
                "source_line": " ".join(lines[index : index + 10]),
            }
        )

        index += 10

    return claims


def _is_fake_zero_header_claim(claim: Dict[str, Any]) -> bool:
    claim_number = _clean(claim.get("claim_number")).upper()
    source_line = _clean(claim.get("source_line"))
    description = _clean(claim.get("description"))

    total = _money(claim.get("total_incurred") or claim.get("total_amount"))
    paid = _money(claim.get("paid_amount") or claim.get("paid"))
    reserve = _money(claim.get("reserve_amount") or claim.get("reserve"))

    if total != 0 or paid != 0 or reserve != 0:
        return False

    header_like_claim_numbers = {
        "AUTO-LIABILITY",
        "GENERAL-LIABILITY",
        "WORKERS-COMP",
        "MOTOR-TRUCK-CARGO",
        "CARGO",
        "POLICY",
        "CLAIM",
        "CLAIM-NUMBER",
    }

    if claim_number in header_like_claim_numbers:
        return True

    if re.fullmatch(r"(GL|WC|CG|AL)-\d{5,}", claim_number):
        return True

    header_text = f"{source_line} {description}".lower()
    if "carrier=" in header_text and (" eff " in f" {header_text} " or " exp " in f" {header_text} "):
        return True

    if "policy" in header_text and "claim" not in header_text and "carrier" in header_text:
        return True

    return False


def _clean_existing_claims(claims: List[Dict[str, Any]], policy_map: Dict[str, Dict[str, str]]) -> List[Dict[str, Any]]:
    cleaned: List[Dict[str, Any]] = []
    seen = set()

    for original in claims or []:
        if not isinstance(original, dict):
            continue

        claim = dict(original)
        if _is_fake_zero_header_claim(claim):
            continue

        claim_number = _clean(claim.get("claim_number")).upper()
        if not claim_number or claim_number in {"UNKNOWN", "CLAIM NUMBER", "CLAIM"}:
            continue

        prefix = _claim_prefix(claim_number)
        if prefix in policy_map:
            claim["policy_number"] = policy_map[prefix]["policy_number"]
            claim["line_of_business"] = policy_map[prefix]["line_of_business"]
            claim["claim_type"] = policy_map[prefix]["policy_type"]

        total = _money(claim.get("total_incurred") or claim.get("total_amount"))
        paid = _money(claim.get("paid_amount") or claim.get("paid"))
        reserve = _money(claim.get("reserve_amount") or claim.get("reserve"))

        if total <= 0 and (paid > 0 or reserve > 0):
            claim["total_incurred"] = paid + reserve

        key = (_clean(claim.get("claim_number")).upper(), _clean(claim.get("policy_number")).upper())
        if key in seen:
            continue
        seen.add(key)

        cleaned.append(claim)

    return cleaned


def _rollup_policies(policies: List[Dict[str, Any]], claims: List[Dict[str, Any]], carrier: str) -> List[Dict[str, Any]]:
    by_policy = {str(p.get("policy_number") or "").upper(): dict(p) for p in policies or [] if p.get("policy_number")}

    for claim in claims:
        policy_number = _clean(claim.get("policy_number")).upper()
        if not policy_number:
            continue

        prefix = _policy_prefix(policy_number)
        lob = _clean(claim.get("line_of_business")) or LOB_BY_POLICY_PREFIX.get(prefix, "Unknown")

        if policy_number not in by_policy:
            by_policy[policy_number] = {
                "policy_number": policy_number,
                "policy_type": lob,
                "line_coverage": lob,
                "line_of_business": lob,
                "writing_carrier": carrier,
                "carrier": carrier,
                "effective_date": "",
                "expiration_date": "",
                "claim_count": 0,
                "total_paid": 0,
                "total_reserve": 0,
                "total_incurred": 0,
            }

        row = by_policy[policy_number]
        row["policy_type"] = lob if lob != "Unknown" else row.get("policy_type") or lob
        row["line_coverage"] = lob if lob != "Unknown" else row.get("line_coverage") or lob
        row["line_of_business"] = lob if lob != "Unknown" else row.get("line_of_business") or lob
        row["writing_carrier"] = carrier or row.get("writing_carrier") or ""
        row["carrier"] = carrier or row.get("carrier") or ""

    for row in by_policy.values():
        row["claim_count"] = 0
        row["total_paid"] = 0.0
        row["total_reserve"] = 0.0
        row["total_incurred"] = 0.0

    for claim in claims:
        policy_number = _clean(claim.get("policy_number")).upper()
        if policy_number not in by_policy:
            continue
        by_policy[policy_number]["claim_count"] += 1
        by_policy[policy_number]["total_paid"] += _money(claim.get("paid_amount") or claim.get("paid"))
        by_policy[policy_number]["total_reserve"] += _money(claim.get("reserve_amount") or claim.get("reserve"))
        by_policy[policy_number]["total_incurred"] += _money(claim.get("total_incurred") or claim.get("total_amount"))

    return list(by_policy.values())


def cleanup_loss_run_extraction(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministic post-extraction cleanup for messy commercial loss runs.

    This runs after the universal parser and before upload persistence. It does not
    change OCR or file upload behavior. It only corrects fields that are already
    visible in raw_text_preview and removes obvious non-claim header rows.
    """
    if not isinstance(parsed, dict):
        return parsed

    cleaned = dict(parsed)
    raw_text = str(
        cleaned.get("raw_text_preview")
        or cleaned.get("raw_text")
        or cleaned.get("text")
        or cleaned.get("extracted_text")
        or ""
    )
    lines = _lines(raw_text)

    if not lines:
        return cleaned

    profile = dict(cleaned.get("profile") or {})
    carrier = _detect_carrier(lines)
    business_name = _detect_business_name(lines)
    account_number = _line_after_label(lines, ["Account #", "Account Number", "Account No", "Customer Number"])

    existing_policies = cleaned.get("policies") or profile.get("policies") or []
    extracted_policies = _extract_policy_schedule(lines, carrier)
    policies = extracted_policies or existing_policies or []

    policy_map = _build_policy_map(policies)

    raw_claims = cleaned.get("claims") or cleaned.get("parsed_claims") or cleaned.get("saved_claim_rows") or []
    multiline_claims = _extract_claims_from_multiline_rows(lines, policy_map)

    # Prefer the deterministic multiline parse when it finds real rows. Otherwise
    # clean the universal parser output.
    if len(multiline_claims) >= 2 and sum(_money(c.get("total_incurred")) for c in multiline_claims) > 0:
        claims = multiline_claims
    else:
        claims = _clean_existing_claims(raw_claims, policy_map)

    policies = _rollup_policies(policies, claims, carrier)

    if business_name:
        profile["business_name"] = business_name
        profile["insured"] = business_name
        profile["named_insured"] = business_name

    if carrier:
        profile["carrier_name"] = carrier
        profile["writing_carrier"] = carrier

    if account_number:
        profile["account_number"] = account_number
        profile["customer_number"] = profile.get("customer_number") or account_number

    if policies:
        profile["policy_number"] = policies[0].get("policy_number") or profile.get("policy_number") or ""
        profile["effective_date"] = policies[0].get("effective_date") or profile.get("effective_date") or ""
        profile["expiration_date"] = policies[0].get("expiration_date") or profile.get("expiration_date") or ""
        profile["policies"] = policies

    profile["raw_text_preview"] = raw_text[:6000]

    validation = dict(cleaned.get("validation") or profile.get("validation") or {})
    validation["claim_count"] = len(claims)
    validation["policy_count"] = len(policies)
    validation["calculated_total_incurred"] = round(sum(_money(c.get("total_incurred")) for c in claims), 2)
    validation["cleanup_applied"] = True
    validation["cleanup_engine"] = "LossQ Parser Cleanup V1"
    validation["warnings"] = [
        warning
        for warning in validation.get("warnings", [])
        if "named insured" not in str(warning).lower()
        and "carrier" not in str(warning).lower()
    ]

    cleaned["profile"] = profile
    cleaned["policies"] = policies
    cleaned["claims"] = claims
    cleaned["parsed_claims"] = claims
    cleaned["saved_claim_rows"] = claims
    cleaned["claim_count"] = len(claims)
    cleaned["policy_count"] = len(policies)
    cleaned["validation"] = validation
    cleaned["raw_text_preview"] = raw_text[:6000]

    return cleaned
