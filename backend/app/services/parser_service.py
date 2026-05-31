from pypdf import PdfReader
import re


def extract_text_from_pdf(file_path):
    text = ""

    try:
        reader = PdfReader(file_path)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    except Exception:
        pass

    return text


def clean_text(value):
    if not value:
        return ""

    cleaned = str(value).replace("\n", " ").replace("\r", " ").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)

    bad_values = ["none", "nan", "needs review", "not set"]
    if cleaned.lower() in bad_values:
        return ""

    return cleaned


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


def find_text_after_label(labels, text):
    for label in labels:
        match = re.search(
            rf"{label}\s*[:\-]?\s*([A-Za-z0-9 ,.&/#\-]+)",
            text,
            re.IGNORECASE,
        )
        if match:
            return clean_text(match.group(1))
    return ""


def find_date_after_label(labels, text):
    for label in labels:
        match = re.search(
            rf"{label}\s*[:\-]?\s*(\d{{1,2}}[\/\-]\d{{1,2}}[\/\-]\d{{2,4}}|\d{{4}}-\d{{1,2}}-\d{{1,2}})",
            text,
            re.IGNORECASE,
        )
        if match:
            return clean_text(match.group(1))
    return ""


def extract_profile_from_text(text):
    profile = {
        "business_name": "",
        "carrier_name": "",
        "agency_name": "",
        "policy_number": "",
        "effective_date": "",
        "expiration_date": "",
        "evaluation_date": "",
    }

    profile["business_name"] = find_text_after_label(
        [
            "Named Insured",
            "Insured Name",
            "Insured",
            "Business Name",
            "Account Name",
            "Policyholder",
        ],
        text,
    )

    profile["agency_name"] = find_text_after_label(
        [
            "Agency Name",
            "Agency",
            "Broker Name",
            "Broker",
            "Producer",
        ],
        text,
    )

    profile["policy_number"] = find_text_after_label(
        [
            "Policy Number",
            "Policy No",
            "Policy #",
            "Policy",
        ],
        text,
    )

    profile["evaluation_date"] = find_date_after_label(
        [
            "Evaluation Date",
            "Valuation Date",
            "Loss Run Date",
            "As Of",
        ],
        text,
    )

    effective_range = re.search(
        r"Effective\s*[:\-]?\s*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})\s*[-–]\s*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})",
        text,
        re.IGNORECASE,
    )

    if effective_range:
        profile["effective_date"] = clean_text(effective_range.group(1))
        profile["expiration_date"] = clean_text(effective_range.group(2))
    else:
        profile["effective_date"] = find_date_after_label(
            ["Effective Date", "Policy Effective Date", "Eff Date", "Effective"],
            text,
        )
        profile["expiration_date"] = find_date_after_label(
            ["Expiration Date", "Policy Expiration Date", "Exp Date", "Expiration"],
            text,
        )

    carrier = find_text_after_label(
        [
            "Carrier Name",
            "Insurance Carrier",
            "Carrier",
            "Insurance Company",
        ],
        text,
    )

    if not carrier:
        if "Berkley" in text or "Mid-Atlantic" in text:
            carrier = "Berkley Mid-Atlantic Group"
        elif "Continental Western" in text:
            carrier = "Continental Western Insurance Company"
        elif "Firemen" in text:
            carrier = "Firemen's Insurance Company"

    profile["carrier_name"] = carrier

    return profile


def detect_line(block):
    lower = block.lower()

    if "general liability" in lower or "slip" in lower or "premises" in lower:
        return "General Liability"

    if "commercial auto" in lower or "auto" in lower or "vehicle" in lower:
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

    claim_pattern = (
        r"(?:Claim Number\s*)?"
        r"("
        r"\d{1,3}\s?[A-Z]{1,4}\s?\d{6,15}"
        r"|GL-\d+"
        r"|AUTO-\d+"
        r"|WC-\d+"
        r"|PROP-\d+"
        r"|CLM-\d+"
        r"|\b\d{5,15}\b"
        r")"
    )

    matches = list(re.finditer(claim_pattern, text, re.IGNORECASE))

    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[start:end]

        if len(block.strip()) < 20:
            continue

        paid = find_money(
            [
                "Paid Loss Gross of Recovery",
                "Paid Loss",
                "Amount Paid",
                "Loss Paid",
                "Paid",
            ],
            block,
        )

        reserve = find_money(
            [
                "Case Loss & Expense Reserve",
                "Outstanding Reserve",
                "Loss Reserve",
                "Reserve",
            ],
            block,
        )

        total = find_money(
            [
                "Gross Incurred",
                "Net Incurred",
                "Total Incurred",
                "Incurred",
                "Total Loss",
            ],
            block,
        )

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

        date_of_loss = find_date_after_label(
            ["Loss Date", "Date of Loss", "DOL", "Claim Date"],
            block,
        )

        date_reported = find_date_after_label(
            ["Date Reported", "Reported Date", "Report Date"],
            block,
        )

        flag = None
        if total >= 100000:
            flag = "High severity claim"
        if litigation:
            flag = "Litigation exposure" if not flag else flag + " | Litigation exposure"

        claim_number = clean_text(match.group(1)).upper()

        claims.append({
            **profile,
            "claim_number": claim_number,
            "policy_id": 1,
            "line_of_business": line,
            "claim_type": line,
            "cause_of_loss": "Needs Review",
            "claimant_type": "Needs Review",
            "date_of_loss": date_of_loss or "Needs Review",
            "date_reported": date_reported,
            "date_closed": "",
            "status": status,
            "description": clean_text(block[:1000]),
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