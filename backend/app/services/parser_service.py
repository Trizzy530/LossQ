from pypdf import PdfReader
import re


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


def money_values(text):
    return [
        money_to_float(x)
        for x in re.findall(
            r"\$\s*\(?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\)?",
            text or ""
        )
    ]

def find_money(labels, block):
    for label in labels:
        match = re.search(
            rf"{re.escape(label)}\s*[:\-]?\s*\$?\s*([\d,]+(?:\.\d+)?)",
            block or "",
            re.IGNORECASE,
        )
        if match:
            return money_to_float(match.group(1))
    return 0.0


def find_text_after_label(labels, text, max_chars=120):
    text = text or ""

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
                    "Policy Number",
                    "Policy No",
                    "Policy Period",
                    "Effective",
                    "Expiration",
                    "Carrier",
                    "Agency",
                    "Producer",
                    "Claim Number",
                    "Loss Date",
                    "Valuation Date",
                    "Evaluation Date",
                    "Claimant",
                    "Status",
                    "Line Of Business",
                    "Line of Business",
                ]:
                    value = re.split(stop, value, flags=re.IGNORECASE)[0].strip()

                return clean_text(value)

    return ""


def find_date_after_label(labels, text):
    text = text or ""
    date_pattern = r"(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2})"

    for label in labels:
        match = re.search(
            rf"{re.escape(label)}\s*[:\-]?\s*{date_pattern}",
            text,
            re.IGNORECASE,
        )
        if match:
            return clean_text(match.group(1))

    return ""


def find_any_date(text):
    match = re.search(
        r"(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2})",
        text or "",
    )
    return clean_text(match.group(1)) if match else ""


def find_policy_period(text):
    text = text or ""
    date = r"(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2})"

    patterns = [
        rf"Policy\s*Period\s*[:\-]?\s*{date}\s*(?:to|through|thru|\-|\u2013|\u2014)\s*{date}",
        rf"Effective\s*[:\-]?\s*{date}\s*(?:to|through|thru|\-|\u2013|\u2014)\s*{date}",
        rf"Coverage\s*Period\s*[:\-]?\s*{date}\s*(?:to|through|thru|\-|\u2013|\u2014)\s*{date}",
        rf"Policy\s*Term\s*[:\-]?\s*{date}\s*(?:to|through|thru|\-|\u2013|\u2014)\s*{date}",
        rf"{date}\s*(?:to|through|thru|\-|\u2013|\u2014)\s*{date}",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return clean_text(match.group(1)), clean_text(match.group(2))

    return "", ""


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


def guess_carrier_from_text(text):
    known = [
        ("National General", ["national general"]),
        ("Berkley Mid-Atlantic Group", [
            "berkley mid-atlantic",
            "berkley mid atlantic",
            "mid-atlantic group",
        ]),
        ("Evanston Insurance Company", ["evanston insurance", "evanston"]),
        ("Continental Western Insurance Company", ["continental western"]),
        ("Firemen's Insurance Company", ["firemen"]),
        ("Acadia Insurance Company", ["acadia insurance"]),
        ("Tri-State Insurance Company of Minnesota", ["tri-state insurance"]),
        ("Union Insurance Company", ["union insurance company"]),
        ("Union Standard Lloyds", ["union standard lloyds"]),
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

    lower = f" {str(text or '').lower()} "

    for name, terms in known:
        if any(term in lower for term in terms):
            return name

    return ""

def reject_fake_carrier(value):
    text = clean_text(value or "")
    upper = text.upper()

    fake_terms = [
        "LOSS RUN",
        "EXPERIENCE DETAIL",
        "INTERNAL COPY",
        "CLAIM DETAIL",
        "LOSS EXPERIENCE",
        "SUMMARY LOSS RUN",
        "REPORT DATE",
        "RUN DATE",
        "PAGE ",
        "POLICY DETAIL",
    ]

    if not text:
        return ""

    if any(term in upper for term in fake_terms):
        return ""

    return text


def detect_real_carrier(text):
    text = text or ""

    known_carriers = [
        "Vanliner Insurance Company",
        "biBERK Insurance Services",
        "GEICO",
        "Progressive",
        "Travelers",
        "The Hartford",
        "Hartford",
        "Nationwide",
        "Liberty Mutual",
        "State Farm",
        "Zurich",
        "Chubb",
        "CNA",
        "Berkshire Hathaway",
    ]

    for carrier in known_carriers:
        if carrier.lower() in text.lower():
            return carrier

    label_value = find_text_after_label(
        [
            "Writing Carrier",
            "Carrier",
            "Insurance Company",
            "Insurer",
            "Company",
        ],
        text,
        max_chars=90,
    )

    return reject_fake_carrier(label_value)


def find_account_number(text):
    account = find_text_after_label(
        [
            "Account Number",
            "Account No.",
            "Account No",
            "Account #",
            "Customer Number",
            "Customer No.",
            "Client Number",
            "Insured Account",
        ],
        text,
        max_chars=80,
    )

    account = clean_text(account or "")

    if not account:
        match = re.search(
            r"\b(?:ACCT|ACCOUNT|CUST|CLIENT)[-\s#:]*([A-Z0-9][A-Z0-9\-]{4,30})\b",
            text or "",
            re.IGNORECASE,
        )
        if match:
            account = clean_text(match.group(1))

    return account


def find_policy_period_dates(text):
    text = text or ""

    period_patterns = [
        r"(?:Policy\s*Period|Policy\s*Term|Coverage\s*Period)\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s*(?:to|through|thru|\-)\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"(?:Effective|Eff\.?\s*Date)\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}).{0,40}(?:Expiration|Exp\.?\s*Date)\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
    ]

    for pattern in period_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return clean_text(match.group(1)), clean_text(match.group(2))

    return "", ""


