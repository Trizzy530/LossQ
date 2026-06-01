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
    return normalize_whitespace(text)


def normalize_whitespace(value):
    if not value:
        return ""
    value = str(value).replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def clean_text(value):
    if not value:
        return ""
    cleaned = str(value).replace("\n", " ").replace("\r", " ").strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" :-|")
    if cleaned.lower() in ["none", "nan", "needs review", "not set", "unknown"]:
        return ""
    return cleaned


def money_to_float(value):
    if not value:
        return 0.0
    cleaned = str(value).replace("$", "").replace(",", "").replace("(", "-").replace(")", "").strip()
    try:
        return float(cleaned)
    except Exception:
        return 0.0


def money_values(text):
    return [money_to_float(x) for x in re.findall(r"\$?\(?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\)?", text)]


def find_money(labels, block):
    for label in labels:
        match = re.search(
            rf"{re.escape(label)}\s*[:\-]?\s*\$?\s*([\d,]+(?:\.\d+)?)",
            block,
            re.IGNORECASE,
        )
        if match:
            return money_to_float(match.group(1))
    return 0.0


def find_text_after_label(labels, text, max_chars=90):
    for label in labels:
        patterns = [
            rf"{re.escape(label)}\s*[:\-]\s*([^\n\r]{{1,{max_chars}}})",
            rf"{re.escape(label)}\s+([A-Za-z0-9 ,.&/#'\-]{{1,{max_chars}}})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = clean_text(match.group(1))
                for stop in [
                    "Policy Number", "Policy No", "Policy Period", "Effective",
                    "Expiration", "Carrier", "Agency", "Producer", "Claim Number",
                    "Loss Date", "Valuation Date", "Claimant", "Status",
                ]:
                    value = re.split(stop, value, flags=re.IGNORECASE)[0].strip()
                return clean_text(value)
    return ""


def find_date_after_label(labels, text):
    date_pattern = r"(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2})"
    for label in labels:
        match = re.search(rf"{re.escape(label)}\s*[:\-]?\s*{date_pattern}", text, re.IGNORECASE)
        if match:
            return clean_text(match.group(1))
    return ""


def find_any_date(text):
    match = re.search(r"(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2})", text)
    return clean_text(match.group(1)) if match else ""


def find_policy_period(text):
    date = r"(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2})"
    patterns = [
        rf"Policy\s*Period\s*[:\-]?\s*{date}\s*(?:to|through|thru|\-|\u2013|\u2014)\s*{date}",
        rf"Effective\s*[:\-]?\s*{date}\s*(?:to|through|thru|\-|\u2013|\u2014)\s*{date}",
        rf"Coverage\s*Period\s*[:\-]?\s*{date}\s*(?:to|through|thru|\-|\u2013|\u2014)\s*{date}",
        rf"Policy\s*Term\s*[:\-]?\s*{date}\s*(?:to|through|thru|\-|\u2013|\u2014)\s*{date}",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return clean_text(match.group(1)), clean_text(match.group(2))
    return "", ""


def guess_carrier_from_text(text):
    known = [
    ("National General", [
        "national general"
    ]),

    ("Berkley Mid-Atlantic Group", [
        "berkley mid-atlantic",
        "berkley mid atlantic",
        "mid-atlantic group"
    ]),

    ("Evanston Insurance Company", [
        "evanston insurance",
        "evanston"
    ]),

    ("Continental Western Insurance Company", [
        "continental western"
    ]),

    ("Firemen's Insurance Company", [
        "firemen"
    ]),

    ("Travelers", ["travelers"]),
    ("Liberty Mutual", ["liberty mutual"]),
    ("Nationwide", ["nationwide"]),
    ("The Hartford", ["hartford"]),
    ("CNA", ["cna insurance", " cna "]),
    ("Hanover", ["hanover"]),
    ("Auto-Owners", ["auto owners", "auto-owners"]),
    ("Progressive Commercial", ["progressive"]),
    ("Zurich", ["zurich"]),
    ("Chubb", ["chubb"]),
    ("AIG", [" aig "]),
]
    lower = f" {text.lower()} "
    for name, terms in known:
        if any(term in lower for term in terms):
            return name
    return ""


def extract_profile_from_text(text):
    text = normalize_whitespace(text)
    effective, expiration = find_policy_period(text)

    carrier = (
    guess_carrier_from_text(text)
    or find_text_after_label(
        [
            "Carrier Name",
            "Insurance Carrier",
            "Insurance Company",
            "Company Name",
            "Carrier",
            "Insurer",
            "Writing Company",
        ],
        text,
    )
)
        "policy_number": find_text_after_label(
            ["Policy Number", "Policy No.", "Policy No", "Policy #", "Policy ID"],
            text,
            max_chars=60,
        ),
        "effective_date": effective or find_date_after_label(["Effective Date", "Policy Effective Date", "Eff Date", "Effective"], text),
        "expiration_date": expiration or find_date_after_label(["Expiration Date", "Policy Expiration Date", "Exp Date", "Expiration"], text),
        "evaluation_date": find_date_after_label(["Evaluation Date", "Valuation Date", "Loss Run Date", "Loss Runs as of", "As Of", "Run Date", "Report Date"], text),
    }


def detect_line(block):
    lower = block.lower()
    if "general liability" in lower or "slip" in lower or "premises" in lower:
        return "General Liability"
    if "commercial auto" in lower or "auto" in lower or "vehicle" in lower or "collision" in lower:
        return "Commercial Auto"
    if "workers" in lower or "employee injury" in lower or "compensation" in lower:
        return "Workers Compensation"
    if "cargo" in lower or "freight" in lower:
        return "Cargo"
    if "property" in lower or "water damage" in lower or "fire" in lower:
        return "Property"
    return "Unknown"


def claim_number_candidates(text):
    pattern = (
        r"\b("
        r"\d{1,3}\s?[A-Z]{1,4}\s?\d{6,15}"
        r"|GL[-\s]?\d+"
        r"|AUTO[-\s]?\d+"
        r"|WC[-\s]?\d+"
        r"|PROP[-\s]?\d+"
        r"|CLM[-\s]?\d+"
        r"|[A-Z]{2,5}[-\s]?\d{5,15}"
        r"|\d{6,15}"
        r")\b"
    )
    return list(re.finditer(pattern, text, re.IGNORECASE))


def build_claim(profile, claim_number, block):
    paid = find_money(["Paid Loss Gross of Recovery", "Paid Loss", "Amount Paid", "Loss Paid", "Total Paid", "Paid"], block)
    reserve = find_money(["Case Loss & Expense Reserve", "Outstanding Reserve", "Loss Reserve", "Total Reserve", "Reserve"], block)
    total = find_money(["Gross Incurred", "Net Incurred", "Total Incurred", "Incurred", "Total Loss"], block)

    values = money_values(block)
    if total == 0 and len(values) >= 3:
        paid = paid or values[-3]
        reserve = reserve or values[-2]
        total = values[-1]
    elif total == 0:
        total = paid + reserve

    lower = block.lower()
    litigation = any(word in lower for word in ["litigation", "attorney", "lawsuit", "counsel", "suit filed", "legal"])
    status_match = re.search(r"\b(Open|Closed|Pending|Denied|Settled|Reopened)\b", block, re.I)

    flag = None
    if total >= 100000:
        flag = "High severity claim"
    if litigation:
        flag = "Litigation exposure" if not flag else flag + " | Litigation exposure"

    return {
        **profile,
        "claim_number": clean_text(claim_number).upper(),
        "policy_id": 1,
        "line_of_business": detect_line(block),
        "claim_type": detect_line(block),
        "cause_of_loss": find_text_after_label(["Cause of Loss", "Loss Cause", "Cause"], block, 80) or "Needs Review",
        "claimant_type": find_text_after_label(["Claimant Type", "Claimant"], block, 80) or "Needs Review",
        "date_of_loss": find_date_after_label(["Loss Date", "Date of Loss", "DOL", "Claim Date", "Accident Date"], block) or find_any_date(block) or "Needs Review",
        "date_reported": find_date_after_label(["Date Reported", "Reported Date", "Report Date"], block),
        "date_closed": find_date_after_label(["Date Closed", "Closed Date", "Closure Date"], block),
        "status": status_match.group(1).title() if status_match else "Needs Review",
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
    }


def parse_claims_from_text(text):
    text = normalize_whitespace(text)
    profile = extract_profile_from_text(text)
    claims = []
    seen = set()

    matches = claim_number_candidates(text)

    for index, match in enumerate(matches):
        claim_number = clean_text(match.group(1)).upper()
        start = max(match.start() - 150, 0)
        end = matches[index + 1].start() if index + 1 < len(matches) else min(match.end() + 1200, len(text))
        block = text[start:end]

        has_claim_context = any(word in block.lower() for word in ["claim", "loss", "paid", "reserve", "incurred", "open", "closed"])
        has_money = bool(money_values(block))

        if not has_claim_context and not has_money:
            continue

        if claim_number in seen:
            continue

        claim = build_claim(profile, claim_number, block)

        if claim["total_incurred"] == 0 and claim["paid_amount"] == 0 and claim["reserve_amount"] == 0:
            continue

        claims.append(claim)
        seen.add(claim_number)

    return claims