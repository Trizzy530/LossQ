from fastapi import APIRouter, HTTPException

# LOSSQ_DISABLE_UPLOAD_V2_EXAMPLE_V1
# This example upload file is intentionally disabled.
# Production uploads must use the secured upload.py or upload_v2.py routes.

router = APIRouter(prefix="/upload-v2-example", tags=["Disabled Upload V2 Example"])


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def disabled_upload_v2_example(path: str = ""):
    raise HTTPException(
        status_code=410,
        detail="Upload V2 example route is disabled. Use the secured LossQ upload routes.",
    )