def extract_policy_rows(text):
    rows = []
    seen = set()

    patterns = [
        r"\b(?P<line>Commercial\s*Auto|Auto|AL|General\s*Liability|GL|Motor\s*Truck\s*Cargo|Cargo|Workers\s*Compensation|WC)\b.{0,80}?\b(?P<policy>[A-Z]{1,8}[-\s]?[A-Z0-9]{2,12}[-\s]?[A-Z0-9]{2,12})\b",
        r"\b(?P<policy>VL[-\s]?(?:AL|CA|AUTO|GL|CARGO|MTC|WC)[-\s]?\d{3,10})\b.{0,80}?\b(?P<line>Commercial\s*Auto|Auto|AL|General\s*Liability|GL|Motor\s*Truck\s*Cargo|Cargo|Workers\s*Compensation|WC)\b",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, text or "", re.IGNORECASE):
            policy = clean_text(match.group("policy")).replace(" ", "-").upper()
            line = normalize_line_name(match.group("line"))

            key = (policy, line)
            if key in seen:
                continue

            seen.add(key)
            rows.append(
                {
                    "policy_number": policy,
                    "line_of_business": line,
                }
            )

    return rows


def normalize_line_name(value):
    text = str(value or "").strip().lower()

    if text in ["al", "auto", "commercial auto"] or "auto" in text:
        return "Commercial Auto"

    if text == "gl" or "general liability" in text:
        return "General Liability"

    if text in ["cargo", "mtc"] or "motor truck cargo" in text:
        return "Motor Truck Cargo"

    if text == "wc" or "workers compensation" in text or "workers comp" in text:
        return "Workers Compensation"

    return clean_text(value or "Unknown")


def money_to_float(value):
    if value is None:
        return 0.0

    text = str(value).replace("$", "").replace(",", "").replace("(", "-").replace(")", "")
    text = re.sub(r"[^0-9.\-]", "", text)

    try:
        return float(text or 0)
    except Exception:
        return 0.0


