rom __future__ import annotations

import re
from typing import Any
from datetime import datetime

POLICY_TYPE_KEYWORDS = [
    "Commercial Auto",
    "Business Auto",
    "General Liability",
    "Motor Truck Cargo",
    "Workers Compensation",
    "Workers Comp",
    "Umbrella",
    "Excess Liability",
    "Commercial Package Policy",
    "Package Policy",
    "Cargo",
    "Property",
    "Inland Marine",
]

CARRIER_KEYWORDS = [
    "Travelers",
    "GEICO",
    "GIECO",
    "Progressive",
    "State Auto Insurance Group",
    "State Auto",
    "The Hartford",
    "Hartford",
    "Liberty Mutual",
    "Nationwide",
    "CNA",
    "Zurich",
    "Chubb",
    "AmTrust",
    "Berkshire Hathaway",
    "Vanliner",
    "Continental Western",
    "Auto-Owners",
    "Sentry",
    "Great West",
    "Old Republic",
    "Canal Insurance",
]


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def lines_from_text(text: str) -> list[str]:
    return [clean_text(line) for line in (text or "").splitlines() if clean_text(line)]


def money(value: Any) -> float:
    text = clean_text(value)
    if not text:
        return 0.0
    text = text.replace("$", "").replace(",", "")
    text = text.replace("(", "-").replace(")", "")
    text = re.sub(r"[^0-9.\-]", "", text)
    try:
        return float(text or 0)
    except Exception:
        return 0.0


def is_money_line(value: Any) -> bool:
    return bool(re.fullmatch(r"\$?\(?\d[\d,]*(?:\.\d{2})?\)?", clean_text(value)))


