from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.account_profile import AccountProfile
from app.models.claim import Claim
from app.models.underwriting_rule_set import UnderwritingRuleSet
from app.role_utils import require_permission
from app.services.audit import record_audit_event
from app.services.underwriting_intelligence import (
    DEFAULT_RULES,
    claim_metrics,
    compare_renewal_claims,
    evaluate_underwriting_rules,
    validate_rules,
)


router = APIRouter(prefix="/loss-intelligence", tags=["Loss Intelligence"])

CLAIM_EXPORT_FIELDS = [
    "claim_number", "policy_number", "line_of_business", "claim_type", "cause_of_loss",
    "date_of_loss", "date_reported", "date_closed", "status", "description",
    "paid_amount", "reserve_amount", "total_incurred", "litigation",
    "attorney_assigned", "suit_filed",
]


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _money(value: Any) -> float:
    try:
        return float(str(value or 0).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def _json_value(value: Any, fallback: Any) -> Any:
    if value is None or value == "":
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _claims_for_policy(db: Session, organization_id: int, policy_number: str) -> list[Claim]:
    normalized = _clean(policy_number).upper()
    if not normalized:
        raise HTTPException(status_code=422, detail="policy_number is required.")
    return (
        db.query(Claim)
        .filter(
            Claim.organization_id == organization_id,
            func.upper(func.trim(Claim.policy_number)) == normalized,
            func.coalesce(Claim.is_deleted, False).is_(False),
        )
        .order_by(Claim.claim_number.asc())
        .all()
    )


def _profile_for_policy(db: Session, organization_id: int, policy_number: str) -> AccountProfile | None:
    normalized = _clean(policy_number).upper()
    return (
        db.query(AccountProfile)
        .filter(
            AccountProfile.organization_id == organization_id,
            func.upper(func.trim(AccountProfile.policy_number)) == normalized,
        )
        .order_by(AccountProfile.id.desc())
        .first()
    )


def _claim_record(claim: Claim) -> dict[str, Any]:
    return {
        "claim_number": _clean(claim.claim_number),
        "policy_number": _clean(claim.policy_number),
        "line_of_business": _clean(claim.line_of_business),
        "claim_type": _clean(claim.claim_type),
        "cause_of_loss": _clean(claim.cause_of_loss),
        "date_of_loss": _clean(claim.date_of_loss),
        "date_reported": _clean(claim.date_reported),
        "date_closed": _clean(claim.date_closed),
        "status": _clean(claim.status),
        "description": _clean(claim.description),
        "paid_amount": _money(claim.paid_amount),
        "reserve_amount": _money(claim.reserve_amount),
        "total_incurred": _money(claim.total_incurred),
        "litigation": bool(claim.litigation),
        "attorney_assigned": bool(claim.attorney_assigned),
        "suit_filed": bool(claim.suit_filed),
    }


def _account_record(profile: AccountProfile | None, policy_number: str) -> dict[str, Any]:
    if profile is None:
        return {"policy_number": policy_number, "profile_found": False}
    return {
        "profile_found": True,
        "business_name": _clean(profile.business_name),
        "account_number": _clean(profile.account_number),
        "policy_number": _clean(profile.policy_number),
        "carrier_name": _clean(profile.carrier_name),
        "writing_carrier": _clean(profile.writing_carrier),
        "agency_name": _clean(profile.agency_name),
        "effective_date": _clean(profile.effective_date),
        "expiration_date": _clean(profile.expiration_date),
        "evaluation_date": _clean(profile.evaluation_date),
        "line_of_business": _clean(profile.line_of_business),
        "current_premium": _money(profile.current_premium),
        "expiring_premium": _money(profile.expiring_premium),
        "policies": _json_value(profile.policies, []),
        "validation": _json_value(profile.validation, {}),
    }


def _rule_set_for_org(db: Session, organization_id: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    row = (
        db.query(UnderwritingRuleSet)
        .filter(UnderwritingRuleSet.organization_id == organization_id)
        .first()
    )
    if row is None:
        return validate_rules(DEFAULT_RULES), {"name": "LossQ default rules", "version": 0, "custom": False}
    rules = validate_rules(_json_value(row.rules_json, DEFAULT_RULES))
    return rules, {"name": row.name, "version": row.version, "custom": True, "updated_at": row.updated_at}


@router.get("/rules")
def get_underwriting_rules(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("read")),
):
    rules, metadata = _rule_set_for_org(db, current_user["organization_id"])
    return {"rules": rules, **metadata}


@router.put("/rules")
def save_underwriting_rules(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("manage_rules")),
):
    try:
        rules = validate_rules(payload.get("rules") or [])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not rules:
        raise HTTPException(status_code=422, detail="At least one underwriting rule is required.")

    organization_id = current_user["organization_id"]
    row = (
        db.query(UnderwritingRuleSet)
        .filter(UnderwritingRuleSet.organization_id == organization_id)
        .first()
    )
    if row is None:
        row = UnderwritingRuleSet(
            organization_id=organization_id,
            name=_clean(payload.get("name")) or "Organization underwriting rules",
            version=1,
            rules_json=json.dumps(rules),
            updated_by_user_id=current_user.get("user_id"),
        )
        db.add(row)
    else:
        row.name = _clean(payload.get("name")) or row.name
        row.version = int(row.version or 0) + 1
        row.rules_json = json.dumps(rules)
        row.updated_by_user_id = current_user.get("user_id")
    try:
        db.commit()
        db.refresh(row)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Underwriting rules could not be saved.") from exc
    record_audit_event(
        db,
        current_user=current_user,
        action="underwriting_rules_updated",
        resource_type="underwriting_rule_set",
        resource_id=str(row.id),
        details={"version": row.version, "rule_count": len(rules), "name": row.name},
    )
    return {"name": row.name, "version": row.version, "rules": rules}


