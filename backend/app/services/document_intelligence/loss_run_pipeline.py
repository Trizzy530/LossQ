from __future__ import annotations

from .claim_table_parser import parse_claims
from .confidence_engine import score_document
from .field_normalizer import extract_profile
from .policy_schedule_parser import parse_policy_schedule
from .text_extractor import extract_text
from .validation_engine import validate_loss_run
from .utils import normalize_policy_number


def attach_policy_claim_counts(policies: list[dict], claims: list[dict]) -> list[dict]:
    policy_map = {}

    for claim in claims:
        policy_number = normalize_policy_number(claim.get("policy_number"))
        if not policy_number:
            continue

        if policy_number not in policy_map:
            policy_map[policy_number] = {
                "claim_count": 0,
                "total_paid": 0.0,
                "total_reserve": 0.0,
                "total_incurred": 0.0,
            }

        policy_map[policy_number]["claim_count"] += 1
        policy_map[policy_number]["total_paid"] += float(claim.get("paid_amount") or 0)
        policy_map[policy_number]["total_reserve"] += float(claim.get("reserve_amount") or 0)
        policy_map[policy_number]["total_incurred"] += float(claim.get("total_incurred") or 0)

    updated = []

    for policy in policies:
        policy_number = normalize_policy_number(policy.get("policy_number"))
        stats = policy_map.get(policy_number, {})

        updated_policy = {
            **policy,
            "claim_count": int(stats.get("claim_count", policy.get("claim_count") or 0)),
            "total_paid": round(float(stats.get("total_paid", policy.get("total_paid") or 0)), 2),
            "total_reserve": round(float(stats.get("total_reserve", policy.get("total_reserve") or 0)), 2),
            "total_incurred": round(float(stats.get("total_incurred", policy.get("total_incurred") or 0)), 2),
        }

        updated.append(updated_policy)

    return updated


def ensure_claim_policies(claims: list[dict], policies: list[dict], profile: dict) -> list[dict]:
    known_policy_numbers = [
        normalize_policy_number(policy.get("policy_number"))
        for policy in policies
        if policy.get("policy_number")
    ]

    account_policy = normalize_policy_number(
        profile.get("policy_number") or profile.get("account_number") or ""
    )

    cleaned = []

    for claim in claims:
        claim_policy = normalize_policy_number(claim.get("policy_number"))

        if not claim_policy:
            if len(known_policy_numbers) == 1:
                claim_policy = known_policy_numbers[0]
            else:
                claim_policy = account_policy

        cleaned.append(
            {
                **claim,
                "policy_number": claim_policy,
            }
        )

    return cleaned


def parse_loss_run_file(file_path: str, filename: str = "") -> dict:
    text, meta = extract_text(file_path, filename)

    profile = extract_profile(text)
    policies = parse_policy_schedule(text, profile)
    claims, ignored_rows = parse_claims(text, policies, profile)

    claims = ensure_claim_policies(claims, policies, profile)
    policies = attach_policy_claim_counts(policies, claims)

    validation = validate_loss_run(
        text=text,
        profile=profile,
        policies=policies,
        claims=claims,
        ignored_rows=ignored_rows,
    )

    confidence = score_document(
        profile=profile,
        policies=policies,
        claims=claims,
        validation=validation,
        meta=meta,
    )

    validation.update(confidence)

    return {
        "profile": profile,
        "policies": policies,
        "claims": claims,
        "validation": validation,
        "raw_text_preview": (text or "")[:8000],
        "extraction_meta": meta,
    }