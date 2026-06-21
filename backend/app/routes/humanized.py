from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.routes.auth import get_current_user
from app.services.humanized_narrative import build_humanized_narrative


# LOSSQ_HUMANIZED_NARRATIVE_ROUTE_V1

router = APIRouter(prefix="/humanized", tags=["Humanized Narrative"])


class HumanizedNarrativeRequest(BaseModel):
    profile: Dict[str, Any] = Field(default_factory=dict)
    claims: List[Dict[str, Any]] = Field(default_factory=list)
    policies: List[Dict[str, Any]] = Field(default_factory=list)
    exposure_inputs: Dict[str, Any] = Field(default_factory=dict)
    source_context: Optional[str] = ""
    website_text: Optional[str] = ""
    scope_of_work: Optional[str] = ""


@router.post("/narrative")
def generate_humanized_narrative(
    payload: HumanizedNarrativeRequest,
    current_user: dict = Depends(get_current_user),
):
    return build_humanized_narrative(
        profile=payload.profile,
        claims=payload.claims,
        policies=payload.policies,
        exposure_inputs=payload.exposure_inputs,
        source_context=payload.source_context or "",
        website_text=payload.website_text or "",
        scope_of_work=payload.scope_of_work or "",
    )
