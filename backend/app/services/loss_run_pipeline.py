from __future__ import annotations

import re
from typing import Any


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


def lines_from_text(text: str) -> list[str]:
    return [clean_text(line) for line in (text or "").splitlines() if clean_text(line)]


def money(value: Any) -> float:
    if value is None:
        return 0.0

    text = str(value)
    text = text.replace("$", "").replace(",", "")
    text = text.replace("(", "-").replace(")", "")
    text = re.sub(r"[^0-9.\-]", "", text)

    try:
        return float(text or 0)
    except Exception:
        return 0.0


def is_money_line(value: Any) -> bool:
    return bool(re.fullmatch(r"\$?[\d,]+(?:\.\d{2})?", clean_text(value)))


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
    lines = lines_from_text(text)

    for index, line in enumerate(lines):
        upper_line = line.upper().strip(": ")

        for label in labels:
            upper_label = label.upper()

            if upper_line == upper_label:
                if index + 1 < len(lines):
                    return clean_text(lines[index + 1])[:max_chars]

            if upper_line.startswith(upper_label + ":"):
                value = line.split(":", 1)[1]
                return clean_text(value)[:max_chars]

    blob = clean_text(text)

    for label in labels:
        pattern = re.compile(
            rf"{re.escape(label)}\s*[:#\-]?\s*(.{{1,{max_chars}}})",
            re.IGNORECASE,
        )
        match = pattern.search(blob)

        if match:
            value = clean_text(match.group(1))
            value = re.split(
                r"\s{2,}| Carrier | Policy | Account | Customer | Producer | Effective | Expiration | Evaluation | Report ",
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

    carrier = find_after_label(
        text,
        [
            "Writing Carrier",
            "Insurance Carrier",
            "Carrier",
            "Insurer",
            "Company",
        ],
        120,
    )

    return carrier or "Unknown Carrier"


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
        120,
    )

    if value:
        return value

    for line in lines_from_text(text)[:100]:
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
            "Acct #",
            "Acct No",
        ],
        100,
    )

    if value:
        match = re.search(
            r"\b[A-Z]{0,10}[-]?[A-Z0-9]{3,25}[-]?[A-Z0-9]{0,20}\b",
            value,
            re.IGNORECASE,
        )

        if match:
            return match.group(0).upper()

        return value.upper()

    return ""


def detect_report_date(text: str) -> str:
    value = find_after_label(
        text,
        [
            "Valuation Date",
            "Evaluation Date",
            "Report Date",
            "Loss Run Date",
            "Run Date",
            "As Of",
        ],
        100,
    )

    return normalize_date(value)


