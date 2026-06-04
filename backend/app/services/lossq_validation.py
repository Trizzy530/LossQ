"""
LossQ validation engine.

Purpose:
- Phase 3: flag uncertain extraction results instead of guessing.
- Produces structured validation output that the dashboard/review screen can show.
"""

from __future__ import annotations

from typing import Any, Dict, List


def number(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        text = str(value).replace("$", "").replace(",", "").strip()
        if text in {"", "-", "--"}:
            return 0.0
        return float(text)
    except Exception:
        return 0.0


def policy_numbers_from_policies(policies: List[Dict[str, Any]]) -> List[str]:
    values: List[str] = []
    for policy in policies or []:
        value = str(policy.get("policy_number") or "").strip().upper()
        if value and value not in values:
            values.append(value)
    return values


def validate_loss_run_payload(
    profile: Dict[str, Any] | None,
    policies: List[Dict[str, Any]] | None,
    claims: List[Dict[str, Any]] | None,
    document_totals: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    profile = profile or {}
    policies = policies or []
    claims = claims or []
    document_totals = document_totals or {}

    warnings: List[str] = []
    needs_review: List[str] = []
    confidence_score = 100

    if not profile.get("business_name"):
        needs_review.append("Insured/business name was not detected.")
        confidence_score -= 10

    if not (profile.get("carrier_name") or profile.get("writing_carrier")):
        needs_review.append("Carrier or writing carrier was not detected.")
        confidence_score -= 10

    if not profile.get("policy_number") and not policies:
        needs_review.append("No account policy or policy schedule was detected.")
        confidence_score -= 15

    if not claims:
        needs_review.append("No claim rows were detected.")
        confidence_score -= 30

    policy_numbers = policy_numbers_from_policies(policies)
    claims_missing_policy = 0
    claims_outside_schedule = 0
    duplicate_claims = set()
    seen_claims = set()

    for claim in claims:
        claim_number = str(claim.get("claim_number") or "").strip().upper()
        claim_policy = str(claim.get("policy_number") or "").strip().upper()

        if not claim_number:
            warnings.append("A claim row is missing a claim number.")
            confidence_score -= 2
        elif claim_number in seen_claims:
            duplicate_claims.add(claim_number)
        else:
            seen_claims.add(claim_number)

        if not claim_policy:
            claims_missing_policy += 1
        elif policy_numbers and claim_policy not in policy_numbers:
            claims_outside_schedule += 1

        paid = number(claim.get("paid_amount") or claim.get("paid"))
        reserve = number(claim.get("reserve_amount") or claim.get("reserve"))
        incurred = number(claim.get("total_incurred") or claim.get("incurred"))

        if incurred == 0 and (paid or reserve):
            claim["total_incurred"] = paid + reserve

        if incurred and paid + reserve and abs(incurred - (paid + reserve)) > 1:
            warnings.append(f"Claim {claim_number or '[missing claim number]'} incurred does not equal paid + reserve.")
            confidence_score -= 2

    if claims_missing_policy:
        needs_review.append(f"{claims_missing_policy} claim row(s) are missing policy numbers.")
        confidence_score -= min(20, claims_missing_policy * 3)

    if claims_outside_schedule:
        needs_review.append(f"{claims_outside_schedule} claim row(s) do not match the detected policy schedule.")
        confidence_score -= min(20, claims_outside_schedule * 4)

    if duplicate_claims:
        warnings.append(f"Duplicate claim numbers detected: {', '.join(sorted(duplicate_claims))}.")
        confidence_score -= min(10, len(duplicate_claims) * 2)

    calculated_total = sum(number(c.get("total_incurred") or c.get("incurred")) for c in claims)
    document_total = number(
        document_totals.get("total_incurred")
        or document_totals.get("incurred")
        or document_totals.get("total")
    )

    if document_total and abs(calculated_total - document_total) > 1:
        needs_review.append(
            f"Calculated total incurred ${calculated_total:,.0f} does not match document total ${document_total:,.0f}."
        )
        confidence_score -= 15

    policy_rollup: Dict[str, Dict[str, Any]] = {}
    for claim in claims:
        policy_number = str(claim.get("policy_number") or "UNKNOWN").strip().upper() or "UNKNOWN"
        policy_rollup.setdefault(policy_number, {"policy_number": policy_number, "claim_count": 0, "total_incurred": 0})
        policy_rollup[policy_number]["claim_count"] += 1
        policy_rollup[policy_number]["total_incurred"] += number(claim.get("total_incurred") or claim.get("incurred"))

    return {
        "is_valid": len(needs_review) == 0,
        "confidence_score": max(0, min(100, confidence_score)),
        "needs_manual_review": len(needs_review) > 0,
        "needs_review": needs_review,
        "warnings": warnings,
        "policy_count": len(policies),
        "claim_count": len(claims),
        "calculated_total_incurred": calculated_total,
        "document_total_incurred": document_total,
        "policy_rollup": list(policy_rollup.values()),
    }