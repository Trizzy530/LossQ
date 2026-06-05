from __future__ import annotations

import re

from .utils import clean_text, clamp_score, money_values, split_lines


def detect_reported_totals(text: str) -> dict:
    lines = split_lines(text)

    reported = {
        "reported_total_claims": None,
        "reported_open_claims": None,
        "reported_closed_claims": None,
        "reported_litigation_claims": None,
        "reported_total_paid": None,
        "reported_total_reserve": None,
        "reported_total_incurred": None,
    }

    for line in lines:
        lower = clean_text(line).lower()
        amounts = money_values(line)

        if "total claims" in lower:
            match = re.search(r"total claims\s*[:\-]?\s*(\d+)", lower)
            if match:
                reported["reported_total_claims"] = int(match.group(1))

        if "open claims" in lower or "open claims?" in lower:
            if "none" in lower or "no open" in lower:
                reported["reported_open_claims"] = 0
            else:
                match = re.search(r"open claims\??\s*[:\-]?\s*(\d+)", lower)
                if match:
                    reported["reported_open_claims"] = int(match.group(1))

        if "closed claims" in lower:
            match = re.search(r"closed claims\s*[:\-]?\s*(\d+)", lower)
            if match:
                reported["reported_closed_claims"] = int(match.group(1))

        if "litigation" in lower:
            if "litigation no" in lower or "no litigation" in lower:
                reported["reported_litigation_claims"] = 0
            else:
                match = re.search(r"litigation[^0-9]*(\d+)", lower)
                if match:
                    reported["reported_litigation_claims"] = int(match.group(1))

        if "total paid" in lower and amounts:
            reported["reported_total_paid"] = amounts[-1]

        if "total reserve" in lower and amounts:
            reported["reported_total_reserve"] = amounts[-1]

        if "total incurred" in lower and amounts:
            reported["reported_total_incurred"] = amounts[-1]

        if ("totals" in lower or "subtotal" in lower) and len(amounts) >= 3:
            reported["reported_total_paid"] = reported["reported_total_paid"] or amounts[-3]
            reported["reported_total_reserve"] = reported["reported_total_reserve"] or amounts[-2]
            reported["reported_total_incurred"] = reported["reported_total_incurred"] or amounts[-1]

    return reported


def validate_loss_run(text: str, profile: dict, policies: list[dict], claims: list[dict], ignored_rows: list[dict]) -> dict:
    reported = detect_reported_totals(text)

    total_claims = len(claims)
    open_claims = sum(1 for claim in claims if str(claim.get("status") or "").lower() == "open")
    closed_claims = sum(1 for claim in claims if str(claim.get("status") or "").lower() == "closed")
    litigation_claims = sum(1 for claim in claims if claim.get("litigation"))

    total_paid = round(sum(float(claim.get("paid_amount") or 0) for claim in claims), 2)
    total_reserve = round(sum(float(claim.get("reserve_amount") or 0) for claim in claims), 2)
    total_incurred = round(sum(float(claim.get("total_incurred") or 0) for claim in claims), 2)

    warnings: list[str] = []
    passed_checks: list[str] = []

    if profile.get("business_name"):
        passed_checks.append("Named insured/account name detected.")
    else:
        warnings.append("Named insured/account name was not confidently detected.")

    if policies:
        passed_checks.append(f"Policy schedule detected with {len(policies)} policy row(s).")
    else:
        warnings.append("Policy schedule was not confidently detected.")

    if total_claims > 0:
        passed_checks.append(f"{total_claims} claim row(s) extracted.")
    else:
        warnings.append("No claim rows were extracted.")

    if ignored_rows:
        passed_checks.append(f"{len(ignored_rows)} non-claim/header/total row(s) ignored.")

    if reported.get("reported_total_claims") is not None:
        if reported["reported_total_claims"] == total_claims:
            passed_checks.append("Reported claim count matches extracted claim count.")
        else:
            warnings.append(
                f"Reported claim count {reported['reported_total_claims']} does not match extracted claim count {total_claims}."
            )

    if reported.get("reported_open_claims") is not None:
        if reported["reported_open_claims"] == open_claims:
            passed_checks.append("Reported open claim count matches extracted open claim count.")
        else:
            warnings.append(
                f"Reported open claims {reported['reported_open_claims']} does not match extracted open claims {open_claims}."
            )

    if reported.get("reported_total_incurred") is not None:
        variance = abs(float(reported["reported_total_incurred"]) - total_incurred)
        if variance <= 1:
            passed_checks.append("Reported total incurred reconciles to extracted claims.")
        else:
            warnings.append(
                f"Reported total incurred ${reported['reported_total_incurred']:,.2f} does not reconcile to extracted ${total_incurred:,.2f}."
            )

    financial_validation = "Passed"
    if any("does not" in warning or "No claim rows" in warning for warning in warnings):
        financial_validation = "Needs Review"

    renewal_signal = "Needs Review"
    lower_text = clean_text(text).lower()

    if "good renewal" in lower_text or "renewal recommended" in lower_text or "favorable renewal" in lower_text:
        renewal_signal = "Good Renewal"
    elif open_claims > 0 or litigation_claims > 0:
        renewal_signal = "Review Required"
    elif total_claims > 0 and total_reserve == 0:
        renewal_signal = "Good Renewal"

    base_score = 70

    if profile.get("business_name"):
        base_score += 5
    if policies:
        base_score += 5
    if claims:
        base_score += 10
    if financial_validation == "Passed":
        base_score += 10
    if warnings:
        base_score -= min(len(warnings) * 6, 25)

    confidence_score = clamp_score(base_score)

    if confidence_score >= 85:
        confidence_level = "High"
    elif confidence_score >= 65:
        confidence_level = "Medium"
    else:
        confidence_level = "Low"

    return {
        "engine": "LossQ Universal Parser Validation Engine V1",
        "document_confidence": confidence_score,
        "confidence_level": confidence_level,
        "financial_validation": financial_validation,
        "renewal_signal": renewal_signal,
        "warnings": warnings,
        "passed_checks": passed_checks,
        "ignored_rows": ignored_rows[:50],
        "reported_totals": reported,
        "extracted_totals": {
            "total_claims": total_claims,
            "open_claims": open_claims,
            "closed_claims": closed_claims,
            "litigation_claims": litigation_claims,
            "total_paid": total_paid,
            "total_reserve": total_reserve,
            "total_incurred": total_incurred,
        },
        "requires_review": confidence_score < 70 or financial_validation != "Passed",
    }