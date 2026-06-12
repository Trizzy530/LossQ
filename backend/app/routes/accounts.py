from fastapi import APIRouter, HTTPException

# LOSSQ_DISABLE_LEGACY_ACCOUNTS_UPLOAD_V1
# This legacy upload route is intentionally disabled.
# Production uploads must use the secured upload.py or upload_v2.py routes.

router = APIRouter(prefix="/legacy-accounts", tags=["Disabled Legacy Accounts Upload"])


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def disabled_legacy_accounts_upload(path: str = ""):
    raise HTTPException(
        status_code=410,
        detail="Legacy accounts upload route is disabled. Use the secured LossQ upload routes.",
    )