@router.get("/evaluate")
def evaluate_policy(
    policy_number: str = Query(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("read")),
):
    organization_id = current_user["organization_id"]
    claims = [_claim_record(row) for row in _claims_for_policy(db, organization_id, policy_number)]
    profile = _profile_for_policy(db, organization_id, policy_number)
    account = _account_record(profile, policy_number)
    rules, metadata = _rule_set_for_org(db, organization_id)
    evaluation = evaluate_underwriting_rules(
        claims,
        premium=account.get("current_premium") or account.get("expiring_premium") or 0,
        rules=rules,
    )
    return {"policy_number": policy_number.upper(), "rule_set": metadata, **evaluation}


@router.get("/renewal-comparison")
def renewal_comparison(
    current_policy_number: str = Query(...),
    prior_policy_number: str = Query(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("read")),
):
    organization_id = current_user["organization_id"]
    current = [_claim_record(row) for row in _claims_for_policy(db, organization_id, current_policy_number)]
    prior = [_claim_record(row) for row in _claims_for_policy(db, organization_id, prior_policy_number)]
    return {
        "current_policy_number": current_policy_number.upper(),
        "prior_policy_number": prior_policy_number.upper(),
        **compare_renewal_claims(current, prior),
    }


def _export_contract(
    *, policy_number: str, profile: AccountProfile | None, claims: list[dict[str, Any]],
    rules: list[dict[str, Any]], rule_metadata: dict[str, Any],
) -> dict[str, Any]:
    account = _account_record(profile, policy_number)
    premium = account.get("current_premium") or account.get("expiring_premium") or 0
    return {
        "schema_version": "lossq.loss-intelligence.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "account": account,
        "summary": claim_metrics(claims, premium=premium),
        "underwriting": {
            "rule_set": rule_metadata,
            **evaluate_underwriting_rules(claims, premium=premium, rules=rules),
        },
        "claims": claims,
    }


@router.get("/export")
def export_loss_intelligence(
    policy_number: str = Query(...),
    format: str = Query(default="json", pattern="^(json|csv)$"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("export")),
):
    organization_id = current_user["organization_id"]
    claims = [_claim_record(row) for row in _claims_for_policy(db, organization_id, policy_number)]
    profile = _profile_for_policy(db, organization_id, policy_number)
    rules, rule_metadata = _rule_set_for_org(db, organization_id)
    contract = _export_contract(
        policy_number=policy_number.upper(), profile=profile, claims=claims,
        rules=rules, rule_metadata=rule_metadata,
    )
    record_audit_event(
        db,
        current_user=current_user,
        action="loss_intelligence_exported",
        resource_type="policy",
        resource_id=policy_number.upper(),
        details={"format": format, "claim_count": len(claims), "schema_version": contract["schema_version"]},
    )
    if format == "json":
        return contract

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CLAIM_EXPORT_FIELDS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(claims)
    filename = f"lossq-{policy_number.upper()}-claims.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
