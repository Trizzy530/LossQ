from __future__ import annotations

import re
from typing import Any


POLICY_TYPE_KEYWORDS = [
    "Commercial Auto",
    "Business Auto",
    "General Liability",
    "Motor Truck Cargo",
    "Cargo",
    "Workers Compensation",
    "Workers Comp",
    "Umbrella",
    "Excess Liability",
    "Commercial Package Policy",
    "Package Policy",
    "Property",
    "Inland Marine",
]


CARRIER_KEYWORDS = [
    "State Auto Insurance Group",
    "State Auto",
    "Vanliner Insurance Company",
    "Vanliner",
    "Continental Western Insurance Company",
    "Continental Western",
    "biBERK",
    "Berkshire Hathaway",
    "Progressive",
    "Travelers",
    "The Hartford",
    "Hartford",
    "Liberty Mutual",
    "Nationwide",
    "CNA",
    "Zurich",
    "Chubb",
    "AmTrust",
    "Great West",
    "Auto-Owners",
    "Sentry",
    "Old Republic",
    "Canal Insurance",
]


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def money(value: Any) -> float:
    if value is None:
        return 0.0

    text = str(value)
    text = text.replace("$", "").replace(",", "").replace("(", "-").replace(")", "")
    text = re.sub(r"[^0-9.\-]", "", text)

    try:
        return float(text or 0)
    except Exception:
        return 0.0


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

    return f"{month:02d}/{day:02d}/{year}"


def extract_pdf_text_all_pages(file_path: str) -> str:
    text_data = ""

    try:
        from pypdf import PdfReader

        reader = PdfReader(file_path)
        page_texts = []

        for page_index, page in enumerate(reader.pages):
            try:
                extracted = page.extract_text() or ""
                page_texts.append(
                    f"\n\n--- PAGE {page_index + 1} OF {len(reader.pages)} ---\n{extracted}"
                )
            except Exception as page_error:
                page_texts.append(
                    f"\n\n--- PAGE {page_index + 1} TEXT FAILED ---\n{str(page_error)}"
                )

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
            try:
                page_text = pytesseract.image_to_string(image) or ""
                ocr_pages.append(
                    f"\n\n--- OCR PAGE {page_index + 1} OF {len(images)} ---\n{page_text}"
                )
            except Exception as page_error:
                ocr_pages.append(
                    f"\n\n--- OCR PAGE {page_index + 1} FAILED ---\n{str(page_error)}"
                )

        return "\n".join(ocr_pages).strip()
    except Exception as ocr_error:
        return text_data or f"OCR failed: {str(ocr_error)}"


def find_after_label(text: str, labels: list[str], max_chars: int = 120) -> str:
    for label in labels:
        pattern = re.compile(
            rf"{re.escape(label)}\s*[:#\-]?\s*(.{{1,{max_chars}}})",
            re.IGNORECASE,
        )
        match = pattern.search(text)
        if match:
            value = clean_text(match.group(1))
            value = re.split(
                r"\s{2,}| Carrier | Policy | Account | Customer | Producer | Effective | Expiration | Evaluation ",
                value,
                flags=re.IGNORECASE,
            )[0]
            return clean_text(value)
    return ""


def detect_carrier(text: str) -> str:
    upper = text.upper()

    for carrier in CARRIER_KEYWORDS:
        if carrier.upper() in upper:
            if carrier.upper() == "STATE AUTO":
                return "State Auto Insurance Group"
            if carrier.upper() == "VANLINER":
                return "Vanliner Insurance Company"
            if carrier.upper() == "CONTINENTAL WESTERN":
                return "Continental Western Insurance Company"
            return carrier

    carrier_from_label = find_after_label(
        text,
        [
            "Carrier",
            "Insurance Carrier",
            "Company",
            "Writing Carrier",
            "Insurer",
        ],
    )

    return carrier_from_label or "Unknown Carrier"


