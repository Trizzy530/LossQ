from __future__ import annotations


def score_document(profile: dict, policies: list[dict], claims: list[dict], validation: dict) -> dict:
    score = 35
    if profile.get("business_name") and "Needs Review" not in str(profile.get("business_name")):
        score += 10
    if profile.get("account_number") and "Needs Review" not in str(profile.get("account_number")):
        score += 5
    if policies:
        score += min(20, len(policies) * 4)
    if claims:
        score += min(25, len(claims) * 4)
    if validation.get("financial_validation") == "Passed":
        score += 15
    if validation.get("ignored_rows"):
        score += 3
    if validation.get("warnings"):
        score -= min(25, len(validation.get("warnings", [])) * 5)

    score = max(0, min(100, int(score)))
    if score >= 85:
        level = "High"
    elif score >= 65:
        level = "Medium"
    else:
        level = "Low"

    validation["document_confidence"] = score
    validation["confidence_level"] = level
    validation["requires_review"] = validation.get("requires_review") or score < 75
    return validation
