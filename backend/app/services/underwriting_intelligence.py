from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


SUPPORTED_METRICS = {
    "claim_count",
    "open_claim_count",
    "total_incurred",
    "total_reserve",
    "max_single_claim",
    "loss_ratio",
    "litigated_claim_count",
}
SUPPORTED_OPERATORS = {"gt", "gte", "lt", "lte", "eq"}

DEFAULT_RULES = [
    {
        "id": "open-claims",
        "label": "Multiple open claims",
        "metric": "open_claim_count",
        "operator": "gte",
        "threshold": 2,
        "severity": "warning",
        "action": "Obtain current loss details and resolution plans for every open claim.",
        "enabled": True,
    },
    {
        "id": "large-loss",
        "label": "Large individual loss",
        "metric": "max_single_claim",
        "operator": "gte",
        "threshold": 100000,
        "severity": "critical",
        "action": "Refer for senior underwriting review and require a large-loss narrative.",
        "enabled": True,
    },
    {
        "id": "loss-ratio",
        "label": "Elevated loss ratio",
        "metric": "loss_ratio",
        "operator": "gte",
        "threshold": 0.65,
        "severity": "critical",
        "action": "Review pricing adequacy, exposure changes, and corrective actions.",
        "enabled": True,
    },
]


def money(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        return float(str(value).replace("$", "").replace(",", "").strip() or 0)
    except (TypeError, ValueError):
        return 0.0


def clean(value: Any) -> str:
    return str(value or "").strip()


def claim_key(claim: Mapping[str, Any]) -> str:
    claim_number = clean(claim.get("claim_number")).upper()
    policy_number = clean(claim.get("policy_number")).upper()
    return f"{policy_number}|{claim_number}"


def claim_metrics(claims: Iterable[Mapping[str, Any]], premium: Any = 0) -> dict[str, float]:
    rows = [dict(claim) for claim in claims]
    incurred_values = [money(row.get("total_incurred")) for row in rows]
    total_incurred = sum(incurred_values)
    premium_value = money(premium)
    return {
        "claim_count": float(len(rows)),
        "open_claim_count": float(
            sum(1 for row in rows if clean(row.get("status")).lower() == "open")
        ),
        "total_incurred": round(total_incurred, 2),
        "total_reserve": round(sum(money(row.get("reserve_amount")) for row in rows), 2),
        "max_single_claim": round(max(incurred_values, default=0.0), 2),
        "loss_ratio": round(total_incurred / premium_value, 4) if premium_value > 0 else 0.0,
        "litigated_claim_count": float(
            sum(
                1
                for row in rows
                if bool(row.get("litigation") or row.get("attorney_assigned") or row.get("suit_filed"))
            )
        ),
    }


def _compare(actual: float, operator: str, threshold: float) -> bool:
    if operator == "gt":
        return actual > threshold
    if operator == "gte":
        return actual >= threshold
    if operator == "lt":
        return actual < threshold
    if operator == "lte":
        return actual <= threshold
    if operator == "eq":
        return actual == threshold
    raise ValueError(f"Unsupported underwriting rule operator: {operator}")


def validate_rules(rules: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rule_rows = list(rules)
    if len(rule_rows) > 100:
        raise ValueError("A rule set cannot contain more than 100 rules.")
    validated = []
    seen_ids: set[str] = set()
    for index, raw_rule in enumerate(rule_rows, start=1):
        rule = dict(raw_rule)
        rule_id = clean(rule.get("id"))
        metric = clean(rule.get("metric"))
        operator = clean(rule.get("operator"))
        severity = clean(rule.get("severity") or "warning").lower()
        if not rule_id or rule_id in seen_ids:
            raise ValueError(f"Rule {index} needs a unique id.")
        if len(rule_id) > 64:
            raise ValueError(f"Rule {index} id cannot exceed 64 characters.")
        if metric not in SUPPORTED_METRICS:
            raise ValueError(f"Rule {rule_id} uses unsupported metric {metric}.")
        if operator not in SUPPORTED_OPERATORS:
            raise ValueError(f"Rule {rule_id} uses unsupported operator {operator}.")
        if severity not in {"info", "warning", "critical"}:
            raise ValueError(f"Rule {rule_id} uses unsupported severity {severity}.")
        try:
            threshold = float(rule.get("threshold"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Rule {rule_id} needs a numeric threshold.") from exc
        seen_ids.add(rule_id)
        validated.append(
            {
                "id": rule_id,
                "label": (clean(rule.get("label")) or rule_id)[:160],
                "metric": metric,
                "operator": operator,
                "threshold": threshold,
                "severity": severity,
                "action": clean(rule.get("action"))[:1000],
                "enabled": bool(rule.get("enabled", True)),
            }
        )
    return validated


def evaluate_underwriting_rules(
    claims: Iterable[Mapping[str, Any]], *, premium: Any = 0,
    rules: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    validated_rules = validate_rules(rules or DEFAULT_RULES)
    metrics = claim_metrics(claims, premium=premium)
    triggered = []
    for rule in validated_rules:
        if not rule["enabled"]:
            continue
        actual = metrics[rule["metric"]]
        if _compare(actual, rule["operator"], rule["threshold"]):
            triggered.append({**rule, "actual": actual})

    severities = {rule["severity"] for rule in triggered}
    decision = "refer" if "critical" in severities else "review" if "warning" in severities else "clear"
    return {
        "decision": decision,
        "metrics": metrics,
        "triggered_rules": triggered,
        "rules_evaluated": len([rule for rule in validated_rules if rule["enabled"]]),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def compare_renewal_claims(
    current_claims: Iterable[Mapping[str, Any]],
    prior_claims: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    current_rows = [dict(row) for row in current_claims]
    prior_rows = [dict(row) for row in prior_claims]
    current_map = {claim_key(row): row for row in current_rows}
    prior_map = {claim_key(row): row for row in prior_rows}

    new_keys = sorted(current_map.keys() - prior_map.keys())
    removed_keys = sorted(prior_map.keys() - current_map.keys())
    changed_claims = []
    tracked_fields = ("status", "paid_amount", "reserve_amount", "total_incurred")
    for key in sorted(current_map.keys() & prior_map.keys()):
        current = current_map[key]
        prior = prior_map[key]
        changes = {}
        for field in tracked_fields:
            before = money(prior.get(field)) if field != "status" else clean(prior.get(field))
            after = money(current.get(field)) if field != "status" else clean(current.get(field))
            if before != after:
                changes[field] = {"before": before, "after": after}
        if changes:
            changed_claims.append({"claim_key": key, "changes": changes})

    current_metrics = claim_metrics(current_rows)
    prior_metrics = claim_metrics(prior_rows)
    deltas = {
        key: round(current_metrics[key] - prior_metrics[key], 4)
        for key in current_metrics
        if key != "loss_ratio"
    }
    incurred_delta = deltas["total_incurred"]
    direction = "deteriorated" if incurred_delta > 0 else "improved" if incurred_delta < 0 else "unchanged"
    return {
        "direction": direction,
        "current": current_metrics,
        "prior": prior_metrics,
        "deltas": deltas,
        "new_claims": [current_map[key] for key in new_keys],
        "removed_claims": [prior_map[key] for key in removed_keys],
        "changed_claims": changed_claims,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
