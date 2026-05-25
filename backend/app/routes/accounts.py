from fastapi import APIRouter, UploadFile, File, Depends
from sqlalchemy.orm import Session
import shutil
import os
from datetime import datetime

from app.services.parser_service import extract_text_from_pdf, parse_claims_from_text
from app.services.excel_parser_service import parse_claims_from_excel
from app.database import SessionLocal
from app.models.claim import Claim

router = APIRouter(prefix="/upload", tags=["Upload"])

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/loss-run")
async def upload_loss_run(file: UploadFile = File(...), db: Session = Depends(get_db)):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    safe_filename = file.filename.replace(" ", "_")
    file_path = os.path.join(UPLOAD_DIR, f"{timestamp}_{safe_filename}")

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    parsed_claims = []

    lower_name = file.filename.lower()

    if lower_name.endswith(".pdf"):
        text = extract_text_from_pdf(file_path)
        parsed_claims = parse_claims_from_text(text)

    elif lower_name.endswith(".xlsx") or lower_name.endswith(".csv"):
        parsed_claims = parse_claims_from_excel(file_path)

    for claim_data in parsed_claims:
        claim_data.pop("id", None)
        new_claim = Claim(**claim_data)
        db.add(new_claim)

    db.commit()

    return {
        "message": "Loss run uploaded, parsed, and saved successfully",
        "filename": file.filename,
        "stored_path": file_path,
        "content_type": file.content_type,
        "saved_claims": len(parsed_claims),
        "parsed_claims": parsed_claims
    }