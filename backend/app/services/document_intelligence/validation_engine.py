from __future__ import annotations

import re
from typing import Any

from .utils import clean_text, clamp_score, money_values


def safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def detect_reported_totals(text: str) -> dict:
    lower = text.lower()

    reported_open_claims = None
    reported_closed_claims = None
    reported_litigation_claims = None
    reported_total_claims = None
    reported_total_paid = None
    reported_total_reserve = None
    reported_total_incurred = None

    open_match = re.search(r"\bopen claims?\s*[:\-]?\s*(none|no|zero|\d+)", lower, re.I)
    if open_match:
        value = open_match.group(1).lower()
        reported_open_claims = 0 if value in {"none", "no", "zero"} else int(value)

    lit_match = re.search(r"\blitigation claims?\s*[:\-]?\s*(none|no|zero|\d+)", lower, re.I)
    if lit_match:
        value = lit_match.group(1).lower()
        reported_litigation_claims = 0 if value in {"none", "no", "zero"} else int(value)

    total_claims_match = re.search(r"\btotal claims?\s*[:\-]?\s*(none|no|zero|\d+)", lower, re.I)
    if total_claims_match:
        value = total_claims_match.group(1).lower()
        reported_total_claims = 0 if value in {"none", "no", "zero"} else int(value)

    closed_match = re.search(r"\bclosed claims?\s*[:\-]?\s*(none|no|zero|\d+)", lower, re.I)
    if closed_match:
        value = closed_match.group(1).lower()
        reported_closed_claims = 0 if value in {"none", "no", "zero"} else int(value)

    total_paid_match = re.search(r"\btotal paid\s*[:\-]?\s*(\$?[\d,]+(?:\.\d{1,2})?)", text, re.I)
    if total_paid_match:
        values = money_values(total_paid_match.group(1))
        if values:
            reported_total_paid = values[-1]

    total_reserve_match = re.search(r"\btotal reserves?\s*[:\-]?\s*(\$?[\d,]+(?:\.\d{1,2})?)", text, re.I)
    if total_reserve_match:
        values = money_values(total_reserve_match.group(1))
        if values:
            reported_total_reserve = values[-1]

    total_incurred_match = re.search(r"\btotal incurred\s*[:\-]?\s*(\$?[\d,]+(?:\.\d{1,2})?)", text, re.I)
    if total_incurred_match:
        values = money_values(total_incurred_match.group(1))
        if values:
            reported_total_incurred = values[-1]

    return {
        "reported_total_claims": reported_total_claims,
        "reported_open_claims": reported_open_claims,
        "reported_closed_claims": reported_closed_claims,
        "reported_litigation_claims": reported_litigation_claims,
        "reported_total_paid": reported_total_paid,
        "reported_total_reserve": reported_total_reserve,
        "reported_total_incurred": reported_total_incurred,
    }


def determine_renewal_signal(
    total_claims: int,
    open_claims: int,
    litigation_claims: int,
    total_reserve: float,
    total_incurred: float,
    reported_totals: dict,
) -> str:
    """
    Renewal signal should not overstate risk or quality.

    Important distinction:
    - 0 claims is not "Strong Renewal" because there is no loss activity to analyze.
      It should be labeled as clean/no-loss history and still reviewed normally.
    - Low closed losses with zero reserves can be Good Renewal.
    """

    reported_total_claims = reported_totals.get("reported_total_claims")
    reported_open_claims = reported_totals.get("reported_open_claims")
    reported_litigation_claims = reported_totals.get("reported_litigation_claims")

    no_claims_reported = (
        total_claims == 0
        and (reported_total_claims == 0 or reported_total_claims is None)
        and (reported_open_claims in (0, None))
        and (reported_litigation_claims in (0, None))
        and total_reserve == 0
        and total_incurred == 0
    )

    if no_claims_reported:
        return "No Claims Reported - Clean Loss History"

    if litigation_claims > 0:
        return "Adverse Renewal Review - Litigation Present"

    if open_claims > 0 or total_reserve > 0:
        return "Renewal Review Needed - Open Claims or Reserves"

    if total_claims >= 8 or total_incurred >= 100000:
        return "Renewal Review Needed - Frequency or Severity Concern"

    if total_claims > 0 and open_claims == 0 and litigation_claims == 0 and total_reserve == 0:
        return "Good Renewal"

    return "Standard Renewal Review"