def parse_messy_claim_rows(text, profile):
    claims = []
    seen = set()

    claim_pattern = re.compile(
        r"\b(?P<claim>VL[-\s]?(?:AL|CA|AUTO|GL|CARGO|MTC|WC)[-\s]?\d{3,10}|[A-Z]{2,8}[-\s]?\d{4,12})\b",
        re.IGNORECASE,
    )

    matches = list(claim_pattern.finditer(text or ""))

    for index, match in enumerate(matches):
        claim_number = clean_text(match.group("claim")).replace(" ", "-").upper()

        if claim_number in seen:
            continue

        start = max(match.start() - 120, 0)
        end = matches[index + 1].start() if index + 1 < len(matches) else min(match.end() + 900, len(text))
        block = text[start:end]

        lower_block = block.lower()

        if not any(word in lower_block for word in ["paid", "reserve", "incurred", "closed", "open", "claim", "litigation", "$"]):
            continue

        money_matches = re.findall(r"\$?\(?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\)?", block)

        money_values_clean = [
            money_to_float(value)
            for value in money_matches
            if money_to_float(value) > 0
        ]

        paid = 0.0
        reserve = 0.0
        total = 0.0

        paid_match = re.search(
            r"(?:Paid|Paid\s*Loss|Amount\s*Paid|Loss\s*Paid)\s*[:\-]?\s*(\$?\(?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\)?)",
            block,
            re.IGNORECASE,
        )

        reserve_match = re.search(
            r"(?:Reserve|Case\s*Reserve|Outstanding\s*Reserve|Open\s*Reserve)\s*[:\-]?\s*(\$?\(?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\)?)",
            block,
            re.IGNORECASE,
        )

        total_match = re.search(
            r"(?:Total\s*Incurred|Incurred|Gross\s*Incurred|Net\s*Incurred)\s*[:\-]?\s*(\$?\(?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\)?)",
            block,
            re.IGNORECASE,
        )

        if paid_match:
            paid = money_to_float(paid_match.group(1))

        if reserve_match:
            reserve = money_to_float(reserve_match.group(1))

        if total_match:
            total = money_to_float(total_match.group(1))

        if total == 0 and len(money_values_clean) >= 3:
            paid = paid or money_values_clean[-3]
            reserve = reserve or money_values_clean[-2]
            total = money_values_clean[-1]
        elif total == 0 and paid + reserve > 0:
            total = paid + reserve

        if paid == 0 and reserve == 0 and total == 0:
            continue

        status = "Open" if re.search(r"\bopen\b", block, re.IGNORECASE) else "Closed"
        if re.search(r"\bclosed\b", block, re.IGNORECASE):
            status = "Closed"

        litigation = bool(re.search(r"litigation|attorney|suit|counsel|lawsuit", block, re.IGNORECASE))

        claim = {
            **profile,
            "claim_number": claim_number,
            "policy_id": 1,
            "line_of_business": detect_line(block, claim_number),
            "claim_type": detect_line(block, claim_number),
            "cause_of_loss": find_text_after_label(["Cause of Loss", "Loss Cause", "Cause"], block, 80) or "Needs Review",
            "claimant_type": find_text_after_label(["Claimant Type", "Claimant"], block, 80) or "Needs Review",
            "date_of_loss": find_date_after_label(["Date of Loss", "Loss Date", "DOL"], block) or "",
            "date_reported": find_date_after_label(["Date Reported", "Reported Date", "Report Date"], block) or "",
            "date_closed": find_date_after_label(["Date Closed", "Closed Date"], block) or "",
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
            "flag": "Litigation exposure" if litigation else "",
        }

        claims.append(claim)
        seen.add(claim_number)

    return claims


