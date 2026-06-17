import re
import csv
import pandas as pd


# LOSSQ_CARRIER_STYLE_EXCEL_PARSER_V1

def clean_money(value):
    try:
        if value is None or pd.isna(value):
            return 0.0
    except Exception:
        if value is None:
            return 0.0

    cleaned = (
        str(value)
        .replace("$", "")
        .replace(",", "")
        .replace("(", "-")
        .replace(")", "")
        .replace("%", "")
        .strip()
    )

    if cleaned.lower() in {"", "-", "none", "null", "nan"}:
        return 0.0

    try:
        return float(cleaned)
    except Exception:
        return 0.0


def clean_text(value):
    try:
        if value is None or pd.isna(value):
            return ""
    except Exception:
        if value is None:
            return ""

    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "null"}:
        return ""
    return text


def normalize_key(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


ALIASES = {
    "business_name": [
        "businessname", "insured", "insuredname", "namedinsured", "accountname", "companyname",
    ],
    "carrier_name": [
        "carrier", "carriername", "insurancecarrier", "writingcarrier", "insurer",
    ],
    "writing_carrier": [
        "writingcarrier", "carrier", "carriername", "insurancecarrier", "insurer",
    ],
    "agency_name": [
        "agency", "agencyname", "producingagency", "broker", "producer",
    ],
    "account_number": [
        "accountnumber", "account", "customer", "customernumber", "insurednumber",
    ],
    "policy_number": [
        "policynumber", "policyno", "policynum", "policy", "policyid",
    ],
    "policy_type": [
        "policytype", "coverage", "coverageline", "lineofbusiness", "lob", "line",
    ],
    "line_of_business": [
        "lineofbusiness", "lob", "coverage", "coverageline", "policytype", "line", "claimtype",
    ],
    "effective_date": [
        # LOSSQ_XLSX_POLICY_DATE_ALIASES_V1
        "effectivedate", "effective", "effdate", "eff", "inceptiondate",
        "policybegin", "policystart", "policyeffective", "policyeffectivedate",
        "periodstart", "periodfrom", "termstart", "from",
    ],
    "expiration_date": [
        "expirationdate", "expiration", "expdate", "exp", "expirydate",
        "policyend", "policyexpiration", "policyexpirationdate", "policyexpiry",
        "policyexpirydate", "periodend", "periodto", "termend", "to",
    ],
    "evaluation_date": [
        "evaluationdate", "valuationdate", "rundate", "reportdate", "asofdate",
    ],
    "claim_number": [
        "claimnumber", "claimno", "claimnum", "claim", "claimid", "claimidentifier",
    ],
    "date_of_loss": [
        "dateofloss", "dol", "lossdate", "accidentdate", "occurrencedate", "incidentdate",
    ],
    "date_reported": [
        "datereported", "reporteddate", "reportdate", "claimreporteddate",
    ],
    "date_closed": [
        "dateclosed", "closeddate", "closuredate",
    ],
    "status": [
        "status", "claimstatus", "claimstate",
    ],
    "claimant": [
        "claimant", "claimantname", "injuredparty", "thirdparty",
    ],
    "cause_of_loss": [
        "causeofloss", "cause", "losscause", "descriptionofloss", "claimcause",
    ],
    "description": [
        "description", "lossdescription", "claimdescription", "narrative", "notes",
    ],
    "paid_amount": [
        "paidamount", "paid", "losspaid", "totalpaid", "payment", "payments",
    ],
    "reserve_amount": [
        "reserveamount", "reserve", "outstandingreserve", "lossreserve", "reserves", "openreserve",
    ],
    "total_incurred": [
        "totalincurred", "incurred", "totalloss", "total", "grossincurred", "totalclaim",
    ],
    "litigation": [
        "litigation", "litigated", "attorney", "represented", "suitfiled",
    ],
    "flag": [
        "flag", "flagged", "watch", "watchlist", "alert", "severityflag",
    ],
    "state": [
        "state", "jurisdiction", "lossstate",
    ],
}


def row_to_normalized_map(row):
    return {normalize_key(value): index for index, value in enumerate(row) if clean_text(value)}


def find_alias(row_map, field):
    for alias in ALIASES.get(field, []):
        if alias in row_map:
            return row_map[alias]
    return None


def header_score(row):
    row_map = row_to_normalized_map(row)

    score = 0
    for field in [
        "claim_number",
        "policy_number",
        "date_of_loss",
        "status",
        "paid_amount",
        "reserve_amount",
        "total_incurred",
        "line_of_business",
    ]:
        if find_alias(row_map, field) is not None:
            score += 1

    # Claim Number is required for a real claim table.
    if find_alias(row_map, "claim_number") is None:
        return 0

    return score


def find_header_row(raw_df):
    best_index = None
    best_score = 0

    max_scan = min(len(raw_df), 80)

    for index in range(max_scan):
        row = list(raw_df.iloc[index].values)
        score = header_score(row)

        if score > best_score:
            best_score = score
            best_index = index

    if best_index is None or best_score < 3:
        return None

    return best_index


def extract_metadata_from_raw_sheet(raw_df):
    metadata = {}

    field_by_label = {
        "insured": "business_name",
        "business name": "business_name",
        "named insured": "business_name",
        "writing carrier": "writing_carrier",
        "carrier": "carrier_name",
        "producing agency": "agency_name",
        "agency": "agency_name",
        "account number": "account_number",
        "account": "account_number",
        "evaluation date": "evaluation_date",
        "valuation date": "evaluation_date",
        "report date": "evaluation_date",
    }

    rows = raw_df.fillna("").values.tolist()

    for row in rows[:60]:
        for idx, cell in enumerate(row):
            label = str(cell or "").strip().lower()
            if label in field_by_label:
                value = ""
                for next_idx in range(idx + 1, min(idx + 4, len(row))):
                    value = clean_text(row[next_idx])
                    if value:
                        break

                if value:
                    metadata[field_by_label[label]] = value

    return metadata


def get_from_row(row_values, header_map, field, default=None):
    for alias in ALIASES.get(field, []):
        index = header_map.get(alias)
        if index is not None and index < len(row_values):
            value = row_values[index]
            try:
                if pd.notna(value):
                    return value
            except Exception:
                if value is not None:
                    return value

    return default



# LOSSQ_XLSX_POLICY_SCHEDULE_DATE_LOOKUP_V1
def extract_policy_schedule_dates_from_raw_sheet(raw_df):
    schedule = {}
    if raw_df is None or raw_df.empty:
        return schedule

    rows = raw_df.fillna("").values.tolist()
    effective_aliases = {"effectivedate", "effective", "effdate", "eff", "inceptiondate", "policybegin", "policystart", "policyeffective", "policyeffectivedate", "periodstart", "periodfrom", "termstart", "from"}
    expiration_aliases = {"expirationdate", "expiration", "expdate", "exp", "expirydate", "policyend", "policyexpiration", "policyexpirationdate", "policyexpiry", "policyexpirydate", "periodend", "periodto", "termend", "to"}

    for idx, row in enumerate(rows[:120]):
        normalized = [normalize_key(cell) for cell in row]
        has_policy = any(cell in {"policynumber", "policyno", "policy"} for cell in normalized)
        has_effective = any(cell in effective_aliases for cell in normalized)
        has_expiration = any(cell in expiration_aliases for cell in normalized)

        if not (has_policy and (has_effective or has_expiration)):
            continue

        header_map = {key: pos for pos, key in enumerate(normalized) if key}

        def idx_for(candidates):
            for candidate in candidates:
                if candidate in header_map:
                    return header_map[candidate]
            return None

        policy_idx = idx_for(["policynumber", "policyno", "policy"])
        eff_idx = idx_for(list(effective_aliases))
        exp_idx = idx_for(list(expiration_aliases))

        if policy_idx is None:
            continue

        for data_row in rows[idx + 1:]:
            clean_cells = [clean_text(cell) for cell in data_row]
            if not any(clean_cells):
                break

            policy_number = clean_cells[policy_idx] if policy_idx < len(clean_cells) else ""
            if not policy_number or not re.search(r"[A-Z]{2,10}-[A-Z0-9]+-\d{4}-[A-Z0-9]+", policy_number.upper()):
                continue

            effective = clean_cells[eff_idx] if eff_idx is not None and eff_idx < len(clean_cells) else ""
            expiration = clean_cells[exp_idx] if exp_idx is not None and exp_idx < len(clean_cells) else ""

            schedule[policy_number.upper()] = {
                "effective_date": effective,
                "expiration_date": expiration,
            }

    return schedule

def parse_raw_sheet(raw_df):
    if raw_df is None or raw_df.empty:
        return []

    header_index = find_header_row(raw_df)
    if header_index is None:
        return []

    metadata = extract_metadata_from_raw_sheet(raw_df)
    policy_schedule_dates = extract_policy_schedule_dates_from_raw_sheet(raw_df)

    headers = list(raw_df.iloc[header_index].values)
    header_map = row_to_normalized_map(headers)

    claims = []
    seen = set()

    for row_index in range(header_index + 1, len(raw_df)):
        row_values = list(raw_df.iloc[row_index].values)

        claim_number = clean_text(get_from_row(row_values, header_map, "claim_number", ""))

        if not claim_number:
            continue

        # Skip subtotal/header-like rows.
        lowered_claim = claim_number.lower()
        if lowered_claim in {"claim number", "claim #", "claim no", "total", "subtotal"}:
            continue

        policy_number = clean_text(get_from_row(row_values, header_map, "policy_number", ""))
        date_of_loss = clean_text(get_from_row(row_values, header_map, "date_of_loss", ""))

        paid = clean_money(get_from_row(row_values, header_map, "paid_amount", 0))
        reserve = clean_money(get_from_row(row_values, header_map, "reserve_amount", 0))
        total = clean_money(get_from_row(row_values, header_map, "total_incurred", paid + reserve))

        if total == 0 and (paid or reserve):
            total = paid + reserve

        line = clean_text(get_from_row(row_values, header_map, "line_of_business", "")) or clean_text(
            get_from_row(row_values, header_map, "policy_type", "")
        ) or "Unknown"

        description = clean_text(get_from_row(row_values, header_map, "description", ""))
        cause = clean_text(get_from_row(row_values, header_map, "cause_of_loss", ""))

        row_text = " ".join(clean_text(v) for v in row_values).lower()
        litigation_raw = clean_text(get_from_row(row_values, header_map, "litigation", ""))
        litigation = litigation_raw.lower() in {"yes", "y", "true", "1", "litigated", "litigation"} or any(
            word in row_text for word in ["attorney", "litigation", "lawsuit", "counsel", "suit filed", "represented"]
        )

        flag = clean_text(get_from_row(row_values, header_map, "flag", ""))
        if litigation:
            flag = "Litigation exposure" if not flag else f"{flag} | Litigation exposure"

        business_name = clean_text(get_from_row(row_values, header_map, "business_name", "")) or metadata.get("business_name", "")
        carrier_name = clean_text(get_from_row(row_values, header_map, "carrier_name", "")) or metadata.get("carrier_name", "") or metadata.get("writing_carrier", "")
        writing_carrier = clean_text(get_from_row(row_values, header_map, "writing_carrier", "")) or metadata.get("writing_carrier", "") or carrier_name
        agency_name = clean_text(get_from_row(row_values, header_map, "agency_name", "")) or metadata.get("agency_name", "")
        account_number = clean_text(get_from_row(row_values, header_map, "account_number", "")) or metadata.get("account_number", "")

        unique_key = f"{claim_number.upper()}|{policy_number.upper()}|{date_of_loss.upper()}|{total:.2f}"
        if unique_key in seen:
            continue

        seen.add(unique_key)

        claims.append(
            {
                "business_name": business_name,
                "carrier_name": carrier_name,
                "writing_carrier": writing_carrier or carrier_name,
                "agency_name": agency_name,
                "account_number": account_number,
                "customer_number": account_number,
                "policy_number": policy_number,
                "policy_type": clean_text(get_from_row(row_values, header_map, "policy_type", "")) or line,
                "line_of_business": line,
                "claim_type": line,
                "effective_date": clean_text(get_from_row(row_values, header_map, "effective_date", "")),
                "expiration_date": clean_text(get_from_row(row_values, header_map, "expiration_date", "")),
                "evaluation_date": clean_text(get_from_row(row_values, header_map, "evaluation_date", "")) or metadata.get("evaluation_date", ""),
                "claim_number": claim_number,
                "date_of_loss": date_of_loss,
                "date_reported": clean_text(get_from_row(row_values, header_map, "date_reported", "")),
                "date_closed": clean_text(get_from_row(row_values, header_map, "date_closed", "")),
                "status": clean_text(get_from_row(row_values, header_map, "status", "")) or "Open",
                "claimant": clean_text(get_from_row(row_values, header_map, "claimant", "")),
                "cause_of_loss": cause or description or "Needs Review",
                "description": description or cause or "Needs Review",
                "paid_amount": paid,
                "reserve_amount": reserve,
                "total_incurred": total,
                "litigation": litigation,
                "suit_filed": litigation,
                "flag": flag,
                "state": clean_text(get_from_row(row_values, header_map, "state", "")),
                "source": "excel_or_csv",
            }
        )

    return claims




# LOSSQ_RAGGED_SECTION_CSV_READER_V1
def lossq_read_ragged_csv(file_path):
    """
    Reads section-based / ragged CSV files where different rows have different
    column counts. This prevents pandas ParserError on loss-run worksheets with
    account sections, policy schedule tables, exposure inputs, claim detail tables,
    and summaries in one CSV.
    """
    rows = []

    encodings = ["utf-8-sig", "utf-8", "latin-1"]

    last_error = None
    for encoding in encodings:
        try:
            with open(file_path, "r", newline="", encoding=encoding) as f:
                reader = csv.reader(f)
                rows = [list(row) for row in reader]
            break
        except Exception as exc:
            last_error = exc
            rows = []

    if not rows and last_error:
        raise last_error

    max_cols = max((len(row) for row in rows), default=0)

    normalized_rows = []
    for row in rows:
        clean_row = ["" if value is None else value for value in row]
        if len(clean_row) < max_cols:
            clean_row = clean_row + [""] * (max_cols - len(clean_row))
        normalized_rows.append(clean_row)

    return pd.DataFrame(normalized_rows, dtype=object)


def parse_claims_from_excel(file_path):
    all_claims = []
    lower = str(file_path or "").lower()

    if lower.endswith(".csv"):
        raw_df = lossq_read_ragged_csv(file_path)
        all_claims.extend(parse_raw_sheet(raw_df))
    else:
        sheets = pd.read_excel(file_path, sheet_name=None, header=None, dtype=object)

        for _, raw_df in sheets.items():
            sheet_claims = parse_raw_sheet(raw_df)
            all_claims.extend(sheet_claims)

    # Global dedupe across sheets.
    final = []
    seen = set()

    for claim in all_claims:
        key = (
            clean_text(claim.get("claim_number")).upper(),
            clean_text(claim.get("policy_number")).upper(),
            clean_text(claim.get("date_of_loss")).upper(),
            clean_money(claim.get("total_incurred")),
        )

        if key in seen:
            continue

        seen.add(key)
        final.append(claim)

    return final






