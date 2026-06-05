from __future__ import annotations

import re
from .utils import compact_spaces, money_values


def _extract_summary_counts(text: str) -> dict:
    lower_text = text or ""
    summary: dict = {}
    patterns = {
        "reported_total_claims": r"Total Claims\s+([0-9]+)",
        "reported_open_claims": r"Open Claims\??\s+(?:NONE shown / all closed|([0-9]+)|NONE|NO)",
        "reported_litigation_claims": r"(?:Litigation / Attorney Claims|Litigation)\s+(?:NO|NONE|([0-9]+))",
        "reported_total_paid": r"Total Paid\s+\$?([0-9,]+(?:\.\d{1,2})?)",
        "reported_total_reserve": r"Total Reserve\s+\$?([0-9,]+(?:\.\d{1,2})?)",
        "reported_total_incurred": r"Total Incurred\s+\$?([0-9,]+(?:\.\d{1,2})?)",
    }
    for key, pattern in patterns.items():
        m = re.search(pattern, lower_text, re.IGNORECASE)
        if not m:
            continue
        raw = next((g for g in m.groups() if g is not None), "0")
        if raw.upper() in ["NO", "NONE"]:
            raw = "0"
        summary[key] = float(str(raw).replace(",", ""))

    # Handle rows like TOTALS $20,030 $0 $20,030.
    for line in lower_text.splitlines():
        if re.search(r"\b(total|totals|subtotal|sub-total)\b", line, re.IGNORECASE):
            vals = money_values(line)
            if len(vals) >= 3:
                summary.setdefault("reported_total_paid", vals[-3])
                summary.setdefault("reported_total_reserve", vals[-2])
                summary.setdefault("reported_total_incurred", vals[-1])
    return summary


def validate_loss_run(text: str, profile: dict, policies: list[dict], claims: list[dict], ignored_rows: list[dict], extraction_meta: dict) -> dict:
    total_claims = len(claims)
    open_claims = sum(1 for c in claims if str(c.get("status", "")).lower() == "open")
    closed_claims = sum(1 for c in claims if str(c.get("status", "")).lower() == "closed")
    litigation_claims = sum(1 for c in claims if c.get("litigation"))
    total_paid = sum(float(c.get("paid_amount") or 0) for c in claims)
    total_reserve = sum(float(c.get("reserve_amount") or 0) for c in claims)
    total_incurred = sum(float(c.get("total_incurred") or 0) for c in claims)

    reported = _extract_summary_counts(text)
    warnings: list[str] = []
    passed_checks: list[str] = []

    if ignored_rows:
        passed_checks.append(f"Ignored {len(ignored_rows)} subtotal/total/noise row(s).")

    if not profile.get("business_name") or "Needs Review" in str(profile.get("business_name")):
        warnings.append("Named insured/business name needs review.")
    else:
        passed_checks.append("Named insured detected.")

    if policies:
        passed_checks.append(f"Detected {len(policies)} policy schedule row(s).")
    else:
        warnings.append("No policy schedule rows confidently detected.")

    if claims:
        passed_checks.append(f"Detected {total_claims} claim row(s).")
    else:
        warnings.append("No claim rows were confidently detected. Review required before relying on results.")

    tolerance = 1.0
    for reported_key, extracted_value, label in [
        ("reported_total_paid", total_paid, "paid total"),
        ("reported_total_reserve", total_reserve, "reserve total"),
        ("reported_total_incurred", total_incurred, "incurred total"),
    ]:
        if reported_key in reported:
            diff = abs(float(reported[reported_key]) - float(extracted_value))
            if diff <= tolerance:
                passed_checks.append(f"Financial reconciliation passed for {label}.")
            else:
                warnings.append(
                    f"Financial reconciliation mismatch for {label}: reported {reported[reported_key]}, extracted {round(extracted_value, 2)}."
                )

    lower = compact_spaces(text).lower()
    renewal_signal = "Needs Review"
    if "good renewal" in lower or "favorable renewal" in lower or "renewal recommended" in lower:
        renewal_signal = "Good Renewal"
    elif "poor renewal" in lower or "non-renew" in lower or "adverse" in lower:
        renewal_signal = "Adverse Renewal"

    financial_status = "Passed" if not any("Financial reconciliation mismatch" in w for w in warnings) and claims else "Needs Review"

    return {
        "document_type": "Loss Run / Experience Detail" if "loss run" in lower or "experience" in lower else "Document Needs Review",
        "document_confidence": 0,  # set by confidence engine
        "financial_validation": financial_status,
        "renewal_signal": renewal_signal,
        "extracted_totals": {
            "total_claims": total_claims,
            "open_claims": open_claims,
            "closed_claims": closed_claims,
            "litigation_claims": litigation_claims,
            "total_paid": round(total_paid, 2),
            "total_reserve": round(total_reserve, 2),
            "total_incurred": round(total_incurred, 2),
        },
        "reported_totals": reported,
        "passed_checks": passed_checks,
        "warnings": warnings + extraction_meta.get("warnings", []),
        "ignored_rows": ignored_rows[:20],
        "requires_review": bool(warnings) or not claims,
    }
