"""Conservative layout-aware reader for reconciled, split-table US loss runs.

No carrier names, claim prefixes or sample identifiers are hard-coded. Unrecognized
layouts return None; recognized but inconsistent documents require review.
"""
from datetime import datetime
from decimal import Decimal
import re


class StructuredPDFError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise StructuredPDFError(message)


def _cells(line):
    return re.split(r"\s{2,}", line.strip())


def _key(value):
    return re.sub(r"[^a-z0-9]", "", value.lower())


HEADERS = {
    "account": ("namedinsured", "accountnumber", "producingagency", "domicile"),
    "policy": ("policynumber", "coverage", "effective", "expiration", "annualpremium", "exposurebasis", "exposure"),
    "financial": ("claimnumber", "policynumber", "lob", "lossdate", "status", "paid", "reserve", "totalincurred"),
    "admin": ("claimnumber", "claimant", "jur", "reported", "closed", "adjuster", "litigation", "description"),
}


def _date(value):
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    raise StructuredPDFError("Invalid or ambiguous date in structured loss run.")


def _amount(value):
    value = value.strip().replace("$", "").replace(",", "")
    _require(bool(re.fullmatch(r"-?\d+(?:\.\d{1,2})?", value)), "Missing or invalid financial value.")
    return Decimal(value)


def _identifier(value):
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9./_-]{3,79}", value) and re.search(r"\d", value))


def _columns(header, row):
    # Layout extraction keeps blank cells; header positions distinguish a blank
    # closure date from the next adjuster column.
    starts = [m.start() for m in re.finditer(r"\S(?:.*?\S)?(?=\s{2,}|$)", header)]
    bounds = [0] + [max(0, x - 2) for x in starts[1:]] + [len(row)]
    return [row[a:b].strip() for a, b in zip(bounds, bounds[1:])]


