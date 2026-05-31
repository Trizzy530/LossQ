from pypdf import PdfReader
import re


def extract_text_from_pdf(file_path):
    reader = PdfReader(file_path)
    text = ""

    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"

    return text


def money_to_float(value):
    if not value:
        return 0.0

    cleaned = (
        str(value)
        .replace("$", "")
        .replace(",", "")
        .replace("(", "-")
        .replace(")", "")
        .strip()
    )

    try:
        return float(cleaned)
    except Exception:
        return 0.0


def find_money(labels, block):
    for label in labels:
        match = re.search(
            rf"{label}\s*[:\-]?\s*\$?\s*([\d,]+(?:\.\d+)?)",
            block,
            re.IGNORECASE,
        )
        if match:
            return money_to_float(match.group(1))
    return 0.0


def find_text(labels, text):
    for label in labels:
        match = re.search(
            rf"{label}\s*[:\-]?\s*([^\n\r]+)",
            text,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()
    return ""


def find_date(labels, text):
    for label in labels:
        match = re.search(
            rf"{label}\s*[:\-]?\s*(\d{{1,2}}[\/\-]\d{{1,2}}[\/\-]\d{{2,4}}|\d{{4}}-\d{{1,2}}-\d{{1,2}})",
            text,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()
    return ""


def extract_profile_from_text(text):
    return {
        "business_name": find_text(
            ["Named Insured", "Insured Name", "Business Name", "Account Name"],
            text,
        ),
        "carrier_name": find_text(
            ["Carrier", "Carrier Name", "Insurance Carrier"],
            text,
        ),
        "agency_name": find_text(
            ["Agency", "Agency Name", "Broker", "Broker Name"],
            text,
        ),
        "policy_number": find_text(
            ["Policy Number", "Policy No", "Policy #", "Policy"],
            text,
        ),
        "effective_date": find_date(
            ["Effective Date", "Policy Effective Date", "Eff Date"],
            text,
        ),
        "expiration_date": find_date(
            ["Expiration Date", "Policy Expiration Date", "Exp Date"],
            text,
        ),
    }


def detect_line(block):
    lower = block.lower()

    if "general liability" in lower or "slip" in lower or "premises" in lower:
        return "General Liability"

    if "commercial auto" in lower or "auto" in lower or "vehicle" in lower or "collision" in lower:
        return "Commercial Auto"

    if "workers" in lower or "employee injury" in lower:
        return "Workers Compensation"

    if "cargo" in lower or "freight" in lower:
        return "Cargo"

    if "property" in lower or "water damage" in lower or "fire" in lower:
        return "Property"

    return "Unknown"


def parse_claims_from_text(text):
    claims = []

    profile = extract_profile_from_text(text)

    claim_pattern = r"(GL-\d+|AUTO-\d+|WC-\d+|PROP-\d+|CLM-\d+|\b\d{5,12}\b)"
    matches = list(re.finditer(claim_pattern, text, re.IGNORECASE))

    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[start:end]

        if len(block.strip()) < 20:
            continue

        paid = find_money(["Paid", "Amount Paid", "Loss Paid"], block)
        reserve = find_money(["Reserve", "Outstanding Reserve", "Loss Reserve"], block)
        total = find_money(["Total Incurred", "Incurred", "Total Loss"], block)

        if total == 0:
            total = paid + reserve

        lower = block.lower()

        litigation = any(
            word in lower
            for word in ["litigation", "attorney", "lawsuit", "counsel", "suit filed"]
        )

        status_match = re.search(r"\b(Open|Closed|Pending|Denied|Settled)\b", block, re.I)
        status = status_match.group(1).title() if status_match else "Needs Review"

        line = detect_line(block)

        flag = None
        if total >= 100000:
            flag = "High severity claim"
        if litigation:
            flag = "Litigation exposure" if not flag else flag + " | Litigation exposure"

        claims.append({
            **profile,
            "claim_number": match.group(1).upper(),
            "policy_id": 1,
            "line_of_business": line,
            "claim_type": line,
            "cause_of_loss": "Needs Review",
            "claimant_type": "Needs Review",
            "date_of_loss": find_date(["Date of Loss", "Loss Date", "DOL"], block) or "Needs Review",
            "date_reported": find_date(["Date Reported", "Reported Date", "Report Date"], block),
            "date_closed": find_date(["Date Closed", "Closed Date", "Closure Date"], block),
            "status": status,
            "description": block[:750],
            "paid_amount": paid,
            "reserve_amount": reserve,
            "total_incurred": total,
            "litigation": litigation,
            "litigation_status": "Litigation detected" if litigation else "None",
            "attorney_assigned": litigation,
            "suit_filed": litigation,
            "venue_state": "Needs Review",
            "injury_type": "Needs Review",
            "flag": flag,
        })

    return claims