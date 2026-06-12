from fastapi import APIRouter, HTTPException

# LOSSQ_DISABLE_PUBLIC_POLICIES_ROUTE_V1
# This old policies route is disabled.
# Production account/policy data must flow through authenticated account-profile and renewal routes.

router = APIRouter(prefix="/policies", tags=["Disabled Policies"])


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def disabled_policies_route(path: str = ""):
    raise HTTPException(
        status_code=410,
        detail="Legacy policies route is disabled.",
    )
