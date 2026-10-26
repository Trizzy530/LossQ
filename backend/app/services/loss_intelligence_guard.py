from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class ReplacementDecision:
    safe_to_replace: bool
    mode: str
    reasons: tuple[str, ...]
    existing_claim_count: int
    incoming_claim_count: int
    extraction_status: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        return payload


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _money(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        cleaned = _clean(value).replace("$", "").replace(",", "")
        if not cleaned or cleaned in {"-", "None", "none", "null"}:
            return 0.0
        return float(cleaned)
    except (TypeError, ValueError):
        return 0.0


def _claim_has_identity(claim: Mapping[str, Any]) -> bool:
    claim_number = _clean(claim.get("claim_number")).upper()
    policy_number = _clean(claim.get("policy_number")).upper()
    return bool(claim_number and claim_number != "UNKNOWN" and policy_number)


def _claim_financials_reconcile(claim: Mapping[str, Any], tolerance: float = 1.0) -> bool:
    paid = _money(claim.get("paid_amount") or claim.get("paid"))
    reserve = _money(claim.get("reserve_amount") or claim.get("reserve"))
    incurred = _money(claim.get("total_incurred") or claim.get("incurred"))

    # Zero-dollar claims can be legitimate and should not fail solely for being zero.
    if paid == 0 and reserve == 0 and incurred == 0:
        return True

    return abs((paid + reserve) - incurred) <= tolerance


def decide_claim_replacement(
    *,
    existing_claim_count: int,
    incoming_claims: Iterable[Mapping[str, Any]],
    extraction_quality: Mapping[str, Any] | None,
    reported_total_claims: int | None = None,
) -> ReplacementDecision:
    """Decide whether an upload may replace a policy's persisted claim history.

    Replacement is intentionally conservative. An uncertain parse remains visible in the
    upload response, but it must not destroy a previously trusted claim set.
    """

    claims = list(incoming_claims or [])
    quality = dict(extraction_quality or {})
    status = _clean(quality.get("status") or "unknown").lower()
    critical_issues = [
        _clean(item) for item in (quality.get("critical_issues") or []) if _clean(item)
    ]
    reasons: list[str] = []

    if not claims:
        reasons.append("No incoming claims were extracted.")

    invalid_identity_count = sum(1 for claim in claims if not _claim_has_identity(claim))
    if invalid_identity_count:
        reasons.append(
            f"{invalid_identity_count} incoming claim(s) are missing a reliable claim or policy identifier."
        )

    unreconciled_count = sum(
        1 for claim in claims if not _claim_financials_reconcile(claim)
    )
    if unreconciled_count:
        reasons.append(
            f"{unreconciled_count} incoming claim(s) have paid plus reserve values that do not reconcile to incurred."
        )

    if status in {"review_required", "failed", "unknown", ""}:
        reasons.append(f"Extraction quality status is {status or 'unknown'}.")

    reasons.extend(critical_issues)

    if reported_total_claims is not None and len(claims) != int(reported_total_claims):
        reasons.append(
            "Extracted claim count does not match the document's reported total claim count."
        )

    if existing_claim_count > 0 and len(claims) < existing_claim_count:
        reasons.append(
            "Incoming extraction contains fewer claims than the currently saved policy history."
        )

    safe_to_replace = not reasons
    return ReplacementDecision(
        safe_to_replace=safe_to_replace,
        mode="replace" if safe_to_replace else "review_only",
        reasons=tuple(dict.fromkeys(reasons)),
        existing_claim_count=max(0, int(existing_claim_count or 0)),
        incoming_claim_count=len(claims),
        extraction_status=status or "unknown",
    )

