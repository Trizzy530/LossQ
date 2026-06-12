from fastapi import APIRouter, UploadFile, File, HTTPException
import shutil
import re
import os
from pathlib import Path
from datetime import datetime

from app.services.parser_service import extract_text_from_pdf, parse_claims_from_text
from app.services.excel_parser_service import parse_claims_from_excel
from app.routes.summary import build_underwriting_intelligence

router = APIRouter(prefix="/demo", tags=["Demo"])

DEMO_UPLOAD_DIR = "demo_uploads"
os.makedirs(DEMO_UPLOAD_DIR, exist_ok=True)

# LOSSQ_DEMO_UPLOAD_SECURITY_V1
MAX_DEMO_UPLOAD_BYTES = int(os.getenv("LOSSQ_DEMO_MAX_UPLOAD_MB", "10")) * 1024 * 1024
ALLOWED_DEMO_EXTENSIONS = {".pdf", ".csv", ".xlsx"}
ALLOWED_DEMO_CONTENT_TYPES = {
    "application/pdf",
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream",
}


def validate_demo_upload_file(file: UploadFile) -> str:
    original_name = Path(file.filename or "").name
    if not original_name:
        raise HTTPException(status_code=400, detail="A filename is required.")

    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_DEMO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported demo file type. Upload PDF, CSV, or XLSX.")

    content_type = (file.content_type or "").lower().strip()
    if content_type and content_type not in ALLOWED_DEMO_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported demo upload content type.")

    try:
        file.file.seek(0, os.SEEK_END)
        file_size = file.file.tell()
        file.file.seek(0)
    except Exception:
        raise HTTPException(status_code=400, detail="Could not validate uploaded file size.")

    if file_size <= 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    if file_size > MAX_DEMO_UPLOAD_BYTES:
        max_mb = MAX_DEMO_UPLOAD_BYTES // (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"Demo upload is too large. Maximum size is {max_mb} MB.")

    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", original_name).strip("._")
    if not safe_name:
        safe_name = f"lossq_demo_upload{extension}"

    return safe_name



class DemoClaim:
    def __init__(self, data):
        self.claim_number = data.get("claim_number", "")
        self.policy_id = data.get("policy_id", 1)
        self.line_of_business = data.get("line_of_business", "Unknown")
        self.claim_type = data.get("claim_type", "Unknown")
        self.cause_of_loss = data.get("cause_of_loss", "Needs Review")
        self.claimant_type = data.get("claimant_type", "Needs Review")
        self.date_of_loss = data.get("date_of_loss", "Needs Review")
        self.status = data.get("status", "Open")
        self.description = data.get("description", "")
        self.paid_amount = data.get("paid_amount", 0)
        self.reserve_amount = data.get("reserve_amount", 0)
        self.total_incurred = data.get("total_incurred", 0)
        self.litigation = data.get("litigation", False)
        self.litigation_status = data.get("litigation_status", "None")
        self.attorney_assigned = data.get("attorney_assigned", False)
        self.suit_filed = data.get("suit_filed", False)
        self.venue_state = data.get("venue_state", "Needs Review")
        self.injury_type = data.get("injury_type", "Needs Review")
        self.flag = data.get("flag", None)


def parse_demo_file(file_path: str, filename: str):
    name = filename.lower()

    if name.endswith(".pdf"):
        text = extract_text_from_pdf(file_path)
        return parse_claims_from_text(text)

    if name.endswith(".csv") or name.endswith(".xlsx"):
        return parse_claims_from_excel(file_path)

    raise HTTPException(
        status_code=400,
        detail="Unsupported file type. Upload PDF, CSV, or XLSX."
    )


@router.post("/analyze")
async def demo_analyze(file: UploadFile = File(...)):
    try:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        safe_filename = validate_demo_upload_file(file)
        file_path = os.path.join(DEMO_UPLOAD_DIR, f"{timestamp}_{safe_filename}")

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        parsed_claims = parse_demo_file(file_path, safe_filename)

        demo_claims = [DemoClaim(claim) for claim in parsed_claims]

        intelligence = build_underwriting_intelligence(demo_claims)

        return {
            "message": "Demo analysis complete",
            "filename": file.filename,
            "claims_found": len(parsed_claims),
            "claims": parsed_claims,
            "analysis": intelligence,
        }

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Demo failed: {str(error)}"
        )