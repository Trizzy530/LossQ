"""
Example upload route showing how to use lossq_loss_run_pipeline_v2.py.

Use this as a reference if your current backend/app/routes/upload.py already has
DB save logic you do not want to disrupt. The important part is the import and
parse_loss_run_upload(...) call.
"""

from __future__ import annotations

from fastapi import APIRouter, File, UploadFile

try:
    from app.services.lossq_loss_run_pipeline_v2 import parse_loss_run_upload
except Exception:
    from ..services.lossq_loss_run_pipeline_v2 import parse_loss_run_upload

router = APIRouter(prefix="/upload", tags=["Upload V2 Example"])


@router.post("/loss-run-v2")
async def upload_loss_run_v2(file: UploadFile = File(...)):
    content = await file.read()
    parsed = parse_loss_run_upload(file.filename or "loss_run", content)

    # Your existing upload.py likely saves claims to DB here.
    # Keep that existing save logic. This response shape supports dashboard + review.
    return {
        **parsed,
        "uploaded_files": [file.filename],
        "saved_claims": parsed.get("claim_count", 0),
    }