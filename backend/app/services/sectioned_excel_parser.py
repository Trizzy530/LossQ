from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any


# LOSSQ_SECTIONED_EXCEL_LOSS_RUN_SERVICE_V1
def lossq_sectioned_excel_loss_run_repair_v1(
    file_path: str,
    parsed_claims: list[dict[str, Any]] | None = None,
    parsed_profile: dict[str, Any] | None = None,
    direct_profile: dict[str, Any] | None = None,
):
    """
    Universal sectioned Excel loss run parser.

    Purpose:
    - Handles XLSX/XLSM files with label/value account rows, exposure rows,
      and a Claims Detail table.
    - Supports English/French bilingual labels.
    - Does not hardcode a customer, carrier, policy, or file name.
    - Returns stronger claims/profile only when the uploaded workbook contains
      a recognizable sectioned loss-run structure.
    """

    parsed_claims = parsed_claims if isinstance(parsed_claims, list) else []
    parsed_profile = parsed_profile if isinstance(parsed_profile, dict) else {}
    direct_profile = direct_profile if isinstance(direct_profile, dict) else {}

    lower_path = str(file_path or "").lower()
    if not lower_path.endswith((".xlsx", ".xlsm")):
        return parsed_claims, parsed_profile, direct_profile

    def clean(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (datetime, date)):
            return value.strftime("%Y-%m-%d")
        return re.sub(r"\s+", " ", str(value).replace("\ufeff", "").strip()).strip(" :-|/")

    def key(value: Any) -> str:
        return re.sub(r"[^a-z0-9À-ÿ]+", " ", clean(value).lower()).strip()

    def money_float(value: Any) -> float:
        raw = clean(value)
        if not raw or raw in {"—", "-", "N/A", "n/a"}:
            return 0.0

        negative = raw.startswith("(") and raw.endswith(")")
        raw = re.sub(r"[^0-9.\-]", "", raw)

        try:
            amount = float(raw or 0)
            return -amount if negative else amount
        except Exception:
            return 0.0

    def money_text(value: Any) -> str:
        amount = money_float(value)
        if amount == int(amount):
            return str(int(amount))
        return str(amount)

    def normalize_status(value: Any) -> str:
        raw = clean(value).lower()
        if "open" in raw or "ouvert" in raw or "ouverte" in raw:
            return "Open"
        if "closed" in raw or "fermé" in raw or "fermee" in raw or "clos" in raw or "clôturé" in raw:
            return "Closed"
        return clean(value)

    def parse_province(value: Any):
        raw = clean(value)
        compact = re.sub(r"[^a-z0-9À-ÿ]+", "", raw.lower())

        provinces = {
            "alberta": ("AB", "Alberta", "Alberta Superintendent of Insurance"),
            "ab": ("AB", "Alberta", "Alberta Superintendent of Insurance"),
            "britishcolumbia": ("BC", "British Columbia", "BCFSA"),
            "bc": ("BC", "British Columbia", "BCFSA"),
            "manitoba": ("MB", "Manitoba", "FIRB"),
            "mb": ("MB", "Manitoba", "FIRB"),
            "newbrunswick": ("NB", "New Brunswick", "FCNB"),
            "nb": ("NB", "New Brunswick", "FCNB"),
            "newfoundlandandlabrador": ("NL", "Newfoundland and Labrador", "Digital Government and Service NL"),
            "nl": ("NL", "Newfoundland and Labrador", "Digital Government and Service NL"),
            "novascotia": ("NS", "Nova Scotia", "Nova Scotia Office of the Superintendent of Insurance"),
            "ns": ("NS", "Nova Scotia", "Nova Scotia Office of the Superintendent of Insurance"),
            "northwestterritories": ("NT", "Northwest Territories", "Northwest Territories Superintendent of Insurance"),
            "nt": ("NT", "Northwest Territories", "Northwest Territories Superintendent of Insurance"),
            "nunavut": ("NU", "Nunavut", "Nunavut Superintendent of Insurance"),
            "nu": ("NU", "Nunavut", "Nunavut Superintendent of Insurance"),
            "ontario": ("ON", "Ontario", "FSRA"),
            "on": ("ON", "Ontario", "FSRA"),
            "princeedwardisland": ("PE", "Prince Edward Island", "PEI Superintendent of Insurance"),
            "pei": ("PE", "Prince Edward Island", "PEI Superintendent of Insurance"),
            "pe": ("PE", "Prince Edward Island", "PEI Superintendent of Insurance"),
            "quebec": ("QC", "Québec", "AMF"),
            "québec": ("QC", "Québec", "AMF"),
            "qc": ("QC", "Québec", "AMF"),
            "saskatchewan": ("SK", "Saskatchewan", "Saskatchewan Superintendent of Insurance"),
            "sk": ("SK", "Saskatchewan", "Saskatchewan Superintendent of Insurance"),
            "yukon": ("YT", "Yukon", "Yukon Superintendent of Insurance"),
            "yt": ("YT", "Yukon", "Yukon Superintendent of Insurance"),
        }

        return provinces.get(compact, ("", raw, ""))

    def parse_period(value: Any):
        raw = clean(value)
        match = re.search(
            r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\s*(?:au|to|through|thru|-|–)\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
            raw,
            flags=re.I,
        )
        if not match:
            return "", ""
        return clean(match.group(1)), clean(match.group(2))

    def looks_like_claim_number(value: Any) -> bool:
        raw = clean(value).upper()
        if not raw or raw in {"TOTAL", "N/A", "NA", "-", "—"}:
            return False
        return bool(re.search(r"[A-Z]{1,8}[-_]\d{2,}", raw) or re.search(r"\d{4,}", raw))

    try:
        from openpyxl import load_workbook

        workbook = load_workbook(file_path, data_only=True)
    except Exception as exc:
        print("LOSSQ_SECTIONED_EXCEL_LOSS_RUN_SERVICE_READ_ERROR_V1:", str(exc)[:200])
        return parsed_claims, parsed_profile, direct_profile

    all_rows: list[list[str]] = []

    for sheet in workbook.worksheets:
        for row in sheet.iter_rows(values_only=True):
            values = [clean(cell) for cell in row]
            if any(values):
                all_rows.append(values)

    if not all_rows:
        return parsed_claims, parsed_profile, direct_profile

    first_text = "\n".join(" ".join(row) for row in all_rows[:35])

    if not re.search(r"(?i)(claims detail|détail des sinistres|detail des sinistres|sinistre|claim #)", first_text):
        return parsed_claims, parsed_profile, direct_profile

    carrier = ""
    business_name = ""
    policy_number = ""
    province_code = ""
    province_name = ""
    regulator = ""
    currency = ""
    line_of_business = ""
    effective_date = ""
    expiration_date = ""
    evaluation_date = ""

    for row in all_rows[:12]:
        line = clean(" ".join(cell for cell in row if cell))
        if re.search(r"(?i)\b(insurance|assurance|assurances|mutual|casualty|indemnity|underwriters|general insurance)\b", line):
            if not re.search(r"(?i)\b(loss run|relevé des sinistres|releve des sinistres|claims detail)\b", line):
                carrier = line
                break

    for row in all_rows:
        label = key(row[0] if len(row) > 0 else "")
        value = clean(row[1] if len(row) > 1 else "")

        if not label or not value:
            continue

        if not business_name and re.search(r"(assuré|assure|insured|named insured)", label):
            business_name = value
            continue

        if not policy_number and re.search(r"(policy|police)", label):
            policy_number = value
            continue

        if not province_code and re.search(r"(province|state)", label):
            province_code, province_name, regulator = parse_province(value)
            continue

        if not currency and re.search(r"(currency|devise)", label):
            currency = value.upper()
            continue

        if not line_of_business and re.search(r"(ibc|bac|line of business|ligne)", label):
            line_of_business = value
            continue

        if not evaluation_date and re.search(r"(report date|date du rapport|valuation|evaluation|évaluation)", label):
            evaluation_date = value
            continue

        if re.search(r"(period|période|periode)", label):
            start, end = parse_period(value)
            effective_date = effective_date or start
            expiration_date = expiration_date or end
            continue

    if not carrier:
        for row in all_rows[-8:]:
            line = clean(" ".join(cell for cell in row if cell))
            match = re.search(r"(?i)(préparé par|prepare par|prepared by)\s*[:#-]\s*(.+)$", line)
            if match:
                carrier = re.sub(r"(?i)\s+[–-]\s+(lignes commerciales|commercial lines).*$", "", clean(match.group(2))).strip()
                break

    header_index = None
    headers: list[str] = []

    for index, row in enumerate(all_rows):
        joined = " ".join(row)
        if re.search(r"(?i)(claim #|sinistre)", joined) and re.search(r"(?i)(loss date|date sinistre|reported|déclaration|declaration|incurred|engagé|engage)", joined):
            header_index = index
            headers = row
            break

    claims: list[dict[str, Any]] = []

    if header_index is not None and headers:
        normalized_headers = [key(item) for item in headers]

        def col(*patterns: str) -> int:
            for idx, item in enumerate(normalized_headers):
                for pattern in patterns:
                    if re.search(pattern, item, flags=re.I):
                        return idx
            return -1

        c_claim = col(r"claim", r"sinistre")
        c_loss = col(r"loss date", r"date sinistre")
        c_report = col(r"reported", r"déclaration", r"declaration")
        c_claimant = col(r"claimant", r"réclamant", r"reclamant")
        c_desc = col(r"description")
        c_cov = col(r"coverage", r"couverture")
        c_status = col(r"status", r"statut")
        c_paid = col(r"paid", r"payé", r"paye")
        c_reserve = col(r"reserve", r"réserve")
        c_incurred = col(r"incurred", r"engagé", r"engage")

        for row in all_rows[header_index + 1 :]:
            if not any(row):
                continue

            if clean(row[0] if row else "").upper() == "TOTAL":
                continue

            joined = " ".join(row)
            if re.search(r"(?i)(notes|remarques|prepared by|préparé par|confidential|confidentiel)", joined):
                break

            claim_number = clean(row[c_claim]) if 0 <= c_claim < len(row) else ""

            if not looks_like_claim_number(claim_number):
                continue

            paid = money_text(row[c_paid]) if 0 <= c_paid < len(row) else "0"
            reserve = money_text(row[c_reserve]) if 0 <= c_reserve < len(row) else "0"
            incurred = money_text(row[c_incurred]) if 0 <= c_incurred < len(row) else ""

            if not incurred:
                incurred = money_text(money_float(paid) + money_float(reserve))

            coverage = clean(row[c_cov]) if 0 <= c_cov < len(row) else line_of_business

            claims.append({
                "claim_number": claim_number,
                "policy_number": policy_number,
                "line_of_business": coverage or line_of_business,
                "coverage": coverage or line_of_business,
                "loss_date": clean(row[c_loss]) if 0 <= c_loss < len(row) else "",
                "reported_date": clean(row[c_report]) if 0 <= c_report < len(row) else "",
                "claimant": clean(row[c_claimant]) if 0 <= c_claimant < len(row) else "",
                "description": clean(row[c_desc]) if 0 <= c_desc < len(row) else "",
                "status": normalize_status(row[c_status]) if 0 <= c_status < len(row) else "",
                "paid": paid,
                "paid_amount": paid,
                "reserve": reserve,
                "reserve_amount": reserve,
                "total_incurred": incurred,
                "incurred": incurred,
                "currency": currency,
                "state": province_code,
                "province": province_name or province_code,
                "carrier_name": carrier,
                "writing_carrier": carrier,
                "source_parser": "sectioned_excel_loss_run_service",
            })

    real_existing = [
        claim for claim in parsed_claims
        if isinstance(claim, dict) and looks_like_claim_number(claim.get("claim_number") or claim.get("claim_no"))
    ]

    if claims and len(claims) >= len(real_existing):
        parsed_claims = claims

    coverage_claim_counts: dict[str, int] = {}
    coverage_totals: dict[str, float] = {}

    for claim in parsed_claims:
        if not isinstance(claim, dict):
            continue
        cov = clean(claim.get("coverage") or claim.get("line_of_business") or line_of_business) or "Policy"
        coverage_claim_counts[cov] = coverage_claim_counts.get(cov, 0) + 1
        coverage_totals[cov] = coverage_totals.get(cov, 0.0) + money_float(claim.get("total_incurred") or claim.get("incurred"))

    policy_rows = []

    in_exposure = False
    exposure_header_seen = False

    for row in all_rows:
        joined = " ".join(row)

        if re.search(r"(?i)(exposure data|données d'exposition|donnees d exposition)", joined):
            in_exposure = True
            continue

        if in_exposure and re.search(r"(?i)(claims detail|détail des sinistres|detail des sinistres)", joined):
            break

        if not in_exposure:
            continue

        if re.search(r"(?i)(category|catégorie|categorie)", joined):
            exposure_header_seen = True
            continue

        if not exposure_header_seen:
            continue

        coverage_name = clean(row[0] if row else "")

        if not coverage_name or coverage_name.upper() == "TOTAL":
            continue

        if re.search(r"(?i)(included|inclus)", coverage_name):
            continue

        matching_claims = 0
        matching_total = 0.0

        for cov, count in coverage_claim_counts.items():
            if coverage_name.lower().find(cov.lower()) >= 0 or cov.lower().find(coverage_name.lower()) >= 0:
                matching_claims += count
                matching_total += coverage_totals.get(cov, 0.0)

        if not matching_claims:
            if re.search(r"(?i)d&o|directors|administrateurs", coverage_name):
                for cov, count in coverage_claim_counts.items():
                    if re.search(r"(?i)d&o|directors|administrateurs", cov):
                        matching_claims += count
                        matching_total += coverage_totals.get(cov, 0.0)

            if re.search(r"(?i)e&o|professional|professionnelle|erreurs|omissions", coverage_name):
                for cov, count in coverage_claim_counts.items():
                    if re.search(r"(?i)e&o|professional|professionnelle|erreurs|omissions", cov):
                        matching_claims += count
                        matching_total += coverage_totals.get(cov, 0.0)

        numeric_values = [clean(cell) for cell in row[1:] if clean(cell) and re.search(r"\d", clean(cell))]
        premium = numeric_values[-1] if numeric_values else ""

        policy_rows.append({
            "policy_number": policy_number,
            "policyNumber": policy_number,
            "line_of_business": coverage_name,
            "lineOfBusiness": coverage_name,
            "policy_type": coverage_name,
            "policyType": coverage_name,
            "coverage": coverage_name,
            "carrier": carrier,
            "carrier_name": carrier,
            "carrierName": carrier,
            "writing_carrier": carrier,
            "writingCarrier": carrier,
            "effective_date": effective_date,
            "effectiveDate": effective_date,
            "effective": effective_date,
            "expiration_date": expiration_date,
            "expirationDate": expiration_date,
            "expiration": expiration_date,
            "evaluation_date": evaluation_date,
            "evaluationDate": evaluation_date,
            "state": province_code,
            "stateProvince": province_code,
            "province": province_name or province_code,
            "province_code": province_code,
            "currency": currency,
            "premium": premium,
            "claims": matching_claims,
            "claim_count": matching_claims,
            "total_incurred": matching_total,
        })

    if not policy_rows and policy_number:
        total_incurred = sum(money_float(claim.get("total_incurred")) for claim in parsed_claims if isinstance(claim, dict))
        policy_rows = [{
            "policy_number": policy_number,
            "policyNumber": policy_number,
            "line_of_business": line_of_business,
            "lineOfBusiness": line_of_business,
            "policy_type": line_of_business,
            "policyType": line_of_business,
            "coverage": line_of_business,
            "carrier": carrier,
            "carrier_name": carrier,
            "carrierName": carrier,
            "writing_carrier": carrier,
            "writingCarrier": carrier,
            "effective_date": effective_date,
            "effectiveDate": effective_date,
            "expiration_date": expiration_date,
            "expirationDate": expiration_date,
            "evaluation_date": evaluation_date,
            "evaluationDate": evaluation_date,
            "state": province_code,
            "stateProvince": province_code,
            "province": province_name or province_code,
            "province_code": province_code,
            "currency": currency,
            "claims": len(parsed_claims),
            "claim_count": len(parsed_claims),
            "total_incurred": total_incurred,
        }]

    is_canada = bool(province_code or currency == "CAD" or re.search(r"(?i)canada|cad|québec|quebec|ontario|manitoba|ibc|bac", first_text))

    def apply_profile(target: dict[str, Any]):
        if not isinstance(target, dict):
            return

        if business_name:
            target["business_name"] = business_name
            target["insured_name"] = business_name
            target["insured"] = business_name
            target["company_name"] = business_name
            target["account_name"] = business_name

        if carrier:
            target["carrier_name"] = carrier
            target["carrierName"] = carrier
            target["carrier"] = carrier
            target["writing_carrier"] = carrier
            target["writingCarrier"] = carrier
            target["document_writing_carrier"] = carrier
            target["documentWritingCarrier"] = carrier
            target["uploaded_writing_carrier"] = carrier
            target["uploadedWritingCarrier"] = carrier

        if policy_number:
            target["policy_number"] = policy_number
            target["policyNumber"] = policy_number
            target["main_policy_number"] = policy_number
            target["mainPolicyNumber"] = policy_number

        if line_of_business:
            target["line_of_business"] = line_of_business
            target["lineOfBusiness"] = line_of_business
            target["policy_type"] = line_of_business
            target["policyType"] = line_of_business

        if effective_date:
            target["effective_date"] = effective_date
            target["effectiveDate"] = effective_date
            target["effective"] = effective_date

        if expiration_date:
            target["expiration_date"] = expiration_date
            target["expirationDate"] = expiration_date
            target["expiration"] = expiration_date

        if evaluation_date:
            target["evaluation_date"] = evaluation_date
            target["evaluationDate"] = evaluation_date
            target["valuation_date"] = evaluation_date
            target["valuationDate"] = evaluation_date
            target["report_date"] = evaluation_date
            target["reportDate"] = evaluation_date

        if currency:
            target["currency"] = currency
            target["default_currency"] = currency
            target["defaultCurrency"] = currency

        if province_code:
            target["state"] = province_code
            target["primary_state"] = province_code
            target["primaryState"] = province_code
            target["state_province"] = province_code
            target["stateProvince"] = province_code
            target["province_code"] = province_code
            target["provinceCode"] = province_code
            target["province"] = province_name or province_code
            target["province_name"] = province_name or province_code
            target["provinceName"] = province_name or province_code

        if is_canada:
            target["country"] = "Canada"
            target["market"] = "Canada"
            target["country_market"] = "Canada"
            target["countryMarket"] = "Canada"
            target["market_country"] = "Canada"
            target["marketCountry"] = "Canada"
            target["date_format"] = "DD/MM/YYYY"
            target["dateFormat"] = "DD/MM/YYYY"
            target["market_date_format"] = "DD/MM/YYYY"
            target["marketDateFormat"] = "DD/MM/YYYY"

        if regulator:
            target["regulator"] = regulator
            target["insurance_regulator"] = regulator
            target["insuranceRegulator"] = regulator
            target["market_regulator"] = regulator
            target["marketRegulator"] = regulator

        market_context = target.get("market_context") or target.get("marketContext")
        if not isinstance(market_context, dict):
            market_context = {}

        if is_canada:
            market_context["country"] = "Canada"
            market_context["market"] = "Canada"
            market_context["date_format"] = "DD/MM/YYYY"
            market_context["dateFormat"] = "DD/MM/YYYY"

        if province_code:
            market_context["state"] = province_code
            market_context["state_province"] = province_code
            market_context["stateProvince"] = province_code
            market_context["province"] = province_code
            market_context["province_code"] = province_code
            market_context["provinceCode"] = province_code
            market_context["province_name"] = province_name or province_code

        if currency:
            market_context["currency"] = currency

        if regulator:
            market_context["regulator"] = regulator

        target["market_context"] = market_context
        target["marketContext"] = market_context

        if policy_rows:
            target["policies"] = policy_rows
            target["policy_schedule"] = policy_rows
            target["policySchedule"] = policy_rows

        if parsed_claims:
            target["claims"] = parsed_claims
            target["parsed_claims"] = parsed_claims

    apply_profile(parsed_profile)
    apply_profile(direct_profile)

    print("LOSSQ_SECTIONED_EXCEL_LOSS_RUN_SERVICE_V1:", {
        "business_name": business_name,
        "carrier": carrier,
        "policy_number": policy_number,
        "province": province_code,
        "currency": currency,
        "effective_date": effective_date,
        "expiration_date": expiration_date,
        "evaluation_date": evaluation_date,
        "claims": len(parsed_claims),
        "policy_rows": len(policy_rows),
    })

    return parsed_claims, parsed_profile, direct_profile
