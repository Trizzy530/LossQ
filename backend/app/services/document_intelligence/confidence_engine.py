from __future__ import annotations

from .utils import clamp_score


def score_document(
    profile: dict,
    policies: list[dict],
    claims: list[dict],
    validation: dict,
    meta: dict | None = None,
) -> dict:
    meta = meta or {}
    warnings = list(validation.get("warnings") or [])

    score = 50

    if profile.get("business_name"):
        score += 10

    if profile.get("carrier_name") or profile.get("writing_carrier"):
        score += 5

    if profile.get("policy_number") or profile.get("account_number"):
        score += 5

    if policies:
        score += 10

    if claims:
        score += 15

    if validation.get("financial_validation") == "Passed":
        score += 10

    if meta.get("ocr_used"):
        score -= 5

    score -= min(len(warnings) * 5, 25)

    score = clamp_score(score)

    if score >= 85:
        level = "High"
        recommendation = "Extraction is strong. Standard review recommended before final underwriting use."
    elif score >= 65:
        level = "Medium"
        recommendation = "Extraction is usable but should be reviewed before saving or carrier submission."
    else:
        level = "Low"
        recommendation = "Extraction requires manual review before claims are saved or used for underwriting."

    return {
        "document_confidence": score,
        "confidence_level": level,
        "processing_recommendation": recommendation,
        "ocr_used": bool(meta.get("ocr_used")),
        "warning_count": len(warnings),
    }