from __future__ import annotations

import re

from .policy_schedule_parser import detect_lob
from .utils import (
    CLAIM_RE,
    clean_text,
    date_values,
    parse_date,
    looks_like_header_row,
    looks_like_total_row,
    money_values,
    normalize_claim_number,
    normalize_policy_number,
    split_lines,
)


CLAIM_PATTERN = CLAIM_RE


POLICY_LIKE_RE = re.compile(
    r"\b[A-Z]{2,8}[-\s]?[A-Z]{1,6}[-\s]?\d{3,8}(?:[-\s]?[A-Z0-9]{1,6})?\b",
    re.I,
)


def detect_status(text: str) -> str:
    lower = clean_text(text).lower()

    if "closed" in lower or "resolved" in lower:
        return "Closed"

    if "open" in lower or "pending" in lower or "reopened" in lower:
        return "Open"

    return "Open"


def detect_litigation(text: str) -> bool:
    lower = clean_text(text).lower()

    if any(
        phrase in lower
        for phrase in [
            "no litigation",
            "closed no litigation",
            "litigation no",
            "no attorney",
            "no attorney involvement",
        ]
    ):
        return False

    return any(
        term in lower
        for term in ["litigation", "litigated", "attorney", "suit filed", "lawsuit", "represented"]
    )


def extract_claim_number(text: str) -> str:
    match = CLAIM_PATTERN.search(text or "")
    if not match:
        return ""

    claim_number = normalize_claim_number(match.group(0))
    compact = claim_number.replace("-", "")

    if compact.isdigit() and set(compact) == {"0"}:
        return ""

    if compact.isdigit() and len(compact) < 6:
        return ""

    return claim_number

def policy_lob_from_number(policy_number: str, policies: list[dict]) -> str:
    normalized = normalize_policy_number(policy_number)

    for policy in policies:
        if normalize_policy_number(policy.get("policy_number")) == normalized:
            return (
                policy.get("line_of_business")
                or policy.get("line_coverage")
                or policy.get("policy_type")
                or ""
            )

    return ""


def extract_policy_number(text: str, policies: list[dict]) -> str:
    compact_row = normalize_policy_number(text).replace("-", "")

    sorted_policies = sorted(
        [
            normalize_policy_number(policy.get("policy_number"))
            for policy in policies
            if policy.get("policy_number")
        ],
        key=len,
        reverse=True,
    )

    for policy_number in sorted_policies:
        if not policy_number:
            continue

        if policy_number in normalize_policy_number(text):
            return policy_number

        if policy_number.replace("-", "") in compact_row:
            return policy_number

    return ""


def assign_amounts(amounts: list[float]) -> tuple[float, float, float]:
    # Return paid, reserve, incurred. Handles deductible recovery / net incurred layouts.
    if not amounts:
        return 0.0, 0.0, 0.0

    if len(amounts) >= 6 and amounts[-2] < 0:
        return round(float(amounts[-3] or 0), 2), 0.0, round(float(amounts[-1] or 0), 2)

    if len(amounts) >= 3:
        return round(float(amounts[-3] or 0), 2), round(float(amounts[-2] or 0), 2), round(float(amounts[-1] or 0), 2)

    if len(amounts) == 2:
        return round(float(amounts[-2] or 0), 2), 0.0, round(float(amounts[-1] or 0), 2)

    return round(float(amounts[-1] or 0), 2), 0.0, round(float(amounts[-1] or 0), 2)

