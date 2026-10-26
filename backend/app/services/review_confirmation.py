from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class PreparedReview:
    profile: dict[str, Any]
    policies: list[dict[str, Any]]
    claims: list[dict[str, Any]]
    policy_numbers: tuple[str, ...]
    warnings: tuple[str, ...]


def clean(value: Any) -> str:
    return str(value or "").strip()


def policy_number(value: Any) -> str:
    return clean(value).upper()


def money(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        raw = clean(value).replace("$", "").replace(",", "")
        if not raw or raw in {"-", "None", "none", "null"}:
            return 0.0
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _looks_like_identifier(value: Any) -> bool:
    raw = clean(value).upper()
    return len(raw) >= 3 and any(char.isdigit() for char in raw)


def prepare_review_confirmation(payload: Mapping[str, Any]) -> PreparedReview:
    """Validate a human-reviewed extraction before any database mutation."""

    profile = dict(payload.get("profile") or {})
    policies = [dict(item) for item in (payload.get("policies") or []) if isinstance(item, Mapping)]
    claims = [dict(item) for item in (payload.get("claims") or []) if isinstance(item, Mapping)]

    known_policies: list[str] = []
    for item in policies:
        candidate = policy_number(
            item.get("policy_number") or item.get("policyNumber") or item.get("policy")
        )
        if candidate and candidate not in known_policies:
            known_policies.append(candidate)

    profile_policy = policy_number(profile.get("policy_number"))
    if profile_policy and profile_policy not in known_policies:
        known_policies.append(profile_policy)

    normalized_claims: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    warnings: list[str] = []

    for index, claim in enumerate(claims, start=1):
        claim_number = clean(claim.get("claim_number") or claim.get("claimNumber")).upper()
        claim_policy = policy_number(
            claim.get("policy_number") or claim.get("policyNumber") or profile_policy
        )

        if not _looks_like_identifier(claim_number):
            raise ValueError(f"Claim row {index} needs a valid claim number before confirmation.")
        if not _looks_like_identifier(claim_policy):
            raise ValueError(f"Claim {claim_number} needs a valid policy number before confirmation.")

        key = (claim_number, claim_policy)
        if key in seen:
            raise ValueError(f"Duplicate reviewed claim {claim_number} for policy {claim_policy}.")
        seen.add(key)

        if claim_policy not in known_policies:
            known_policies.append(claim_policy)

        paid = money(claim.get("paid_amount") or claim.get("paid"))
        reserve = money(claim.get("reserve_amount") or claim.get("reserve"))
        incurred = money(claim.get("total_incurred") or claim.get("incurred"))
        if incurred and abs((paid + reserve) - incurred) > 1:
            warnings.append(
                f"Claim {claim_number} was manually confirmed with paid plus reserve not equal to incurred."
            )

        normalized_claims.append(
            {
                **claim,
                "claim_number": claim_number,
                "policy_number": claim_policy,
                "paid_amount": paid,
                "reserve_amount": reserve,
                "total_incurred": incurred,
            }
        )

    validation = dict(payload.get("validation") or {})
    no_loss_confirmed = bool(payload.get("confirm_no_loss") or validation.get("no_loss_confirmed"))
    if not normalized_claims and not no_loss_confirmed:
        raise ValueError(
            "No reviewed claims were supplied. Confirm this is a no-loss account before saving an empty history."
        )

    if not known_policies:
        raise ValueError("At least one valid policy number is required before confirmation.")

    primary_policy = profile_policy or known_policies[0]
    profile["policy_number"] = primary_policy
    profile["policies"] = policies

    return PreparedReview(
        profile=profile,
        policies=policies,
        claims=normalized_claims,
        policy_numbers=tuple(known_policies),
        warnings=tuple(warnings),
    )