def parse_reconciled_layout(text):
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    positions = {}
    for i, line in enumerate(lines):
        keys = tuple(_key(cell) for cell in _cells(line))
        for section, header in HEADERS.items():
            if keys == header:
                positions.setdefault(section, []).append(i)

    if not all(section in positions for section in HEADERS):
        return None
    # Deliberately scope to explicit US/USD documents; other markets and
    # multi-page/repeated header layouts remain on the existing parser.
    if not re.search(r"\bUnited States\b", text, re.I) or not re.search(r"\bUSD\b", text):
        return None
    if any(len(indices) != 1 for indices in positions.values()):
        return None
    a, p, f, d = (positions[k][0] for k in ("account", "policy", "financial", "admin"))
    if not a < p < f < d:
        return None

    account = _cells(lines[a + 1])
    _require(len(account) == 4, "Account table does not align with its headers.")
    insured, account_number, agency, domicile = account
    _require(_identifier(account_number) and bool(insured and agency), "Account identity is incomplete.")
    state = re.fullmatch(r"([A-Z]{2}),\s*United States", domicile, re.I)
    _require(state is not None, "Account domicile is incomplete.")
    # Carrier must be on the same source line as the explicit valuation label,
    # never inferred from the document title.
    carrier = evaluation = ""
    for line in lines[:a]:
        match = re.fullmatch(r"\s*(.+?)\s*\|\s*(?:valuation|evaluation|as of)\s*date\s*:\s*([^|]+)\|\s*USD\s*", line, re.I)
        if match:
            carrier = re.sub(r"\s*\(fictional\)\s*$", "", match[1], flags=re.I).strip()
            evaluation = _date(match[2].strip())
            break
    _require(bool(carrier and evaluation), "Carrier or valuation date could not be verified.")

    policies = {}
    exposures = {}
    exposure_fields = {
        "annualrevenue": "revenue", "revenue": "revenue", "sales": "sales",
        "payroll": "payroll", "vehicles": "vehicle_count", "vehiclecount": "vehicle_count",
        "propertytiv": "property_tiv", "equipmenttiv": "equipment_tiv",
    }
    for line in lines[p + 1:f]:
        row = _cells(line)
        if len(row) == 1 and not _identifier(row[0]):
            continue  # section caption
        _require(len(row) == 7 and _identifier(row[0]), "Policy row is incomplete.")
        number, lob, effective, expiration, premium, basis, exposure = row
        number = number.upper()
        _require(number not in policies and number != account_number.upper() and bool(lob), "Duplicate or invalid policy identity.")
        effective, expiration = _date(effective), _date(expiration)
        _require(effective < expiration, "Invalid policy period.")
        premium, exposure = _amount(premium), _amount(exposure)
        policies[number] = {
            "policy_number": number, "line_of_business": lob, "coverage": lob,
            "carrier_name": carrier, "carrier": carrier, "writing_carrier": carrier,
            "effective_date": effective, "expiration_date": expiration,
            "evaluation_date": evaluation, "premium": float(premium),
            "annual_premium": float(premium), "exposure_basis": basis,
            "exposure_value": float(exposure), "claim_count": 0, "total_incurred": 0.0,
        }
        field = exposure_fields.get(_key(basis))
        if _key(basis) == "limit" and "umbrella" in lob.lower():
            field = "umbrella_limit"
        if field:
            _require(field not in exposures, "Repeated exposure basis requires review.")
            exposures[field] = str(exposure)
    _require(bool(policies), "No verified policies.")

    claims = {}
    reported = None
    for line in lines[f + 1:d]:
        row = _cells(line)
        if row[0].upper() == "TOTAL":
            _require(reported is None and len(row) == 4, "Invalid document total.")
            reported = tuple(_amount(x) for x in row[1:])
            continue
        if len(row) == 1 and not _identifier(row[0]):
            continue
        _require(reported is None and len(row) == 8, "Incomplete claim financial row.")
        number, policy, lob, loss_date, status, paid, reserve, incurred = row
        number, policy = number.upper(), policy.upper()
        _require(_identifier(number) and number not in policies and number not in claims and policy in policies, "Invalid claim or policy identity.")
        _require(status.lower() in ("open", "closed"), "Unknown claim status.")
        paid, reserve, incurred = map(_amount, (paid, reserve, incurred))
        _require(paid + reserve == incurred, "Claim financial amounts do not reconcile.")
        coverage = policies[policy]["line_of_business"]
        claims[number] = {
            "claim_number": number, "policy_number": policy,
            "line_of_business": coverage, "claim_type": coverage,
            "date_of_loss": _date(loss_date), "status": status.title(),
            "paid_amount": float(paid), "reserve_amount": float(reserve),
            "total_incurred": float(incurred),
        }
    _require(bool(claims) and reported is not None, "Claim financial table or reported totals missing.")
    calculated = tuple(sum((Decimal(str(c[key])) for c in claims.values()), Decimal(0))
                       for key in ("paid_amount", "reserve_amount", "total_incurred"))
    _require(calculated == reported, "Extracted paid, reserve or incurred does not match document totals.")

    seen = set()
    for line in lines[d + 1:]:
        first = _cells(line)[0]
        if first.upper() not in claims:
            # Stop at prose/footer, but reject orphan administration rows.
            _require(not _identifier(first), "Administration row has no financial claim.")
            break
        row = _cells(line)
        if len(row) != 8:
            row = _columns(lines[d], line)
        _require(len(row) == 8, "Administration row does not align with headers.")
        number, claimant, jurisdiction, reported_date, closed_date, adjuster, litigation, description = row
        number = number.upper()
        _require(number in claims and number not in seen and bool(claimant and adjuster and description), "Incomplete or duplicate administration row.")
        _require(bool(re.fullmatch(r"[A-Z]{2}", jurisdiction)) and litigation.lower() in ("yes", "no"), "Invalid jurisdiction or litigation indicator.")
        claim = claims[number]
        _require(bool(closed_date) == (claim["status"] == "Closed"), "Claim status and closure date disagree.")
        claim.update(
            claimant=claimant, jurisdiction_state=jurisdiction, adjuster=adjuster, examiner=adjuster,
            date_reported=_date(reported_date), date_closed=_date(closed_date) if closed_date else None,
            litigation=litigation.lower() == "yes", description=description,
            litigation_status="Litigation" if litigation.lower() == "yes" else "",
            flag="Litigation exposure" if litigation.lower() == "yes" else "",
        )
        seen.add(number)
    _require(seen == set(claims), "Administration table is missing claims.")

    for policy in policies.values():
        rows = [c for c in claims.values() if c["policy_number"] == policy["policy_number"]]
        policy["claim_count"] = len(rows)
        policy["total_incurred"] = float(sum((Decimal(str(c["total_incurred"])) for c in rows), Decimal(0)))
    first = next(iter(policies.values()))
    premium_total = sum(Decimal(str(p["premium"])) for p in policies.values())
    profile = {
        "business_name": insured, "insured_name": insured, "named_insured": insured,
        "carrier_name": carrier, "carrier": carrier, "writing_carrier": carrier,
        "agency_name": agency, "producing_agency": agency,
        "account_number": account_number, "customer_number": account_number,
        "policy_number": first["policy_number"], "main_policy": first["policy_number"],
        "effective_date": first["effective_date"], "expiration_date": first["expiration_date"],
        "evaluation_date": evaluation, "state": state[1].upper(),
        "country": "United States", "currency": "USD",
        "policies": list(policies.values()), "policy_numbers": list(policies),
        "current_premium": str(premium_total), "exposure_inputs": exposures.copy(),
        "exposure_basis": " | ".join(f'{p["exposure_basis"]}: {p["exposure_value"]}' for p in policies.values()),
        "raw_text_preview": text[:2500],
        "validation": {
            "claim_count": len(claims), "policy_count": len(policies),
            "reported_totals": {"reported_total_paid": float(reported[0]),
                                "reported_total_reserve": float(reported[1]),
                                "reported_total_incurred": float(reported[2])},
            "calculated_total_incurred": float(calculated[2]),
            "extraction_quality": {"status": "passed", "critical_issues": []},
            "structured_pdf_reconciled": True, "structured_reconciled": True,
            "market_country": "United States", "market_currency": "USD",
            "listed_policy_premium_total": float(premium_total),
        },
        **exposures,
    }
    return list(claims.values()), profile


def parse_reconciled_pdf(path):
    if not str(path).lower().endswith(".pdf"):
        return None
    from pypdf import PdfReader
    try:
        reader = PdfReader(path)
        if len(reader.pages) != 1:
            return None
        text = reader.pages[0].extract_text(extraction_mode="layout") or ""
    except Exception:
        return None
    return parse_reconciled_layout(text)