def extract_profile_from_text(text):
    text = normalize_whitespace(text or "")

    carrier = detect_real_carrier(text)

    effective, expiration = find_policy_period_dates(text)

    policy_rows = extract_policy_rows(text)
    primary_policy = ""

    if policy_rows:
        primary_policy = policy_rows[0].get("policy_number") or ""

    profile = {
        "business_name": find_text_after_label(
            [
                "Named Insured",
                "Insured Name",
                "Insured",
                "Account Name",
                "Customer Name",
                "Client Name",
            ],
            text,
            max_chars=100,
        ),
        "carrier_name": carrier,
        "agency_name": find_text_after_label(
            [
                "Agent Name",
                "Agency Name",
                "Agency",
                "Broker Name",
                "Broker",
                "Producer",
            ],
            text,
            max_chars=100,
        ),
        "policy_number": primary_policy
        or find_text_after_label(
            ["Policy Number", "Policy No.", "Policy No", "Policy #", "Policy ID"],
            text,
            max_chars=60,
        ),
        "effective_date": effective
        or find_date_after_label(
            [
                "Effective Date",
                "Policy Effective Date",
                "Policy Inception",
                "Eff Date",
                "Effective",
            ],
            text,
        ),
        "expiration_date": expiration
        or find_date_after_label(
            [
                "Expiration Date",
                "Policy Expiration Date",
                "Cancellation Date",
                "Exp Date",
                "Expiration",
            ],
            text,
        ),
        "evaluation_date": find_date_after_label(
            [
                "Evaluation Date",
                "Report Date",
                "Run Date",
                "Valuation Date",
                "Loss Run Date",
            ],
            text,
        ),
    }

    account_number = find_account_number(text)

    if account_number:
        profile["account_number"] = account_number

    if policy_rows:
        profile["policies"] = policy_rows

    if not profile.get("carrier_name"):
        profile["carrier_name"] = "Unknown Carrier"

    return profile
    account_number = find_account_number(text)

    if account_number:
        profile["account_number"] = account_number

    if policy_rows:
        profile["policies"] = policy_rows

    if not profile.get("carrier_name"):
        profile["carrier_name"] = "Unknown Carrier"

    return profile
    return {
        "business_name": find_text_after_label(
            [
                "Named Insured",
                "Insured Name",
                "Insured",
                "Business Name",
                "Account Name",
                "Policyholder",
                "Customer Name",
                "Client Name",
            ],
            text,
        ),
        "carrier_name": carrier,
        "agency_name": find_text_after_label(
            [
                "Agent Name",
                "Agency Name",
                "Agency",
                "Broker Name",
                "Broker",
                "Producer",
            ],
            text,
        ),
        "policy_number": find_text_after_label(
            ["Policy Number", "Policy No.", "Policy No", "Policy #", "Policy ID"],
            text,
            max_chars=60,
        ),
        "effective_date": effective
        or find_date_after_label(
            [
                "Effective Date",
                "Policy Effective Date",
                "Policy Inception",
                "Eff Date",
                "Effective",
            ],
            text,
        ),
        "expiration_date": expiration
        or find_date_after_label(
            [
                "Expiration Date",
                "Policy Expiration Date",
                "Cancellation Date",
                "Exp Date",
                "Expiration",
            ],
            text,
        ),
        "evaluation_date": find_date_after_label(
            [
                "Evaluation Date",
                "Valuation Date",
                "Loss Run Date",
                "Loss Runs as of",
                "As Of",
                "Run Date",
                "Report Date",
                "Print Date",
            ],
            text,
        ),
    }


def detect_line(block, claim_number=""):
    lower = str(block or "").lower()
    claim = str(claim_number or "").upper()

    if "CARGO" in claim or "MTC" in claim:
        return "Motor Truck Cargo"

    if "GL" in claim:
        return "General Liability"

    if "WC" in claim:
        return "Workers Compensation"

    if "AL" in claim or "CA" in claim or "AUTO" in claim:
        return "Commercial Auto"

    if "motor truck cargo" in lower or "cargo" in lower:
        return "Motor Truck Cargo"

    if "commercial auto" in lower or "auto liability" in lower or "vehicle" in lower:
        return "Commercial Auto"

    if "general liability" in lower or "premises" in lower or "gl " in lower:
        return "General Liability"

    if "workers compensation" in lower or "workers comp" in lower:
        return "Workers Compensation"

    if "property" in lower or "water damage" in lower or "fire" in lower:
        return "Property"

    return "Unknown"

def claim_number_candidates(text):
    pattern = (
        r"\b("
        r"VL[-\s]?(?:AL|CA|AUTO|GL|CARGO|MTC|WC)[-\s]?\d{3,10}"
        r"|[A-Z]{2,8}[-\s]?(?:AL|CA|AUTO|GL|CARGO|MTC|WC)[-\s]?\d{3,10}"
        r"|GL[-\s]?\d{4,12}"
        r"|AUTO[-\s]?\d{4,12}"
        r"|WC[-\s]?\d{4,12}"
        r"|PROP[-\s]?\d{4,12}"
        r"|CLM[-\s]?\d{4,12}"
        r")\b"
    )

    return list(re.finditer(pattern, text or "", re.IGNORECASE))