def detect_business_name(text: str) -> str:
    value = find_after_label(
        text,
        [
            "Named Insured",
            "Insured Name",
            "Insured",
            "Account Name",
            "Customer Name",
            "Client Name",
            "Company Name",
        ],
    )

    if value:
        return value

    lines = [clean_text(x) for x in text.splitlines() if clean_text(x)]

    for line in lines[:80]:
        upper = line.upper()
        if (
            (" LLC" in upper or " INC" in upper or " CO" in upper or " COMPANY" in upper)
            and "INSURANCE" not in upper
            and "LOSS RUN" not in upper
            and "REPORT" not in upper
        ):
            return line

    return ""


def detect_account_number(text: str) -> str:
    value = find_after_label(
        text,
        [
            "Account Number",
            "Account No",
            "Customer Number",
            "Customer No",
            "Client Number",
            "Insured Number",
        ],
        max_chars=80,
    )

    if value:
        match = re.search(r"\b[A-Z]{0,6}[-]?[A-Z0-9]{4,20}[-]?[A-Z0-9]{0,10}\b", value, re.IGNORECASE)
        if match:
            return match.group(0).upper()
        return value

    match = re.search(r"\b(?:ACCT|ACCOUNT|CUST|CUSTOMER)[-:\s#]*([A-Z0-9\-]{5,30})\b", text, re.IGNORECASE)
    if match:
        return match.group(1).upper()

    return ""


def detect_report_date(text: str) -> str:
    value = find_after_label(
        text,
        [
            "Evaluation Date",
            "Valuation Date",
            "Report Date",
            "Loss Run Date",
            "Run Date",
            "As Of",
        ],
        max_chars=80,
    )

    return normalize_date(value)


def detect_policy_period(text: str) -> tuple[str, str]:
    patterns = [
        r"Policy\s+Period\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s*(?:to|\-|\–)\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"Effective\s+Date\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}).{0,80}?Expiration\s+Date\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"Eff(?:ective)?\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}).{0,80}?Exp(?:iration)?\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return normalize_date(match.group(1)), normalize_date(match.group(2))

    return "", ""


def normalize_policy_type(value: str) -> str:
    text = clean_text(value)
    upper = text.upper()

    if "WORKERS" in upper or "WORKER" in upper or upper in ["WC"]:
        return "Workers Compensation"
    if "GENERAL" in upper and "LIABILITY" in upper:
        return "General Liability"
    if "COMMERCIAL AUTO" in upper:
        return "Commercial Auto"
    if "BUSINESS AUTO" in upper:
        return "Business Auto"
    if "AUTO" in upper:
        return "Commercial Auto"
    if "MOTOR" in upper and "CARGO" in upper:
        return "Motor Truck Cargo"
    if "CARGO" in upper:
        return "Motor Truck Cargo"
    if "UMBRELLA" in upper:
        return "Umbrella"
    if "EXCESS" in upper:
        return "Excess Liability"
    if "PACKAGE" in upper or "CPP" in upper:
        return "Commercial Package Policy"
    if "PROPERTY" in upper:
        return "Property"
    if "INLAND" in upper:
        return "Inland Marine"

    return text or "Policy"


def looks_like_policy_number(value: str) -> bool:
    text = clean_text(value).upper()

    if len(text) < 5:
        return False

    if re.search(r"\b[A-Z]{1,8}[-]?(AUTO|GL|CARGO|WC|UMB|CPP|PKG|BA|AL)[-]?[A-Z0-9\-]{3,30}\b", text):
        return True

    if re.search(r"\b[A-Z]{2,6}\d{6,14}\b", text):
        return True

    if re.search(r"\b[A-Z0-9]{2,10}[-][A-Z0-9]{3,20}[-][A-Z0-9]{2,10}\b", text):
        return True

    return False


def infer_policy_type_from_policy_number(policy_number: str) -> str:
    upper = clean_text(policy_number).upper()

    if "AUTO" in upper or "-AL" in upper or "-BA" in upper:
        return "Commercial Auto"
    if "-GL" in upper or "GL-" in upper:
        return "General Liability"
    if "CARGO" in upper or "-CG" in upper:
        return "Motor Truck Cargo"
    if "-WC" in upper or "WORK" in upper:
        return "Workers Compensation"
    if "UMB" in upper or "TNU" in upper:
        return "Umbrella"
    if "CPP" in upper or "PKG" in upper or "TNC" in upper or "TNG" in upper:
        return "Commercial Package Policy"
    if "TNA" in upper:
        return "Business Auto"

    return "Policy"