def is_date_line(value: Any) -> bool:
    return bool(re.fullmatch(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", clean_text(value)))


def normalize_date(value: Any) -> str:
    text = clean_text(value)
    match = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", text)
    if not match:
        return ""
    month = int(match.group(1))
    day = int(match.group(2))
    year = match.group(3)
    if len(year) == 2:
        year = "20" + year
    return f"{year}-{month:02d}-{day:02d}"


def display_date(value: Any) -> str:
    text = clean_text(value)
    match = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", text)
    if not match:
        return ""
    month = int(match.group(1))
    day = int(match.group(2))
    year = match.group(3)
    if len(year) == 2:
        year = "20" + year
    return f"{month:02d}/{day:02d}/{year}"


def extract_pdf_text_all_pages(file_path: str) -> str:
    text_data = ""
    try:
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        page_texts = []
        for page_index, page in enumerate(reader.pages):
            extracted = page.extract_text() or ""
            page_texts.append(f"\n\n--- PAGE {page_index + 1} OF {len(reader.pages)} ---\n{extracted}")
        text_data = "\n".join(page_texts).strip()
    except Exception:
        text_data = ""

    if len(text_data.strip()) >= 100:
        return text_data

    try:
        from pdf2image import convert_from_path
        import pytesseract
        images = convert_from_path(file_path, dpi=250)
        ocr_pages = []
        for page_index, image in enumerate(images):
            page_text = pytesseract.image_to_string(image) or ""
            ocr_pages.append(f"\n\n--- OCR PAGE {page_index + 1} OF {len(images)} ---\n{page_text}")
        return "\n".join(ocr_pages).strip()
    except Exception as error:
        return text_data or f"OCR failed: {error}"


def find_after_label(text: str, labels: list[str], max_chars: int = 160) -> str:
    lines = lines_from_text(text)
    for index, line in enumerate(lines):
        upper_line = line.upper().strip(": ")
        for label in labels:
            upper_label = label.upper()
            if upper_line == upper_label and index + 1 < len(lines):
                return clean_text(lines[index + 1])[:max_chars]
            if upper_line.startswith(upper_label + ":"):
                return clean_text(line.split(":", 1)[1])[:max_chars]
            if upper_label in upper_line and ":" in line:
                left, right = line.split(":", 1)
                if upper_label in left.upper():
                    value = re.split(r"\s{2,}| Account | Policy | Carrier | Agency | Evaluation | Report ", right, flags=re.I)[0]
                    return clean_text(value)[:max_chars]
    blob = clean_text(text)
    for label in labels:
        pattern = re.compile(rf"{re.escape(label)}\s*[:#\-]?\s*(.{{1,{max_chars}}})", re.I)
        match = pattern.search(blob)
        if match:
            value = re.split(r"\s{2,}| Account | Policy | Carrier | Agency | Evaluation | Report ", match.group(1), flags=re.I)[0]
            return clean_text(value)[:max_chars]
    return ""


def normalize_carrier(value: str) -> str:
    upper = clean_text(value).upper()
    if "GIECO" in upper or "GEICO" in upper:
        return "GEICO"
    if "TRAVELERS" in upper:
        return "Travelers"
    if "PROGRESSIVE" in upper:
        return "Progressive"
    if "STATE AUTO" in upper:
        return "State Auto"
    return clean_text(value)


def detect_business_name(text: str) -> str:
    for line in lines_from_text(text)[:120]:
        match = re.search(r"(?:Named Insured|Insured Name|Insured|Account Name|Customer Name|Client Name)\s*[:#\-]\s*(.+?)(?:\s{2,}|\s+Account\s+(?:No|Number)[:#]|\s+Policy\s+(?:No|Number)[:#]|$)", line, re.I)
        if match:
            return clean_text(match.group(1))[:160]

    value = find_after_label(text, ["Named Insured", "Insured Name", "Insured", "Account Name", "Customer Name", "Client Name"], 160)
    if value:
        return re.split(r"\s{2,}|\s+Account\s+(?:No|Number)[:#]", value, flags=re.I)[0].strip()
    for line in lines_from_text(text)[:120]:
        upper = line.upper()
        if (" LLC" in upper or " INC" in upper or " COMPANY" in upper or " GROUP" in upper) and "INSURANCE" not in upper and "LOSS RUN" not in upper:
            return line
    return ""


def detect_account_number(text: str) -> str:
    value = find_after_label(text, ["Account Number", "Account No", "Customer Number", "Customer No", "Client Number", "Acct #", "Acct No"], 120)
    if value:
        match = re.search(r"\b[A-Z]{1,10}-?ACCT-?[A-Z0-9]{2,30}\b|\b[A-Z0-9]{2,12}-[A-Z0-9]{2,30}-[A-Z0-9]{2,12}\b", value, re.I)
        if match:
            return match.group(0).upper()
        return value.upper()
    account_like = re.search(r"\b[A-Z]{1,10}-?ACCT-?[A-Z0-9]{2,30}\b", text, re.I)
    return account_like.group(0).upper() if account_like else ""


def detect_report_date(text: str) -> str:
    value = find_after_label(text, ["Valuation Date", "Evaluation Date", "Report Date", "Loss Run Date", "Run Date", "As Of", "Report Run"], 120)
    return normalize_date(value)


def detect_policy_period(text: str) -> tuple[str, str]:
    dates = re.findall(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", text or "")
    policy_dates = [d for d in dates if d not in {"05/31/2026", "06/03/2026"}]
    if len(policy_dates) >= 2:
        return normalize_date(policy_dates[0]), normalize_date(policy_dates[1])
    return "", ""


def normalize_policy_type(value: str) -> str:
    upper = clean_text(value).upper()
    if "WORKERS" in upper or upper == "WC":
        return "Workers Compensation"
    if "GENERAL" in upper and "LIABILITY" in upper or upper == "GL":
        return "General Liability"
    if "BUSINESS AUTO" in upper:
        return "Business Auto"
    if "AUTO" in upper:
        return "Commercial Auto"
    if "MOTOR" in upper and "CARGO" in upper or "CARGO" in upper:
        return "Motor Truck Cargo"
    if "UMBRELLA" in upper:
        return "Umbrella"
    if "EXCESS" in upper:
        return "Excess Liability"
    if "PROPERTY" in upper:
        return "Property"
    return clean_text(value) or "Policy"


def looks_like_policy_number(value: str) -> bool:
    text = clean_text(value).upper()
    if len(text) < 5:
        return False
    if "ACCT" in text:
        return False
    patterns = [
        r"\b[A-Z]{2,5}-(?:AUTO|GL|CARGO|WC|CG|BA|AL|CPP|UMB)-[A-Z0-9\-]{3,30}\b",
        r"\b[A-Z]{2,5}-[A-Z]{2,8}-\d{3,10}-\d{2,4}\b",
        r"\b[A-Z0-9]{2,10}-[A-Z0-9]{2,12}-[A-Z0-9]{2,20}\b",
    ]
    return any(re.fullmatch(p, text) for p in patterns)


def extract_policy_numbers_from_line(value: str) -> list[str]:
    text = clean_text(value).upper()
    candidates = re.findall(r"\b[A-Z]{2,5}-(?:AUTO|GL|CARGO|WC|CG|BA|AL|CPP|UMB)-[A-Z0-9\-]{3,30}\b|\b[A-Z0-9]{2,10}-[A-Z0-9]{2,12}-[A-Z0-9]{2,20}\b", text)
    return [c for c in candidates if looks_like_policy_number(c)]


def extract_claim_number_from_line(value: str) -> str:
    text = clean_text(value).upper()
    patterns = [
        r"\b[A-Z]{2,5}-\d{2}-\d{4,6}\b",       # TRV-26-00091
        r"\b[A-Z]{2,5}-[A-Z]{2,5}-\d{3,6}\b",  # GEI-GL-3101 / PRG-CG-8044 / SA-WC-6009
        r"\b[A-Z]{2,5}-[A-Z]{2,5}-\d{2}-\d{4,6}\b",
        r"(?:CLAIM|CLM)\s*#?\s*[:\-]?\s*([A-Z0-9\-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(1).upper() if match.groups() else match.group(0).upper()
    return ""


def infer_policy_type_from_policy_number(policy_number: str) -> str:
    upper = clean_text(policy_number).upper()
    if "AUTO" in upper or "-AL" in upper or "TRV-" in upper:
        return "Commercial Auto"
    if "-GL" in upper or "GL-" in upper:
        return "General Liability"
    if "CARGO" in upper or "-CG" in upper:
        return "Motor Truck Cargo"
    if "-WC" in upper:
        return "Workers Compensation"
    return "Policy"


def detect_carriers_in_document(text: str) -> list[str]:
    found: list[str] = []
    upper = text.upper()
    for carrier in CARRIER_KEYWORDS:
        if carrier.upper() in upper:
            normalized = normalize_carrier(carrier)
            if normalized and normalized not in found:
                found.append(normalized)
    return found



def detect_agency_name(text: str) -> str:
    for line in lines_from_text(text)[:140]:
        match = re.search(r"(?:Producing Agency|Producer / Agency|Agency Name|Agency|Producer|Broker)\s*[:#\-]\s*(.+?)(?:\s{2,}|\s+Evaluation\s+Date[:#]|\s+Report\s+Run[:#]|$)", line, re.I)
        if match:
            return clean_text(match.group(1))[:160]
    value = find_after_label(text, ["Producing Agency", "Producer / Agency", "Agency", "Agency Name", "Producer", "Broker"], 160)
    return re.split(r"\s{2,}|\s+Evaluation\s+Date[:#]|\s+Report\s+Run[:#]", value, flags=re.I)[0].strip()

def build_profile(text: str) -> dict[str, Any]:
    account_number = detect_account_number(text)
    effective_date, expiration_date = detect_policy_period(text)
    carriers = detect_carriers_in_document(text)
    carrier_name = "Multiple Carriers" if len(carriers) > 1 else (carriers[0] if carriers else "Unknown Carrier")
    return {
        "business_name": detect_business_name(text),
        "carrier_name": carrier_name,
        "writing_carrier": carrier_name,
        "agency_name": detect_agency_name(text),
        "account_number": account_number,
        "customer_number": account_number,
        "producer_number": "",
        "policy_number": account_number or "",
        "effective_date": effective_date,
        "expiration_date": expiration_date,
        "evaluation_date": detect_report_date(text),
    }


def extract_policy_schedule(text: str, profile: dict[str, Any]) -> list[dict[str, Any]]:
    lines = lines_from_text(text)
    policies: list[dict[str, Any]] = []
    seen: set[str] = set()
    policy_types = {p.upper(): p for p in POLICY_TYPE_KEYWORDS}

    def add_policy(policy_type: str, carrier: str, writing_carrier: str, policy_number: str, eff: str, exp: str, claim_count: int = 0, total_incurred: float = 0.0):
        policy_number = clean_text(policy_number).upper()
        if not looks_like_policy_number(policy_number) or policy_number in seen:
            return
        seen.add(policy_number)
        final_type = normalize_policy_type(policy_type or infer_policy_type_from_policy_number(policy_number))
        final_carrier = normalize_carrier(carrier or writing_carrier or profile.get("carrier_name") or "Unknown Carrier")
        policies.append({
            "policy_type": final_type,
            "line_coverage": final_type,
            "line_of_business": final_type,
            "policy_number": policy_number,
            "writing_carrier": clean_text(writing_carrier) or final_carrier,
            "carrier": final_carrier,
            "effective_date": display_date(eff) or display_date(profile.get("effective_date")) or profile.get("effective_date", ""),
            "expiration_date": display_date(exp) or display_date(profile.get("expiration_date")) or profile.get("expiration_date", ""),
            "claim_count": int(claim_count or 0),
            "total_incurred": float(total_incurred or 0),
            "status": "Parsed from policy schedule",
        })

    for i, line in enumerate(lines):
        if line.upper() not in policy_types:
            continue

        # Modern vertical schedule layout:
        # Type, Carrier, Writing Carrier, Policy Number, Eff, Exp, Claims, Total Incurred
        if i + 7 < len(lines) and looks_like_policy_number(lines[i + 3]) and is_date_line(lines[i + 4]) and is_date_line(lines[i + 5]):
            add_policy(
                policy_type=line,
                carrier=lines[i + 1],
                writing_carrier=lines[i + 2],
                policy_number=lines[i + 3],
                eff=lines[i + 4],
                exp=lines[i + 5],
                claim_count=int(lines[i + 6]) if re.fullmatch(r"\d+", lines[i + 6]) else 0,
                total_incurred=money(lines[i + 7]) if is_money_line(lines[i + 7]) else 0,
            )
            continue

        # Older vertical layout:
        # Type, Policy Number, Eff, Exp, Claims, Total Incurred
        if i + 5 < len(lines) and looks_like_policy_number(lines[i + 1]) and is_date_line(lines[i + 2]) and is_date_line(lines[i + 3]):
            add_policy(
                policy_type=line,
                carrier=profile.get("carrier_name", ""),
                writing_carrier=profile.get("writing_carrier", ""),
                policy_number=lines[i + 1],
                eff=lines[i + 2],
                exp=lines[i + 3],
                claim_count=int(lines[i + 4]) if re.fullmatch(r"\d+", lines[i + 4]) else 0,
                total_incurred=money(lines[i + 5]) if is_money_line(lines[i + 5]) else 0,
            )

    # Claim-detail headers can also expose policy numbers.
    for line in lines:
        if "CLAIM DETAIL" in line.upper() and "POLICY" in line.upper():
            found = extract_policy_numbers_from_line(line)
            for policy_number in found:
                carrier = ""
                for c in CARRIER_KEYWORDS:
                    if c.upper() in line.upper():
                        carrier = normalize_carrier(c)
                        break
                add_policy(
                    policy_type=infer_policy_type_from_policy_number(policy_number),
                    carrier=carrier,
                    writing_carrier=carrier,
                    policy_number=policy_number,
                    eff=profile.get("effective_date", ""),
                    exp=profile.get("expiration_date", ""),
                )

    return policies


def extract_claim_rows(text: str, profile: dict[str, Any], policies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lines = lines_from_text(text)
    claims: list[dict[str, Any]] = []
    seen: set[str] = set()
    policy_map = {clean_text(p.get("policy_number")).upper(): p for p in policies if p.get("policy_number")}

    current_policy = ""
    current_policy_type = ""
    current_carrier = ""

    def add_claim(claim_number: str, policy_number: str, loss_date: str, status: str, line_type: str, description: str, paid: float, reserve: float, incurred: float, litigation: bool, flagged: bool):
        claim_number = clean_text(claim_number).upper()
        policy_number = clean_text(policy_number).upper()
        if not claim_number or claim_number in seen or not looks_like_policy_number(policy_number):
            return
        seen.add(claim_number)
        final_line = normalize_policy_type(line_type or policy_map.get(policy_number, {}).get("policy_type") or infer_policy_type_from_policy_number(policy_number))
        final_incurred = float(incurred or paid + reserve or 0)
        flag_parts = []
        if flagged:
            flag_parts.append("Watch / flagged claim")
        if final_incurred >= 100000:
            flag_parts.append("High severity claim")
        if litigation:
            flag_parts.append("Litigation exposure")
        claims.append({
            **profile,
            "claim_number": claim_number,
            "policy_number": policy_number,
            "line_of_business": final_line,
            "claim_type": final_line,
            "cause_of_loss": "Needs Review",
            "claimant_type": "Needs Review",
            "date_of_loss": normalize_date(loss_date),
            "date_reported": "",
            "date_closed": "",
            "status": clean_text(status).title(),
            "description": description or "Parsed from loss run.",
            "paid_amount": float(paid or 0),
            "reserve_amount": float(reserve or 0),
            "total_incurred": final_incurred,
            "net_incurred": final_incurred,
            "litigation": bool(litigation),
            "litigation_status": "Litigation detected" if litigation else "None",
            "attorney_assigned": bool(litigation),
            "suit_filed": bool(litigation),
            "venue_state": "Needs Review",
            "injury_type": "Needs Review",
            "flag": " | ".join(flag_parts),
            "carrier_name": normalize_carrier(current_carrier or policy_map.get(policy_number, {}).get("carrier") or profile.get("carrier_name", "")),
        })

    i = 0
    while i < len(lines):
        line = lines[i]
        upper = line.upper()

        if "CLAIM DETAIL" in upper and "POLICY" in upper:
            found = extract_policy_numbers_from_line(line)
            if found:
                current_policy = found[0]
                current_policy_type = policy_map.get(current_policy, {}).get("policy_type") or infer_policy_type_from_policy_number(current_policy)
            current_carrier = ""
            for carrier in CARRIER_KEYWORDS:
                if carrier.upper() in upper:
                    current_carrier = normalize_carrier(carrier)
                    break
            i += 1
            continue

        claim_number = extract_claim_number_from_line(line)
        if claim_number and current_policy:
            # Expected vertical claim row:
            # Claim, Loss Date, Status, LOB, Description, Paid, Reserve, Incurred, Lit?, Flag
            if i + 8 < len(lines) and is_date_line(lines[i + 1]) and lines[i + 2].upper() in {"OPEN", "CLOSED", "REOPENED", "PENDING", "ACTIVE"}:
                loss_date = lines[i + 1]
                status = lines[i + 2]
                line_type = lines[i + 3]
                description = lines[i + 4]
                paid = money(lines[i + 5]) if is_money_line(lines[i + 5]) else 0
                reserve = money(lines[i + 6]) if is_money_line(lines[i + 6]) else 0
                incurred = money(lines[i + 7]) if is_money_line(lines[i + 7]) else paid + reserve
                litigation = lines[i + 8].upper() in {"Y", "YES", "TRUE", "LIT", "LITIGATION"}
                flagged = False
                if i + 9 < len(lines):
                    flagged = lines[i + 9].upper() in {"Y", "YES", "TRUE", "FLAG", "FLAGGED"}
                add_claim(claim_number, current_policy, loss_date, status, line_type, description, paid, reserve, incurred, litigation, flagged)
                i += 10
                continue

        i += 1

    return claims


def update_policy_claim_totals(policies: list[dict[str, Any]], claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_policy = {clean_text(p.get("policy_number")).upper(): p for p in policies if p.get("policy_number")}
    for claim in claims:
        policy_number = clean_text(claim.get("policy_number")).upper()
        if not policy_number:
            continue
        if policy_number not in by_policy:
            final_type = normalize_policy_type(claim.get("line_of_business") or infer_policy_type_from_policy_number(policy_number))
            by_policy[policy_number] = {
                "policy_type": final_type,
                "line_coverage": final_type,
                "line_of_business": final_type,
                "policy_number": policy_number,
                "writing_carrier": claim.get("carrier_name") or "Unknown Carrier",
                "carrier": claim.get("carrier_name") or "Unknown Carrier",
                "effective_date": profile_date(claim.get("effective_date")),
                "expiration_date": profile_date(claim.get("expiration_date")),
                "claim_count": 0,
                "total_incurred": 0.0,
                "status": "Parsed from claims",
            }
    for policy_number, policy in by_policy.items():
        matching = [c for c in claims if clean_text(c.get("policy_number")).upper() == policy_number]
        if matching:
            policy["claim_count"] = len(matching)
            policy["total_incurred"] = round(sum(float(c.get("total_incurred") or 0) for c in matching), 2)
            policy["status"] = "Claims Reported"
        else:
            policy["claim_count"] = int(policy.get("claim_count") or 0)
            policy["total_incurred"] = float(policy.get("total_incurred") or 0)
            policy["status"] = policy.get("status") or "Nothing to Report"
    return list(by_policy.values())


def profile_date(value: Any) -> str:
    return display_date(value) or clean_text(value)


def extract_document_totals(text: str) -> dict[str, Any]:
    lines = lines_from_text(text)
    totals = {
        "total_claims": None,
        "open_claims": None,
        "closed_claims": None,
        "litigation_claims": None,
        "flagged_claims": None,
        "total_paid": None,
        "total_reserve": None,
        "total_incurred": None,
    }
    for i, line in enumerate(lines):
        upper = line.upper()
        if upper == "TOTAL CLAIMS" and i + 1 < len(lines) and re.fullmatch(r"\d+", lines[i + 1]):
            totals["total_claims"] = int(lines[i + 1])
        if upper == "OPEN CLAIMS" and i + 1 < len(lines) and re.fullmatch(r"\d+", lines[i + 1]):
            totals["open_claims"] = int(lines[i + 1])
        if upper in {"LITIGATED CLAIMS", "LITIGATION CLAIMS"} and i + 1 < len(lines) and re.fullmatch(r"\d+", lines[i + 1]):
            totals["litigation_claims"] = int(lines[i + 1])
        if upper.startswith("FLAGGED") and i + 1 < len(lines) and re.fullmatch(r"\d+", lines[i + 1]):
            totals["flagged_claims"] = int(lines[i + 1])
        if upper == "TOTAL PAID" and i + 1 < len(lines) and is_money_line(lines[i + 1]):
            totals["total_paid"] = money(lines[i + 1])
        if upper in {"TOTAL RESERVE", "CASE RESERVE"} and i + 1 < len(lines) and is_money_line(lines[i + 1]):
            totals["total_reserve"] = money(lines[i + 1])
        if upper == "TOTAL INCURRED" and i + 1 < len(lines) and is_money_line(lines[i + 1]):
            totals["total_incurred"] = money(lines[i + 1])
    return totals


def build_validation(claims: list[dict[str, Any]], policies: list[dict[str, Any]], document_totals: dict[str, Any]) -> dict[str, Any]:
    parsed_claim_count = len(claims)
    parsed_open_claims = len([c for c in claims if clean_text(c.get("status")).lower() in {"open", "reopened", "pending", "active"}])
    parsed_closed_claims = len([c for c in claims if clean_text(c.get("status")).lower() == "closed"])
    parsed_litigation_claims = len([c for c in claims if c.get("litigation")])
    parsed_flagged_claims = len([c for c in claims if clean_text(c.get("flag"))])
    parsed_total_paid = round(sum(float(c.get("paid_amount") or 0) for c in claims), 2)
    parsed_total_reserve = round(sum(float(c.get("reserve_amount") or 0) for c in claims), 2)
    parsed_total_incurred = round(sum(float(c.get("total_incurred") or 0) for c in claims), 2)
    issues: list[str] = []
    if document_totals.get("total_claims") is not None and int(document_totals["total_claims"]) != parsed_claim_count:
        issues.append(f"Claim count mismatch: document says {document_totals['total_claims']}, parser found {parsed_claim_count}")
    if document_totals.get("total_incurred") is not None:
        diff = abs(float(document_totals["total_incurred"]) - parsed_total_incurred)
        if diff > 1:
            issues.append(f"Total incurred mismatch: document says {document_totals['total_incurred']}, parser found {parsed_total_incurred}")
    if parsed_claim_count == 0:
        issues.append("No claim rows were parsed.")
    if not policies:
        issues.append("No policy schedule rows were parsed.")
    status = "Passed" if not issues and parsed_claim_count > 0 and policies else "Needs Review"
    if parsed_claim_count == 0 or not policies:
        status = "Failed"
    return {
        "status": status,
        "issues": issues,
        "parsed_claim_count": parsed_claim_count,
        "parsed_open_claims": parsed_open_claims,
        "parsed_closed_claims": parsed_closed_claims,
        "parsed_litigation_claims": parsed_litigation_claims,
        "parsed_flagged_claims": parsed_flagged_claims,
        "parsed_total_paid": parsed_total_paid,
        "parsed_total_reserve": parsed_total_reserve,
        "parsed_total_incurred": parsed_total_incurred,
        "document_total_claims": document_totals.get("total_claims"),
        "document_open_claims": document_totals.get("open_claims"),
        "document_litigation_claims": document_totals.get("litigation_claims"),
        "document_flagged_claims": document_totals.get("flagged_claims"),
        "document_total_paid": document_totals.get("total_paid"),
        "document_total_reserve": document_totals.get("total_reserve"),
        "document_total_incurred": document_totals.get("total_incurred"),
        "policy_count": len(policies),
    }


def parse_loss_run_file(file_path: str, filename: str):
    lower_name = str(filename or "").lower()
    if lower_name.endswith(".pdf"):
        text = extract_pdf_text_all_pages(file_path)
    else:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as file:
                text = file.read()
        except Exception:
            text = ""
    profile = build_profile(text)
    policies = extract_policy_schedule(text, profile)
    claims = extract_claim_rows(text, profile, policies)
    policies = update_policy_claim_totals(policies, claims)
    document_totals = extract_document_totals(text)
    validation = build_validation(claims, policies, document_totals)
    profile["policies"] = policies
    profile["validation"] = validation
    profile["raw_text_preview"] = text[:5000]
    return {
        "profile": profile,
        "policies": policies,
        "claims": claims,
        "parsed_claims": claims,
        "validation": validation,
        "document_totals": document_totals,
        "raw_text_preview": text[:5000],
        "claim_count": len(claims),
        "policy_count": len(policies),
        "total_incurred": validation.get("parsed_total_incurred", 0),
    }