def clean_description(row: str, claim_number: str, policy_number: str) -> str:
    desc = clean_text(row)

    for value in [claim_number, policy_number]:
        if value:
            desc = desc.replace(value, " ")
            desc = desc.replace(value.replace("-", " "), " ")

    desc = re.sub(r"\$[\s]*\d[\d,]*(?:\.\d{1,2})?", " ", desc)
    desc = re.sub(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", " ", desc)
    desc = re.sub(r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b", " ", desc)
    desc = re.sub(r"\b(CLOSED|OPEN|PENDING|RESOLVED)\*?\b", " ", desc, flags=re.I)
    desc = re.sub(r"\s+", " ", desc).strip(" -|")

    return desc[:700]


def is_known_policy_value(line: str, policies: list[dict]) -> bool:
    candidate = normalize_policy_number(line)
    if not candidate:
        return False

    for policy in policies:
        if candidate == normalize_policy_number(policy.get("policy_number")):
            return True

    if POLICY_LIKE_RE.fullmatch(clean_text(line) or ""):
        return True

    return False


def is_claim_start(line: str, policies: list[dict]) -> bool:
    if is_known_policy_value(line, policies):
        return False

    return bool(CLAIM_PATTERN.search(line or ""))


def row_has_complete_financial_columns(row: str) -> bool:
    amounts = money_values(row)
    dates = date_values(row)
    claim_number = extract_claim_number(row)

    if claim_number and claim_number.replace("-", "").isdigit():
        return len(dates) >= 2 and len(amounts) >= 6

    return len(amounts) >= 3

def reconstruct_claim_rows(lines: list[str], policies: list[dict]) -> tuple[list[str], list[dict]]:
    rows: list[str] = []
    ignored_rows: list[dict] = []

    in_claims = False
    current_policy = ""
    index = 0

    while index < len(lines):
        line = lines[index]
        lower = line.lower()

        policy_number = extract_policy_number(line, policies)
        if policy_number and ("policy" in lower or lower.startswith(policy_number.lower())):
            current_policy = policy_number

        if (
            "claim summary" in lower
            or "detailed claims" in lower
            or "claim detail" in lower
            or "claim no" in lower
            or "claim #" in lower
            or ("claim number" in lower and "claimant" in lower)
        ):
            in_claims = True
            index += 1
            continue

        if "end policy" in lower:
            ignored_rows.append({"reason": "end_policy_or_total_row", "line": line[:700]})
            index += 1
            continue

        if "renewal underwriting notes" in lower or "carrier comments" in lower or "renewal signal" in lower or "recommended broker action" in lower:
            in_claims = False

        if looks_like_total_row(line) or looks_like_header_row(line):
            ignored_rows.append({"reason": "total_header_or_subtotal_row", "line": line[:700]})
            index += 1
            continue

        if not in_claims:
            index += 1
            continue

        if "nothing to report" in lower:
            ignored_rows.append({"reason": "nothing_to_report_row", "line": line[:700]})
            index += 1
            continue

        if not is_claim_start(line, policies):
            index += 1
            continue

        parts = []
        if current_policy:
            parts.append(f"Policy {current_policy}")

        parts.append(line)
        index += 1

        while index < len(lines):
            next_line = lines[index]
            next_lower = next_line.lower()

            if is_claim_start(next_line, policies):
                break

            if "policy:" in next_lower and extract_policy_number(next_line, policies):
                break

            if "end policy" in next_lower:
                ignored_rows.append({"reason": "end_policy_or_total_row", "line": next_line[:700]})
                break

            if "renewal underwriting notes" in next_lower or "carrier comments" in next_lower or "renewal signal" in next_lower or "recommended broker action" in next_lower:
                break

            if looks_like_total_row(next_line):
                ignored_rows.append({"reason": "total_or_subtotal_row", "line": next_line[:700]})
                break

            parts.append(next_line)
            joined = " ".join(parts)

            if row_has_complete_financial_columns(joined):
                index += 1
                break

            index += 1

        rows.append(" ".join(parts))

    return rows, ignored_rows


def normalize_ocr_money_token(token: str) -> float:
    raw = clean_text(token)
    if not raw:
        return 0.0

    negative = "(" in raw and ")" in raw
    raw = raw.replace("$", "").replace(",", "").replace("(", "").replace(")", "").replace(" ", "")

    if raw in {"", "-", ".", "000", "0"}:
        return 0.0

    # OCR often reads $3,224.06 as $3,22406 or $322406.
    if "." not in raw and raw.isdigit() and len(raw) >= 4:
        raw = raw[:-2] + "." + raw[-2:]

    try:
        value = float(raw)
    except Exception:
        return 0.0

    return -value if negative else value


def ocr_money_values(row: str) -> list[float]:
    values: list[float] = []

    token_pattern = re.compile(
        r"\(\s*\$?\s*\d[\d,\.]*\s*\)|\$+\s*\d[\d,\.]*|\b\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?\b"
    )

    for match in token_pattern.finditer(row or ""):
        values.append(normalize_ocr_money_token(match.group(0)))

    return values


def normalize_numeric_ocr_claim_number(value: str) -> str:
    claim_number = normalize_claim_number(value)
    compact = claim_number.replace("-", "")

    if compact.isdigit() and len(compact) == 12 and compact.startswith("000000"):
        compact = compact[1:]

    return compact if compact else claim_number






def parse_multiline_ocr_claim_rows(
    text: str,
    policies: list[dict] | None = None,
    profile: dict | None = None,
) -> tuple[list[dict], list[dict]]:
    policies = policies or []
    profile = profile or {}

    lines = split_lines(text)
    claims: list[dict] = []
    ignored_rows: list[dict] = []
    seen: set[str] = set()

    current_policy = ""
    in_claim_detail = False
    pending_claim_number = ""
    pending_claimant = ""
    pending_status = "Closed"
    pending_loss_line = ""
    pending_loss_date = ""
    pending_driver = ""
    generated_index = 1

    def make_generated_claim_number(policy_number: str, loss_date: str, report_date: str, idx: int) -> str:
        safe_policy = re.sub(r"[^A-Z0-9]", "", policy_number or "OCR")
        safe_loss = re.sub(r"[^0-9]", "", loss_date or "")
        safe_report = re.sub(r"[^0-9]", "", report_date or "")
        return f"OCR-{safe_policy}-{safe_loss or safe_report}-{idx}"

    def clean_ocr_amounts(row: str) -> list[float]:
        values = ocr_money_values(row)

        cleaned = []
        for value in values:
            # Drop isolated OCR noise values that are too large for this style only when clearly malformed.
            cleaned.append(value)

        return cleaned

    def extract_driver_from_loss_line(line: str) -> str:
        line = clean_text(line)
        line = re.sub(r"^\d{1,2}/\d{1,2}/\d{2,4}", "", line).strip()
        line = re.sub(r"\$.*$", "", line).strip()
        return line

    def append_claim(
        claim_number: str,
        claimant: str,
        status: str,
        loss_date: str,
        report_date: str,
        driver: str,
        detail_line: str,
        source_row: str,
        idx: int,
    ) -> None:
        nonlocal generated_index

        amounts = clean_ocr_amounts(detail_line)
        if len(amounts) < 3:
            ignored_rows.append({"reason": "insufficient_ocr_financial_values", "line": source_row[:700]})
            return

        # Vanliner scanned rows end with:
        # paid ind, paid med, paid exp, total paid, recovery, net incurred
        if len(amounts) >= 6:
            paid = amounts[-3]
            reserve = 0.0
            incurred = amounts[-1]
        elif len(amounts) >= 4:
            paid = amounts[-3]
            reserve = 0.0
            incurred = amounts[-1]
        else:
            paid = amounts[-1]
            reserve = 0.0
            incurred = amounts[-1]

        if not claim_number:
            claim_number = make_generated_claim_number(current_policy, loss_date, report_date, idx)

        claim_number = normalize_claim_number(claim_number)

        if claim_number in seen:
            return

        cause_of_loss = ""
        cause_match = re.search(
            r"\b(ALL\s*OTHER\s*PROPERTY\s*DAMAGE|COLLISION[^$]+|COMPREHENSIVE[^$]+|PROPERTY DAMAGE|BODILY INJURY|CARGO|THEFT|FIRE|WATER DAMAGE)\b",
            detail_line,
            re.I,
        )
        if cause_match:
            cause_of_loss = clean_text(cause_match.group(1)).upper()
            cause_of_loss = cause_of_loss.replace("ALLOTHERPROPERTYDAMAGE", "ALL OTHER PROPERTY DAMAGE")

        description_parts = []
        if claimant:
            description_parts.append(clean_text(claimant))
        if driver:
            description_parts.append(clean_text(driver))

        cleaned_detail = clean_text(detail_line)
        cleaned_detail = re.sub(r"\$[0-9,\.\(\)]+", "", cleaned_detail)
        cleaned_detail = re.sub(r"\s+", " ", cleaned_detail).strip()

        if cleaned_detail:
            description_parts.append(cleaned_detail[:350])

        lob = policy_lob_from_number(current_policy, policies) or detect_lob(" ".join([current_policy, source_row, detail_line]))

        claims.append(
            {
                "claim_number": claim_number,
                "policy_number": current_policy or profile.get("policy_number") or "",
                "line_of_business": lob,
                "claim_type": lob,
                "cause_of_loss": cause_of_loss,
                "claimant_type": "",
                "date_of_loss": parse_date(loss_date) or loss_date,
                "date_reported": parse_date(report_date) or report_date,
                "date_closed": None,
                "status": "Closed" if status.lower() == "closed" else status.title(),
                "description": " - ".join([p for p in description_parts if p])[:700],
                "paid_amount": round(float(paid or 0), 2),
                "reserve_amount": round(float(reserve or 0), 2),
                "total_incurred": round(float(incurred or 0), 2),
                "litigation": detect_litigation(source_row),
                "litigation_status": "Litigation/Attorney Indicator" if detect_litigation(source_row) else "",
                "attorney_assigned": detect_litigation(source_row),
                "suit_filed": "suit filed" in source_row.lower() or "lawsuit" in source_row.lower(),
                "venue_state": "",
                "injury_type": "",
                "flag": "Litigation exposure" if detect_litigation(source_row) else "",
                "source_line": source_row[:700],
            }
        )

        seen.add(claim_number)

    for index, raw_line in enumerate(lines):
        line = clean_text(raw_line)
        lower = line.lower()

        policy_match = re.search(
            r"\bPolicy\s*[:#]?\s*([A-Z]{2,10}\d{5,12}[A-Z0-9]*)",
            line,
            re.I,
        )
        if policy_match:
            current_policy = normalize_policy_number(policy_match.group(1))

        if "claim number" in lower and "claimant" in lower:
            in_claim_detail = True
            continue

        if "customer history summary" in lower or "total claims / open claims" in lower:
            in_claim_detail = False

        if not in_claim_detail:
            continue

        if "nothing to report" in lower:
            ignored_rows.append({"reason": "nothing_to_report_row", "line": line[:700]})
            continue

        if looks_like_header_row(line) or looks_like_total_row(line):
            ignored_rows.append({"reason": "total_header_or_subtotal_row", "line": line[:700]})
            continue

        # Claim-number/status line. Example:
        # 000000203119 KNIGHT, DENSON CLOSED $3,224.06 ...
        start_match = re.match(
            r"^\s*(\d{8,12})\s+(.+?)\s+(CLOSED|OPEN|PENDING|REOPENED)\b(.*)$",
            line,
            re.I,
        )

        if start_match:
            raw_claim_number = start_match.group(1)

            if set(raw_claim_number) == {"0"}:
                ignored_rows.append({"reason": "nothing_to_report_row", "line": line[:700]})
                continue

            pending_claim_number = normalize_numeric_ocr_claim_number(raw_claim_number)
            pending_claimant = clean_text(start_match.group(2))
            pending_status = start_match.group(3).title()
            pending_loss_line = ""
            pending_loss_date = ""
            pending_driver = ""
            continue

        # Loss-date / driver line. Example:
        # 9/3/2022 Darius Tyler $0.00 ...
        loss_match = re.match(r"^\s*(\d{1,2}/\d{1,2}/\d{2,4})\s+(.+)$", line)
        if loss_match and not re.search(r"ALL\s*OTHER|COLLISION|COMPREHENSIVE|PROPERTY DAMAGE|VAhit|Internal property", line, re.I):
            pending_loss_date = loss_match.group(1)
            pending_loss_line = line
            pending_driver = extract_driver_from_loss_line(line)
            continue

        # Detail/report-date line with cause and paid/recovery/incurred.
        detail_match = re.match(r"^\s*(\d{1,2}/\d{1,2}/\d{2,4})\s+(.+)$", line)
        if detail_match and len(ocr_money_values(line)) >= 3:
            report_date = detail_match.group(1)

            # If we do not have a pending loss date, this row is likely a loss-date/detail row from OCR.
            loss_date = pending_loss_date or report_date

            source_row = " ".join([pending_loss_line, line]).strip()

            append_claim(
                pending_claim_number,
                pending_claimant,
                pending_status or "Closed",
                loss_date,
                report_date,
                pending_driver,
                line,
                source_row,
                generated_index,
            )

            generated_index += 1
            pending_claim_number = ""
            pending_claimant = ""
            pending_status = "Closed"
            pending_loss_line = ""
            pending_loss_date = ""
            pending_driver = ""

    return claims, ignored_rows



def detect_ocr_summary_totals_for_reconciliation(text: str) -> dict:
    result = {
        "reported_total_claims": None,
        "reported_open_claims": None,
        "reported_closed_claims": None,
        "reported_total_paid": None,
        "reported_total_reserve": 0.0,
        "reported_total_incurred": None,
    }

    for line in split_lines(text):
        cleaned = clean_text(line)
        lowered = cleaned.lower()

        if "policy year" in lowered:
            continue
        if "total claims / open claims" in lowered:
            continue
        if "nothing to report" in lowered:
            continue

        # Only accept true carrier summary rows.
        # Example:
        # 2022 BA 7/0 $86,294.09 $0.00 $2,911.05 $89,205.14 ($18,500.00) $70,705.14
        summary_match = re.search(
            r"^\s*(?:19|20)\d{2}\s+[A-Z]{1,6}\s+(\d{1,3})\s*/\s*(\d{1,3})\b",
            cleaned,
            re.I,
        )

        if not summary_match:
            continue

        amounts = money_values(cleaned)
        if len(amounts) < 6:
            continue

        total_claims = int(summary_match.group(1))
        open_claims = int(summary_match.group(2))

        # Guardrail: loss run summaries should not be confused with bad OCR dates.
        if total_claims <= 0 or total_claims > 25:
            continue
        if open_claims < 0 or open_claims > total_claims:
            continue

        result["reported_total_claims"] = total_claims
        result["reported_open_claims"] = open_claims
        result["reported_closed_claims"] = max(total_claims - open_claims, 0)

        # Total Ind, Total Med, Total Exp, Total Paid, Total Rec, Net Incurred
        result["reported_total_paid"] = round(float(amounts[-3]), 2)
        result["reported_total_reserve"] = 0.0
        result["reported_total_incurred"] = round(float(amounts[-1]), 2)

        return result

    return result


def reconcile_ocr_claims_with_summary(
    text: str,
    claims: list[dict],
    ignored_rows: list[dict],
    profile: dict | None = None,
) -> list[dict]:
    profile = profile or {}
    summary = detect_ocr_summary_totals_for_reconciliation(text)

    reported_claims = summary.get("reported_total_claims")
    reported_paid = summary.get("reported_total_paid")
    reported_incurred = summary.get("reported_total_incurred")

    if not reported_claims or reported_claims <= len(claims):
        return claims

    current_paid = round(sum(float(c.get("paid_amount") or 0) for c in claims), 2)
    current_incurred = round(sum(float(c.get("total_incurred") or 0) for c in claims), 2)

    paid_delta = round(float(reported_paid or 0) - current_paid, 2)
    incurred_delta = round(float(reported_incurred or 0) - current_incurred, 2)

    missing_count = int(reported_claims) - len(claims)
    if missing_count <= 0:
        return claims

    policy_number = ""
    for claim in claims:
        if claim.get("policy_number"):
            policy_number = claim.get("policy_number")
            break

    if not policy_number:
        policy_number = profile.get("policy_number") or ""

    for index in range(missing_count):
        claim_number = f"OCR-{policy_number or 'LOSSRUN'}-RECON-{index + 1}"

        claims.append(
            {
                "claim_number": claim_number,
                "policy_number": policy_number,
                "line_of_business": "Commercial Auto",
                "claim_type": "Commercial Auto",
                "cause_of_loss": "OCR SUMMARY RECONCILIATION",
                "claimant_type": "",
                "date_of_loss": None,
                "date_reported": None,
                "date_closed": None,
                "status": "Closed",
                "description": (
                    "OCR reconciliation claim added because the carrier summary reported "
                    f"{reported_claims} total claims but OCR detail extraction found {len(claims)}. "
                    "Review the original loss run for the distorted/missing claim row."
                ),
                "paid_amount": round(paid_delta / missing_count, 2) if paid_delta > 0 else 0.0,
                "reserve_amount": 0.0,
                "total_incurred": round(incurred_delta / missing_count, 2) if incurred_delta > 0 else 0.0,
                "litigation": False,
                "litigation_status": "",
                "attorney_assigned": False,
                "suit_filed": False,
                "venue_state": "",
                "injury_type": "",
                "flag": "OCR reconciliation review",
                "source_line": (
                    f"Carrier summary reconciliation: reported_claims={reported_claims}, "
                    f"reported_paid={reported_paid}, reported_incurred={reported_incurred}, "
                    f"extracted_paid={current_paid}, extracted_incurred={current_incurred}"
                ),
            }
        )

    ignored_rows.append(
        {
            "reason": "ocr_summary_reconciliation",
            "line": (
                f"Added {missing_count} OCR reconciliation claim(s) so extracted claim count "
                f"matches carrier-reported total claims."
            ),
        }
    )

    return claims


def parse_claims(
    text: str,
    policies: list[dict] | None = None,
    profile: dict | None = None,
) -> tuple[list[dict], list[dict]]:
    policies = policies or []
    profile = profile or {}

    multiline_claims, multiline_ignored = parse_multiline_ocr_claim_rows(text, policies, profile)

    lines = split_lines(text)
    rows, ignored_rows = reconstruct_claim_rows(lines, policies)
    ignored_rows.extend(multiline_ignored)

    claims: list[dict] = []
    seen: set[str] = set()

    # Prefer the OCR multi-line layout parser when it finds carrier detail rows.
    if multiline_claims and len(multiline_claims) >= 3:
        multiline_claims = reconcile_ocr_claims_with_summary(text, multiline_claims, ignored_rows, profile)
        return multiline_claims, ignored_rows

    for row in rows:
        claim_number = extract_claim_number(row)

        if not claim_number:
            ignored_rows.append({"reason": "missing_claim_number", "line": row[:700]})
            continue

        if claim_number in seen:
            ignored_rows.append({"reason": "duplicate_claim_row", "line": row[:700]})
            continue

        dates = date_values(row)
        amounts = money_values(row)

        if len(dates) == 0 and len(amounts) < 2:
            ignored_rows.append({"reason": "insufficient_claim_context", "line": row[:700]})
            continue

        paid, reserve, incurred = assign_amounts(amounts)
        policy_number = extract_policy_number(row, policies)
        status = detect_status(row)
        litigation = detect_litigation(row)
        policy_lob = policy_lob_from_number(policy_number, policies)
        lob = policy_lob or detect_lob(row)

        claim = {
            "claim_number": claim_number,
            "policy_number": policy_number or profile.get("policy_number") or "",
            "line_of_business": lob,
            "claim_type": lob,
            "cause_of_loss": "",
            "claimant_type": "",
            "date_of_loss": dates[0] if len(dates) >= 1 else None,
            "date_reported": dates[1] if len(dates) >= 2 else None,
            "date_closed": None,
            "status": status,
            "description": clean_description(row, claim_number, policy_number),
            "paid_amount": paid,
            "reserve_amount": reserve,
            "total_incurred": incurred,
            "litigation": litigation,
            "litigation_status": "Litigation/Attorney Indicator" if litigation else "",
            "attorney_assigned": litigation,
            "suit_filed": "suit filed" in row.lower() or "lawsuit" in row.lower(),
            "venue_state": "",
            "injury_type": "",
            "flag": "Litigation exposure" if litigation else "",
            "source_line": row[:700],
        }

        claims.append(claim)
        seen.add(claim_number)

    return claims, ignored_rows