def validate_loss_run(
    text: str,
    profile: dict,
    policies: list[dict],
    claims: list[dict],
    ignored_rows: list[dict] | None = None,
) -> dict:
    ignored_rows = ignored_rows or []
    warnings: list[str] = []
    passed_checks: list[str] = []

    total_claims = len(claims)
    open_claims = sum(1 for claim in claims if str(claim.get("status") or "").lower() == "open")
    closed_claims = sum(1 for claim in claims if str(claim.get("status") or "").lower() == "closed")
    litigation_claims = sum(1 for claim in claims if bool(claim.get("litigation")))

    total_paid = round(sum(safe_float(claim.get("paid_amount")) for claim in claims), 2)
    total_reserve = round(sum(safe_float(claim.get("reserve_amount")) for claim in claims), 2)
    total_incurred = round(sum(safe_float(claim.get("total_incurred")) for claim in claims), 2)

    reported_totals = detect_reported_totals(text or "")

    if profile.get("business_name"):
        passed_checks.append("Named insured/account name detected.")
    else:
        warnings.append("Named insured/account name was not detected.")

    if policies:
        passed_checks.append(f"Policy schedule detected with {len(policies)} policy row(s).")
    else:
        warnings.append("No policy schedule rows were detected.")

    if total_claims > 0:
        passed_checks.append(f"{total_claims} claim row(s) extracted.")
    else:
        lower_text = (text or "").lower()
        no_loss_language = any(
            phrase in lower_text
            for phrase in [
                "no claims",
                "no losses",
                "no loss activity",
                "zero claims",
                "total claims 0",
                "no open claims",
                "none shown",
            ]
        )

        if no_loss_language:
            passed_checks.append("No claim rows extracted; document appears to report no/zero loss activity.")
        else:
            warnings.append("No claim rows were extracted. Verify whether this is a no-loss report or parser review is needed.")

    if ignored_rows:
        passed_checks.append(f"{len(ignored_rows)} non-claim/header/total row(s) ignored.")

    if reported_totals.get("reported_open_claims") is not None:
        if reported_totals["reported_open_claims"] != open_claims:
            warnings.append(
                f"Reported open claims {reported_totals['reported_open_claims']} does not match extracted open claims {open_claims}."
            )
        else:
            passed_checks.append("Reported open claim count matches extracted open claim count.")

    if reported_totals.get("reported_litigation_claims") is not None:
        if reported_totals["reported_litigation_claims"] != litigation_claims:
            warnings.append(
                f"Reported litigation claims {reported_totals['reported_litigation_claims']} does not match extracted litigation claims {litigation_claims}."
            )

    if reported_totals.get("reported_total_claims") is not None:
        if reported_totals["reported_total_claims"] != total_claims:
            warnings.append(
                f"Reported total claims {reported_totals['reported_total_claims']} does not match extracted total claims {total_claims}."
            )

    # Financial validation: use extracted math first, then compare to reported if available.
    financial_validation = "Passed"

    if abs((total_paid + total_reserve) - total_incurred) > 1:
        # Some reports already provide total incurred as the authoritative field,
        # but in most loss runs paid + reserve should equal incurred.
        warnings.append("Extracted paid plus reserve does not equal extracted total incurred.")
        financial_validation = "Needs Review"

    if reported_totals.get("reported_total_paid") is not None:
        if abs(reported_totals["reported_total_paid"] - total_paid) > 1:
            warnings.append(
                f"Reported total paid {reported_totals['reported_total_paid']} does not match extracted total paid {total_paid}."
            )
            financial_validation = "Needs Review"

    if reported_totals.get("reported_total_reserve") is not None:
        if abs(reported_totals["reported_total_reserve"] - total_reserve) > 1:
            warnings.append(
                f"Reported total reserve {reported_totals['reported_total_reserve']} does not match extracted total reserve {total_reserve}."
            )
            financial_validation = "Needs Review"

    if reported_totals.get("reported_total_incurred") is not None:
        if abs(reported_totals["reported_total_incurred"] - total_incurred) > 1:
            warnings.append(
                f"Reported total incurred {reported_totals['reported_total_incurred']} does not match extracted total incurred {total_incurred}."
            )
            financial_validation = "Needs Review"

    renewal_signal = determine_renewal_signal(
        total_claims=total_claims,
        open_claims=open_claims,
        litigation_claims=litigation_claims,
        total_reserve=total_reserve,
        total_incurred=total_incurred,
        reported_totals=reported_totals,
    )

    confidence_score = 100

    if warnings:
        confidence_score -= min(len(warnings) * 10, 40)

    if not profile.get("business_name"):
        confidence_score -= 10

    if not policies:
        confidence_score -= 10

    if total_claims == 0 and "No Claims Reported" in renewal_signal:
        # Keep high confidence for clean no-loss reports, but do not call it strong.
        confidence_score = min(confidence_score, 92)

    confidence_score = clamp_score(confidence_score)

    if confidence_score >= 85:
        confidence_level = "High"
    elif confidence_score >= 65:
        confidence_level = "Medium"
    else:
        confidence_level = "Low"

    requires_review = confidence_score < 70 or financial_validation != "Passed"

    if "No Claims Reported" in renewal_signal:
        processing_recommendation = (
            "No claim activity was extracted. Treat this as a clean/no-loss history and verify the report is complete before renewal use."
        )
    elif requires_review:
        processing_recommendation = "Review extraction warnings before underwriting use."
    else:
        processing_recommendation = "Extraction is strong. Standard review recommended before final underwriting use."

    return {
        "engine": "LossQ Universal Parser Validation Engine V1",
        "document_confidence": confidence_score,
        "confidence_level": confidence_level,
        "financial_validation": financial_validation,
        "renewal_signal": renewal_signal,
        "warnings": warnings,
        "passed_checks": passed_checks,
        "ignored_rows": ignored_rows,
        "reported_totals": reported_totals,
        "extracted_totals": {
            "total_claims": total_claims,
            "open_claims": open_claims,
            "closed_claims": closed_claims,
            "litigation_claims": litigation_claims,
            "total_paid": total_paid,
            "total_reserve": total_reserve,
            "total_incurred": total_incurred,
        },
        "requires_review": requires_review,
        "processing_recommendation": processing_recommendation,
    }