def extract_policy_schedule(text: str, profile: dict[str, Any]) -> list[dict[str, Any]]:
    carrier = profile.get("carrier_name") or "Unknown Carrier"
    writing_carrier = profile.get("writing_carrier") or carrier
    account_eff = profile.get("effective_date") or ""
    account_exp = profile.get("expiration_date") or ""

    policies: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_policy(
        policy_number: str,
        policy_type: str = "",
        effective_date: str = "",
        expiration_date: str = "",
        claim_count: int = 0,
        total_incurred: float = 0.0,
        status: str = "Parsed",
    ):
        policy_number_clean = clean_text(policy_number).upper()
        if not looks_like_policy_number(policy_number_clean):
            return

        if policy_number_clean in seen:
            return

        seen.add(policy_number_clean)

        final_type = normalize_policy_type(policy_type or infer_policy_type_from_policy_number(policy_number_clean))

        policies.append(
            {
                "policy_type": final_type,
                "line_coverage": final_type,
                "line_of_business": final_type,
                "policy_number": policy_number_clean,
                "writing_carrier": writing_carrier,
                "carrier": carrier,
                "effective_date": normalize_date(effective_date) or account_eff,
                "expiration_date": normalize_date(expiration_date) or account_exp,
                "claim_count": int(claim_count or 0),
                "total_incurred": float(total_incurred or 0),
                "status": status,
            }
        )

    lines = [clean_text(line) for line in text.splitlines() if clean_text(line)]

    policy_type_group = "|".join([re.escape(x) for x in POLICY_TYPE_KEYWORDS])

    patterns = [
        # Policy Number | Line/Coverage | Effective | Expiration
        re.compile(
            rf"(?P<policy>[A-Z0-9][A-Z0-9\-]{{4,35}})\s+"
            rf"(?P<coverage>{policy_type_group})\s+"
            rf"(?P<eff>\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{2,4}})\s+"
            rf"(?P<exp>\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{2,4}})",
            re.IGNORECASE,
        ),
        # Line/Coverage | Policy Number | Effective | Expiration
        re.compile(
            rf"(?P<coverage>{policy_type_group})\s+"
            rf"(?P<policy>[A-Z0-9][A-Z0-9\-]{{4,35}})\s+"
            rf"(?P<eff>\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{2,4}})\s+"
            rf"(?P<exp>\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{2,4}})",
            re.IGNORECASE,
        ),
        # Policy: ABC123 Coverage: Auto Effective: date Expiration: date
        re.compile(
            rf"Policy\s*(?:Number|No\.?|#)?\s*[:\-]?\s*(?P<policy>[A-Z0-9\-]{{5,35}}).{{0,120}}?"
            rf"(?:Line|Coverage|LOB|Policy Type)\s*[:\-]?\s*(?P<coverage>{policy_type_group}).{{0,120}}?"
            rf"(?:Effective|Eff)\s*[:\-]?\s*(?P<eff>\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{2,4}}).{{0,80}}?"
            rf"(?:Expiration|Exp)\s*[:\-]?\s*(?P<exp>\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{2,4}})",
            re.IGNORECASE | re.DOTALL,
        ),
    ]

    for pattern in patterns:
        for match in pattern.finditer(text):
            add_policy(
                policy_number=match.group("policy"),
                policy_type=match.group("coverage"),
                effective_date=match.group("eff"),
                expiration_date=match.group("exp"),
                status="Parsed from policy schedule",
            )

    for line in lines:
        if not any(keyword.upper() in line.upper() for keyword in POLICY_TYPE_KEYWORDS):
            continue

        dates = re.findall(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", line)
        candidates = re.findall(r"\b[A-Z0-9][A-Z0-9\-]{4,35}\b", line.upper())

        policy_number = ""
        for candidate in candidates:
            if looks_like_policy_number(candidate):
                policy_number = candidate
                break

        coverage = ""
        for keyword in POLICY_TYPE_KEYWORDS:
            if keyword.upper() in line.upper():
                coverage = keyword
                break

        if policy_number:
            add_policy(
                policy_number=policy_number,
                policy_type=coverage,
                effective_date=dates[0] if len(dates) >= 1 else account_eff,
                expiration_date=dates[1] if len(dates) >= 2 else account_exp,
                status="Parsed from line",
            )

    return policies


def extract_document_totals(text: str) -> dict[str, Any]:
    totals = {
        "total_claims": None,
        "open_claims": None,
        "closed_claims": None,
        "litigation_claims": None,
        "total_paid": None,
        "total_reserve": None,
        "total_incurred": None,
    }

    patterns = {
        "total_claims": [
            r"Total\s+Claims\s*[:\-]?\s*(\d+)",
            r"Claims\s+Reported\s*[:\-]?\s*(\d+)",
        ],
        "open_claims": [
            r"Open\s+Claims\s*[:\-]?\s*(\d+)",
        ],
        "closed_claims": [
            r"Closed\s+Claims\s*[:\-]?\s*(\d+)",
        ],
        "litigation_claims": [
            r"Litigation\s+Claims\s*[:\-]?\s*(\d+)",
            r"Claims\s+in\s+Litigation\s*[:\-]?\s*(\d+)",
        ],
        "total_paid": [
            r"Total\s+Paid\s*[:\-]?\s*\$?([\d,]+(?:\.\d{2})?)",
            r"Paid\s+Total\s*[:\-]?\s*\$?([\d,]+(?:\.\d{2})?)",
        ],
        "total_reserve": [
            r"Total\s+Reserve\s*[:\-]?\s*\$?([\d,]+(?:\.\d{2})?)",
            r"Case\s+Reserve\s*[:\-]?\s*\$?([\d,]+(?:\.\d{2})?)",
            r"Outstanding\s+Reserve\s*[:\-]?\s*\$?([\d,]+(?:\.\d{2})?)",
        ],
        "total_incurred": [
            r"Total\s+Incurred\s*[:\-]?\s*\$?([\d,]+(?:\.\d{2})?)",
            r"Net\s+Incurred\s*[:\-]?\s*\$?([\d,]+(?:\.\d{2})?)",
            r"Gross\s+Incurred\s*[:\-]?\s*\$?([\d,]+(?:\.\d{2})?)",
        ],
    }

    for key, key_patterns in patterns.items():
        for pattern in key_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if "claims" in key:
                    totals[key] = int(match.group(1))
                else:
                    totals[key] = money(match.group(1))
                break

    return totals


def extract_claim_rows(text: str, profile: dict[str, Any], policies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    seen: set[str] = set()

    policy_map = {
        clean_text(policy.get("policy_number")).upper(): policy
        for policy in policies
        if policy.get("policy_number")
    }

    policy_numbers = list(policy_map.keys())
    policy_type_group = "|".join([re.escape(x) for x in POLICY_TYPE_KEYWORDS])

    lines = [clean_text(line) for line in text.splitlines() if clean_text(line)]

    claim_patterns = [
        re.compile(
            rf"(?P<claim>[A-Z]{{1,10}}[-]?[A-Z]{{0,5}}[-]?\d{{2,6}}[-]?\d{{2,8}})\s+"
            rf"(?P<policy>[A-Z0-9][A-Z0-9\-]{{4,35}})\s+"
            rf"(?P<coverage>{policy_type_group})\s+"
            rf"(?P<status>Open|Closed|Reopened|Pending)\s+"
            rf"\$?(?P<paid>[\d,]+(?:\.\d{{2}})?)\s+"
            rf"\$?(?P<reserve>[\d,]+(?:\.\d{{2}})?)\s+"
            rf"\$?(?P<incurred>[\d,]+(?:\.\d{{2}})?)",
            re.IGNORECASE,
        ),
        re.compile(
            rf"(?P<claim>[A-Z0-9\-]{{5,30}})\s+"
            rf"(?P<status>Open|Closed|Reopened|Pending)\s+"
            rf"(?P<policy>[A-Z0-9][A-Z0-9\-]{{4,35}})\s+"
            rf"(?P<coverage>{policy_type_group})\s+"
            rf"\$?(?P<paid>[\d,]+(?:\.\d{{2}})?)\s+"
            rf"\$?(?P<reserve>[\d,]+(?:\.\d{{2}})?)\s+"
            rf"\$?(?P<incurred>[\d,]+(?:\.\d{{2}})?)",
            re.IGNORECASE,
        ),
    ]

    def add_claim(match):
        claim_number = clean_text(match.group("claim")).upper()

        if claim_number in seen:
            return

        policy_number = clean_text(match.group("policy")).upper()
        if not looks_like_policy_number(policy_number):
            return

        status = clean_text(match.group("status")).title()
        line = normalize_policy_type(match.group("coverage"))

        paid = money(match.group("paid"))
        reserve = money(match.group("reserve"))
        incurred = money(match.group("incurred"))

        if incurred <= 0 and paid + reserve > 0:
            incurred = paid + reserve

        seen.add(claim_number)

        claims.append(
            {
                **profile,
                "claim_number": claim_number,
                "policy_number": policy_number,
                "line_of_business": line,
                "claim_type": line,
                "cause_of_loss": "Needs Review",
                "claimant_type": "Needs Review",
                "date_of_loss": "",
                "date_reported": "",
                "date_closed": "",
                "status": status,
                "description": "Parsed from loss run.",
                "paid_amount": paid,
                "reserve_amount": reserve,
                "total_incurred": incurred,
                "net_incurred": incurred,
                "litigation": False,
                "litigation_status": "Needs Review",
                "attorney_assigned": False,
                "suit_filed": False,
                "venue_state": "Needs Review",
                "injury_type": "Needs Review",
                "flag": "",
            }
        )

    for line in lines:
        if "TOTAL" in line.upper() and "CLAIM" in line.upper():
            continue

        for pattern in claim_patterns:
            match = pattern.search(line)
            if match:
                add_claim(match)
                break

    if not claims:
        for line in lines:
            upper = line.upper()

            if not any(policy_number in upper for policy_number in policy_numbers):
                continue

            money_values = re.findall(r"\$?[\d,]+(?:\.\d{2})?", line)
            if len(money_values) < 1:
                continue

            claim_match = re.search(r"\b[A-Z]{1,10}[-]?[A-Z]{0,5}[-]?\d{2,6}[-]?\d{2,8}\b", line)
            if not claim_match:
                continue

            claim_number = claim_match.group(0).upper()
            if claim_number in seen:
                continue

            policy_number = ""
            for candidate in policy_numbers:
                if candidate in upper:
                    policy_number = candidate
                    break

            if not policy_number:
                continue

            policy = policy_map.get(policy_number, {})
            line_type = policy.get("policy_type") or infer_policy_type_from_policy_number(policy_number)

            status = "Closed" if "CLOSED" in upper else "Open" if "OPEN" in upper else "Needs Review"

            paid = money(money_values[-3]) if len(money_values) >= 3 else 0
            reserve = money(money_values[-2]) if len(money_values) >= 2 else 0
            incurred = money(money_values[-1]) if len(money_values) >= 1 else paid + reserve

            seen.add(claim_number)

            claims.append(
                {
                    **profile,
                    "claim_number": claim_number,
                    "policy_number": policy_number,
                    "line_of_business": line_type,
                    "claim_type": line_type,
                    "cause_of_loss": "Needs Review",
                    "claimant_type": "Needs Review",
                    "date_of_loss": "",
                    "date_reported": "",
                    "date_closed": "",
                    "status": status,
                    "description": "Parsed from loss run.",
                    "paid_amount": paid,
                    "reserve_amount": reserve,
                    "total_incurred": incurred,
                    "net_incurred": incurred,
                    "litigation": "LITIGATION" in upper or "ATTORNEY" in upper or "SUIT" in upper,
                    "litigation_status": "Litigation detected" if ("LITIGATION" in upper or "ATTORNEY" in upper or "SUIT" in upper) else "None",
                    "attorney_assigned": "ATTORNEY" in upper,
                    "suit_filed": "SUIT" in upper,
                    "venue_state": "Needs Review",
                    "injury_type": "Needs Review",
                    "flag": "Litigation exposure" if ("LITIGATION" in upper or "ATTORNEY" in upper or "SUIT" in upper) else "",
                }
            )

    return claims


def update_policy_claim_totals(policies: list[dict[str, Any]], claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for policy in policies:
        policy_number = clean_text(policy.get("policy_number")).upper()
        matching_claims = [
            claim for claim in claims
            if clean_text(claim.get("policy_number")).upper() == policy_number
        ]

        if matching_claims:
            policy["claim_count"] = len(matching_claims)
            policy["total_incurred"] = round(
                sum(float(claim.get("total_incurred") or 0) for claim in matching_claims),
                2,
            )
            policy["status"] = "Claims Reported"
        else:
            policy["claim_count"] = int(policy.get("claim_count") or 0)
            policy["total_incurred"] = float(policy.get("total_incurred") or 0)
            policy["status"] = policy.get("status") or "Nothing to Report"

    return policies


def build_validation(claims: list[dict[str, Any]], policies: list[dict[str, Any]], document_totals: dict[str, Any]) -> dict[str, Any]:
    parsed_claim_count = len(claims)
    parsed_open_claims = len([claim for claim in claims if clean_text(claim.get("status")).lower() == "open"])
    parsed_closed_claims = len([claim for claim in claims if clean_text(claim.get("status")).lower() == "closed"])
    parsed_litigation_claims = len([claim for claim in claims if claim.get("litigation")])
    parsed_total_incurred = round(sum(float(claim.get("total_incurred") or 0) for claim in claims), 2)
    parsed_total_paid = round(sum(float(claim.get("paid_amount") or 0) for claim in claims), 2)
    parsed_total_reserve = round(sum(float(claim.get("reserve_amount") or 0) for claim in claims), 2)

    issues = []

    if document_totals.get("total_claims") is not None and document_totals["total_claims"] != parsed_claim_count:
        issues.append(f"Claim count mismatch: document says {document_totals['total_claims']}, parser found {parsed_claim_count}")

    if document_totals.get("total_incurred") is not None:
        diff = abs(float(document_totals["total_incurred"]) - parsed_total_incurred)
        if diff > 1:
            issues.append(f"Total incurred mismatch: document says {document_totals['total_incurred']}, parser found {parsed_total_incurred}")

    status = "Passed" if not issues and parsed_claim_count > 0 else "Needs Review"

    if parsed_claim_count == 0:
        status = "Failed"
        issues.append("No claim rows were parsed.")

    if not policies:
        status = "Needs Review"
        issues.append("No policy schedule rows were parsed.")

    return {
        "status": status,
        "issues": issues,
        "parsed_claim_count": parsed_claim_count,
        "parsed_open_claims": parsed_open_claims,
        "parsed_closed_claims": parsed_closed_claims,
        "parsed_litigation_claims": parsed_litigation_claims,
        "parsed_total_paid": parsed_total_paid,
        "parsed_total_reserve": parsed_total_reserve,
        "parsed_total_incurred": parsed_total_incurred,
        "document_total_claims": document_totals.get("total_claims"),
        "document_total_incurred": document_totals.get("total_incurred"),
        "policy_count": len(policies),
    }


def parse_loss_run_file(file_path: str, filename: str):
    lower_name = str(filename or "").lower()

    if lower_name.endswith(".pdf"):
        text = extract_pdf_text_all_pages(file_path)
    else:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except Exception:
            text = ""

    carrier = detect_carrier(text)
    business_name = detect_business_name(text)
    account_number = detect_account_number(text)
    effective_date, expiration_date = detect_policy_period(text)
    evaluation_date = detect_report_date(text)

    profile = {
        "business_name": business_name,
        "carrier_name": carrier,
        "writing_carrier": carrier,
        "agency_name": find_after_label(text, ["Agency", "Agency Name", "Producer", "Broker"], max_chars=100),
        "account_number": account_number,
        "customer_number": account_number,
        "policy_number": account_number or "",
        "effective_date": effective_date,
        "expiration_date": expiration_date,
        "evaluation_date": evaluation_date,
    }

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
        "validation": validation,
        "raw_text_preview": text[:5000],
    }