def build_claim(profile, claim_number, block):
    paid = find_money(
        [
            "Paid Loss Gross of Recovery",
            "Paid Loss",
            "Amount Paid",
            "Loss Paid",
            "Total Paid",
            "Paid",
        ],
        block,
    )

    reserve = find_money(
        [
            "Case Loss & Expense Reserve",
            "Outstanding Reserve",
            "Loss Reserve",
            "Total Reserve",
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

    values = money_values(block)

    # Many loss runs have columns like:
    # Paid | Reserve | Recovered | Expense | Incurred
    # The last money value is usually Total/Gross/Net Incurred.
    # The first two money values are usually Paid and Reserve.
    if values:
        if paid == 0 and len(values) >= 1:
            paid = values[0]

        if reserve == 0 and len(values) >= 2:
            reserve = values[1]

        if total == 0:
            total = values[-1]

    # If total is still blank, calculate it safely.
    if total == 0:
        total = paid + reserve

    lower = str(block or "").lower()

    litigation = any(
        word in lower
        for word in ["litigation", "attorney", "lawsuit", "counsel", "suit filed", "legal", "summons", "complaint"]
    )

    status_match = re.search(
        r"\b(Open|Closed|Pending|Denied|Settled|Reopened|Re-Opened)\b",
        block or "",
        re.IGNORECASE,
    )

    flag = None

    if total >= 100000:
        flag = "High severity claim"

    if litigation:
        flag = "Litigation exposure" if not flag else flag + " | Litigation exposure"

    return {
        **profile,
        "claim_number": clean_text(claim_number).upper(),
        "policy_id": 1,
        "line_of_business": detect_line(block, claim_number),
        "claim_type": detect_line(block, claim_number),
        "cause_of_loss": find_text_after_label(
            ["Cause of Loss", "Loss Cause", "Cause"],
            block,
            80,
        )
        or "Needs Review",
        "claimant_type": find_text_after_label(
            ["Claimant Type", "Claimant"],
            block,
            80,
        )
        or "Needs Review",
        "date_of_loss": find_date_after_label(
            ["Loss Date", "Date of Loss", "DOL", "Claim Date", "Accident Date"],
            block,
        )
        or find_any_date(block)
        or "Needs Review",
        "date_reported": find_date_after_label(
            ["Date Reported", "Reported Date", "Report Date"],
            block,
        ),
        "date_closed": find_date_after_label(
            ["Date Closed", "Closed Date", "Closure Date"],
            block,
        ),
        "status": status_match.group(1).replace("-", "").title()
        if status_match
        else "Needs Review",
        "description": clean_text(str(block or "")[:1000]),
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

    messy_claims = parse_messy_claim_rows(text, profile)

    if messy_claims:
        return messy_claims

    explicit_claim_pattern = re.compile(
        r"(?:Claim\s*Number|Claim\s*No|Claim\s*#)\s*[:\-]?\s*([A-Z]{1,10}[-\s]?\d{3,15}|\d{6,15})",
        re.IGNORECASE,
    )

    matches = list(explicit_claim_pattern.finditer(text))

    if matches:
        for index, match in enumerate(matches):
            claim_number = clean_text(match.group(1)).upper()
            start = max(match.start() - 120, 0)
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            block = text[start:end]

            if claim_number in seen:
                continue

            claim = build_claim(profile, claim_number, block)

            if (
                claim["total_incurred"] == 0
                and claim["paid_amount"] == 0
                and claim["reserve_amount"] == 0
            ):
                continue

            claims.append(claim)
            seen.add(claim_number)

        return claims

    matches = claim_number_candidates(text)

    for index, match in enumerate(matches):
        claim_number = clean_text(match.group(1)).upper()
        start = max(match.start() - 150, 0)
        end = matches[index + 1].start() if index + 1 < len(matches) else min(match.end() + 1200, len(text))
        block = text[start:end]

        if claim_number in seen:
            continue

        claim = build_claim(profile, claim_number, block)

        if (
            claim["total_incurred"] == 0
            and claim["paid_amount"] == 0
            and claim["reserve_amount"] == 0
        ):
            continue

        claims.append(claim)
        seen.add(claim_number)

    return claims

    matches = claim_number_candidates(text)

    for index, match in enumerate(matches):
        claim_number = clean_text(match.group(1)).upper()

        start = max(match.start() - 150, 0)
        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else min(match.end() + 1200, len(text))
        )

        block = text[start:end]

        has_claim_context = any(
            word in block.lower()
            for word in ["claim", "loss", "paid", "reserve", "incurred", "open", "closed"]
        )

        has_money = bool(money_values(block))

        if not has_claim_context and not has_money:
            continue

        if claim_number in seen:
            continue

        claim = build_claim(profile, claim_number, block)

        if (
            claim["total_incurred"] == 0
            and claim["paid_amount"] == 0
            and claim["reserve_amount"] == 0
        ):
            continue

        claims.append(claim)
        seen.add(claim_number)

    return claims