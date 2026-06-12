from fastapi import APIRouter, HTTPException

# LOSSQ_DISABLE_PUBLIC_REVIEW_ROUTE_V1
# This old review route is disabled.
# Production extraction review should be implemented through authenticated upload/account routes only.

router = APIRouter(prefix="/review", tags=["Disabled Review"])


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def disabled_review_route(path: str = ""):
    raise HTTPException(
        status_code=410,
        detail="Legacy review route is disabled.",
    )
