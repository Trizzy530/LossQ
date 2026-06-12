from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Body

try:
    from app.services.lossq_validation import validate_loss_run_payload
except Exception:
    from ..services.lossq_validation import validate_loss_run_payload

router = APIRouter(prefix="/review", tags=["Manual Review"])

_LAST_REVIEW_PACKET: Dict[str, Any] = {}


@router.post("/confirm")
async def confirm_reviewed_extraction(payload: Dict[str, Any] = Body(...)):
    """
    Phase 4 endpoint.

    This accepts reviewed profile/policy/claim data from the frontend review page.
    It intentionally does not assume your exact database models, so it is safe to
    add first. Later you can wire this endpoint into your Claim/Policy/Profile DB
    save functions after the UI is confirmed working.
    """
    profile = payload.get("profile") or {}
    policies: List[Dict[str, Any]] = payload.get("policies") or profile.get("policies") or []
    claims: List[Dict[str, Any]] = payload.get("claims") or []
    document_totals = payload.get("document_totals") or {}

    validation = validate_loss_run_payload(profile, policies, claims, document_totals)

    reviewed_packet = {
        "status": "review_confirmed",
        "profile": profile,
        "policies": policies,
        "claims": claims,
        "validation": validation,
        "saved_claims": len(claims),
        "policy_count": len(policies),
        "claim_count": len(claims),
        "total_incurred": validation.get("calculated_total_incurred", 0),
        "source": payload.get("source") or "manual_review",
    }

    _LAST_REVIEW_PACKET.clear()
    _LAST_REVIEW_PACKET.update(reviewed_packet)

    return reviewed_packet


@router.get("/latest")
async def latest_reviewed_extraction():
    if not _LAST_REVIEW_PACKET:
        return {
            "status": "empty",
            "message": "No reviewed extraction has been confirmed in this server session.",
        }
    return _LAST_REVIEW_PACKET