def detect_policy_period(text: str) -> tuple[str, str]:
    lines = lines_from_text(text)

    for i, line in enumerate(lines):
        upper = line.upper()

        if upper in {"EFFECTIVE DATE", "EFFECTIVE", "EFF DATE"}:
            nearby_dates = []

            for j in range(i + 1, min(i + 12, len(lines))):
                if is_date_line(lines[j]):
                    nearby_dates.append(lines[j])

            if len(nearby_dates) >= 2:
                return normalize_date(nearby_dates[0]), normalize_date(nearby_dates[1])

        if "POLICY PERIOD" in upper:
            nearby = " ".join(lines[i : i + 10])
            dates = re.findall(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", nearby)

            if len(dates) >= 2:
                return normalize_date(dates[0]), normalize_date(dates[1])

    return "", ""


def normalize_policy_type(value: str) -> str:
    upper = clean_text(value).upper()

    if "WORKERS" in upper or "WORKER" in upper or upper == "WC":
        return "Workers Compensation"
    if "GENERAL" in upper and "LIABILITY" in upper:
        return "General Liability"
    if "BUSINESS AUTO" in upper:
        return "Business Auto"
    if "COMMERCIAL AUTO" in upper or "AUTO" in upper:
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

    return clean_text(value) or "Policy"


def looks_like_policy_number(value: str) -> bool:
    text = clean_text(value).upper()

    if len(text) < 5:
        return False

    if re.search(
        r"\b[A-Z]{1,10}[-]?(AUTO|GL|CARGO|WC|UMB|CPP|PKG|BA|AL)[-]?[A-Z0-9\-]{2,35}\b",
        text,
    ):
        return True

    if re.search(r"\b[A-Z]{2,6}\d{6,14}\b", text):
        return True

    if re.search(r"\b[A-Z0-9]{2,12}[-][A-Z0-9]{2,25}[-][A-Z0-9]{2,12}\b", text):
        return True

    return False


def infer_policy_type_from_policy_number(policy_number: str) -> str:
    upper = clean_text(policy_number).upper()

    if "AUTO" in upper or "-AL" in upper or "-BA" in upper or "TNA" in upper:
        return "Commercial Auto"
    if "-GL" in upper or "GL-" in upper:
        return "General Liability"
    if "CARGO" in upper or "-CG" in upper:
        return "Motor Truck Cargo"
    if "-WC" in upper:
        return "Workers Compensation"
    if "UMB" in upper or "TNU" in upper:
        return "Umbrella"
    if "CPP" in upper or "PKG" in upper or "TNC" in upper or "TNG" in upper:
        return "Commercial Package Policy"

    return "Policy"


def extract_policy_schedule(text: str, profile: dict[str, Any]) -> list[dict[str, Any]]:
    carrier = profile.get("carrier_name") or "Unknown Carrier"
    writing_carrier = profile.get("writing_carrier") or carrier
    account_eff = profile.get("effective_date") or ""
    account_exp = profile.get("expiration_date") or ""

    lines = lines_from_text(text)

    policies: list[dict[str, Any]] = []
    seen: set[str] = set()
    policy_type_upper = [policy_type.upper() for policy_type in POLICY_TYPE_KEYWORDS]

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

        final_type = normalize_policy_type(
            policy_type or infer_policy_type_from_policy_number(policy_number_clean)
        )

        policies.append(
            {
                "policy_type": final_type,
                "line_coverage": final_type,
                "line_of_business": final_type,
                "policy_number": policy_number_clean,
                "writing_carrier": writing_carrier,
                "carrier": carrier,
                "effective_date": display_date(effective_date) or account_eff,
                "expiration_date": display_date(expiration_date) or account_exp,
                "claim_count": int(claim_count or 0),
                "total_incurred": float(total_incurred or 0),
                "status": status,
            }
        )

    # Vertical policy schedule:
    # Commercial Auto
    # SA-AUTO-918204-25
    # 01/01/2025
    # 01/01/2026
    # Active
    # 4
    # $175,700.00
    for i, line in enumerate(lines):
        if line.upper() not in policy_type_upper:
            continue

        if (
            i + 3 < len(lines)
            and looks_like_policy_number(lines[i + 1])
            and is_date_line(lines[i + 2])
            and is_date_line(lines[i + 3])
        ):
            claim_count = 0
            total_incurred = 0.0

            for j in range(i + 4, min(i + 12, len(lines))):
                if re.fullmatch(r"\d+", lines[j]):
                    claim_count = int(lines[j])

                if is_money_line(lines[j]):
                    total_incurred = money(lines[j])
                    break

            add_policy(
                policy_number=lines[i + 1],
                policy_type=line,
                effective_date=lines[i + 2],
                expiration_date=lines[i + 3],
                claim_count=claim_count,
                total_incurred=total_incurred,
                status="Parsed from policy schedule",
            )

    # Policy-level summary:
    # SA-AUTO-918204-25
    # Commercial Auto
    # 4
    # $115,200.00
    # $60,500.00
    # $175,700.00
    for i, line in enumerate(lines):
        if not looks_like_policy_number(line):
            continue

        if i + 1 < len(lines) and lines[i + 1].upper() in policy_type_upper:
            claim_count = 0
            total_incurred = 0.0

            if i + 2 < len(lines) and re.fullmatch(r"\d+", lines[i + 2]):
                claim_count = int(lines[i + 2])

            money_values = []

            for j in range(i + 3, min(i + 9, len(lines))):
                if is_money_line(lines[j]):
                    money_values.append(money(lines[j]))

            if money_values:
                total_incurred = money_values[-1]

            add_policy(
                policy_number=line,
                policy_type=lines[i + 1],
                effective_date=account_eff,
                expiration_date=account_exp,
                claim_count=claim_count,
                total_incurred=total_incurred,
                status="Parsed from policy summary",
            )

    return policies


def extract_document_totals(text: str) -> dict[str, Any]:
    lines = lines_from_text(text)

    totals = {
        "total_claims": None,
        "open_claims": None,
        "closed_claims": None,
        "litigation_claims": None,
        "total_paid": None,
        "total_reserve": None,
        "total_incurred": None,
    }

    # Vertical summary:
    # Total Claims
    # Open Claims
    # Closed Claims
    # Litigation Claims
    # Total Paid
    # Case Reserve
    # Total Incurred
    # 9
    # 4
    # 5
    # 2
    # $168,500.00
    # $93,000.00
    # $261,500.00
    for i, line in enumerate(lines):
        if line.upper() != "TOTAL CLAIMS":
            continue

        headers = [x.upper() for x in lines[i : i + 7]]
        expected_headers = [
            "TOTAL CLAIMS",
            "OPEN CLAIMS",
            "CLOSED CLAIMS",
            "LITIGATION CLAIMS",
            "TOTAL PAID",
            "CASE RESERVE",
            "TOTAL INCURRED",
        ]

        if headers == expected_headers and i + 13 < len(lines):
            values = lines[i + 7 : i + 14]

            try:
                totals["total_claims"] = int(values[0])
                totals["open_claims"] = int(values[1])
                totals["closed_claims"] = int(values[2])
                totals["litigation_claims"] = int(values[3])
                totals["total_paid"] = money(values[4])
                totals["total_reserve"] = money(values[5])
                totals["total_incurred"] = money(values[6])
                return totals
            except Exception:
                pass

    # Customer history total:
    # Total
    # All Lines
    # 9 / 4
    # $168,500.00
    # $93,000.00
    # $261,500.00
    for i, line in enumerate(lines):
        if line.upper() == "TOTAL" and i + 5 < len(lines):
            if lines[i + 1].upper() == "ALL LINES":
                claim_match = re.search(r"(\d+)\s*/\s*(\d+)", lines[i + 2])

                if claim_match:
                    totals["total_claims"] = int(claim_match.group(1))
                    totals["open_claims"] = int(claim_match.group(2))
                    totals["total_paid"] = money(lines[i + 3])
                    totals["total_reserve"] = money(lines[i + 4])
                    totals["total_incurred"] = money(lines[i + 5])
                    return totals

    return totals


def extract_claim_rows(
    text: str,
    profile: dict[str, Any],
    policies: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    lines = lines_from_text(text)
    claims: list[dict[str, Any]] = []
    seen: set[str] = set()

    policy_map = {
        clean_text(policy.get("policy_number")).upper(): policy
        for policy in policies
        if policy.get("policy_number")
    }

    policy_type_upper = [policy_type.upper() for policy_type in POLICY_TYPE_KEYWORDS]

    def add_claim(
        claim_number: str,
        policy_number: str,
        line_type: str,
        status: str,
        paid: float,
        reserve: float,
        incurred: float,
        litigation: bool,
        description: str = "",
        loss_date: str = "",
    ):
        claim_number_clean = clean_text(claim_number).upper()
        policy_number_clean = clean_text(policy_number).upper()

        if not claim_number_clean:
            return

        if claim_number_clean in seen:
            return

        if not looks_like_policy_number(policy_number_clean):
            return

        seen.add(claim_number_clean)

        final_line = normalize_policy_type(
            line_type
            or policy_map.get(policy_number_clean, {}).get("policy_type")
            or infer_policy_type_from_policy_number(policy_number_clean)
        )

        final_incurred = float(incurred or paid + reserve or 0)

        flag = ""

        if final_incurred >= 100000:
            flag = "High severity claim"

        if litigation:
            flag = "Litigation exposure" if not flag else f"{flag} | Litigation exposure"

        claims.append(
            {
                **profile,
                "claim_number": claim_number_clean,
                "policy_number": policy_number_clean,
                "line_of_business": final_line,
                "claim_type": final_line,
                "cause_of_loss": "Needs Review",
                "claimant_type": "Needs Review",
                "date_of_loss": loss_date,
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
                "flag": flag,
            }
        )

    # Vertical claim table:
    # SA-CA-25-00011
    # 8
    # SA-AUTO-918204-25
    # Commercial Auto
    # 01/22/2025
    # Closed
    # $18,400.00
    # $0.00
    # $18,400.00
    # No
    for i, line in enumerate(lines):
        upper_line = line.upper()

        if not re.fullmatch(r"[A-Z]{2,5}-[A-Z]{2,5}-\d{2}-\d{5}", upper_line):
            continue

        idx = i
        claim_number = lines[idx]
        idx += 1

        # Some PDFs split the final digit of claim number onto the next line.
        if (
            idx < len(lines)
            and re.fullmatch(r"\d{1,3}", lines[idx])
            and idx + 1 < len(lines)
            and looks_like_policy_number(lines[idx + 1])
        ):
            claim_number = claim_number + lines[idx]
            idx += 1

        if idx >= len(lines):
            continue

        policy_number = lines[idx]

        if not looks_like_policy_number(policy_number):
            continue

        idx += 1

        if idx >= len(lines):
            continue

        line_type = lines[idx]

        if line_type.upper() not in policy_type_upper:
            continue

        idx += 1

        loss_date = ""

        if idx < len(lines) and is_date_line(lines[idx]):
            loss_date = normalize_date(lines[idx])
            idx += 1

        if idx >= len(lines):
            continue

        status = lines[idx]

        if status.upper() not in {"OPEN", "CLOSED", "REOPENED", "PENDING"}:
            continue

        idx += 1

        if idx + 2 >= len(lines):
            continue

        if not is_money_line(lines[idx]):
            continue

        paid = money(lines[idx])
        idx += 1

        if not is_money_line(lines[idx]):
            continue

        reserve = money(lines[idx])
        idx += 1

        if not is_money_line(lines[idx]):
            continue

        incurred = money(lines[idx])
        idx += 1

        litigation = False

        if idx < len(lines):
            litigation_value = lines[idx].upper()

            if litigation_value in {"YES", "Y", "TRUE"}:
                litigation = True
                idx += 1
            elif litigation_value in {"NO", "N", "FALSE"}:
                litigation = False
                idx += 1

        description_parts = []

        while idx < len(lines):
            next_line = lines[idx]
            next_upper = next_line.upper()

            if re.fullmatch(r"[A-Z]{2,5}-[A-Z]{2,5}-\d{2}-\d{5}", next_upper):
                break

            if next_upper.startswith("PAGE "):
                break

            if next_upper.startswith("POLICY-LEVEL"):
                break

            if next_upper in {
                "STATE AUTO INSURANCE GROUP",
                "CLAIM DETAIL CONTINUED",
                "CLAIM NUMBER",
                "POLICY NUMBER",
                "LINE / COVERAGE",
                "LOSS DATE",
                "STATUS",
                "PAID",
                "RESERVE",
                "TOTAL INCURRED",
                "LITIGATION",
                "DESCRIPTION",
            }:
                idx += 1
                continue

            description_parts.append(next_line)
            idx += 1

        add_claim(
            claim_number=claim_number,
            policy_number=policy_number,
            line_type=line_type,
            status=status,
            paid=paid,
            reserve=reserve,
            incurred=incurred,
            litigation=litigation,
            description=" ".join(description_parts),
            loss_date=loss_date,
        )

    return claims


def update_policy_claim_totals(
    policies: list[dict[str, Any]],
    claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    for policy in policies:
        policy_number = clean_text(policy.get("policy_number")).upper()

        matching_claims = [
            claim
            for claim in claims
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


def build_validation(
    claims: list[dict[str, Any]],
    policies: list[dict[str, Any]],
    document_totals: dict[str, Any],
) -> dict[str, Any]:
    parsed_claim_count = len(claims)
    parsed_open_claims = len(
        [claim for claim in claims if clean_text(claim.get("status")).lower() == "open"]
    )
    parsed_closed_claims = len(
        [claim for claim in claims if clean_text(claim.get("status")).lower() == "closed"]
    )
    parsed_litigation_claims = len([claim for claim in claims if claim.get("litigation")])

    parsed_total_paid = round(sum(float(claim.get("paid_amount") or 0) for claim in claims), 2)
    parsed_total_reserve = round(
        sum(float(claim.get("reserve_amount") or 0) for claim in claims),
        2,
    )
    parsed_total_incurred = round(
        sum(float(claim.get("total_incurred") or 0) for claim in claims),
        2,
    )

    issues = []

    if (
        document_totals.get("total_claims") is not None
        and int(document_totals["total_claims"]) != parsed_claim_count
    ):
        issues.append(
            f"Claim count mismatch: document says {document_totals['total_claims']}, parser found {parsed_claim_count}"
        )

    if document_totals.get("total_incurred") is not None:
        diff = abs(float(document_totals["total_incurred"]) - parsed_total_incurred)

        if diff > 1:
            issues.append(
                f"Total incurred mismatch: document says {document_totals['total_incurred']}, parser found {parsed_total_incurred}"
            )

    status = "Passed" if not issues and parsed_claim_count > 0 and policies else "Needs Review"

    if parsed_claim_count == 0:
        status = "Failed"
        issues.append("No claim rows were parsed.")

    if not policies:
        status = "Failed"
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
        "document_open_claims": document_totals.get("open_claims"),
        "document_closed_claims": document_totals.get("closed_claims"),
        "document_litigation_claims": document_totals.get("litigation_claims"),
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

    carrier = detect_carrier(text)
    business_name = detect_business_name(text)
    account_number = detect_account_number(text)
    effective_date, expiration_date = detect_policy_period(text)
    evaluation_date = detect_report_date(text)

    profile = {
        "business_name": business_name,
        "carrier_name": carrier,
        "writing_carrier": carrier,
        "agency_name": find_after_label(
            text,
            ["Producer / Agency", "Agency", "Agency Name", "Producer", "Broker"],
            120,
        ),
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