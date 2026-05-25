from fastapi import APIRouter, UploadFile, File, Depends, Form
from sqlalchemy.orm import Session
import shutil
import os
from datetime import datetime
from typing import List

from app.database import SessionLocal
from app.auth_utils import get_current_user
from app.models.claim import Claim
from app.models.upload_history import UploadHistory
from app.services.parser_service import extract_text_from_pdf, parse_claims_from_text
from app.services.excel_parser_service import parse_claims_from_excel

router = APIRouter(prefix="/upload", tags=["Upload"])

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def parse_file(file_path: str, filename: str):
    lower_name = filename.lower()

    if lower_name.endswith(".pdf"):
        text = extract_text_from_pdf(file_path)
        return parse_claims_from_text(text)

    if lower_name.endswith(".csv") or lower_name.endswith(".xlsx"):
        return parse_claims_from_excel(file_path)

    return []


@router.post("/loss-run")
async def upload_loss_run(
    file: UploadFile = File(...),
    policy_number: str = Form(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return await save_uploaded_files([file], policy_number, db, current_user)


@router.post("/loss-runs")
async def upload_multiple_loss_runs(
    files: List[UploadFile] = File(...),
    policy_number: str = Form(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return await save_uploaded_files(files, policy_number, db, current_user)


async def save_uploaded_files(files, policy_number, db, current_user):
    total_saved = 0
    uploaded_files = []

    for file in files:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        safe_filename = file.filename.replace(" ", "_")
        file_path = os.path.join(UPLOAD_DIR, f"{timestamp}_{safe_filename}")

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        parsed_claims = parse_file(file_path, file.filename)

        for claim_data in parsed_claims:
            claim_data["organization_id"] = current_user["organization_id"]
            claim_data["uploaded_by_user_id"] = current_user["user_id"]
            claim_data["uploaded_at"] = datetime.now().isoformat()
            claim_data["policy_number"] = policy_number
            db.add(Claim(**claim_data))

        upload_record = UploadHistory(
            filename=file.filename,
            stored_path=file_path,
            content_type=file.content_type,
            claims_saved=len(parsed_claims),
            uploaded_at=datetime.now().isoformat(),
            uploaded_by_user_id=current_user["user_id"],
            organization_id=current_user["organization_id"],
        )

        db.add(upload_record)

        total_saved += len(parsed_claims)

        uploaded_files.append({
            "filename": file.filename,
            "claims_saved": len(parsed_claims),
            "policy_number": policy_number,
        })

    db.commit()

    return {
        "message": "Loss run file(s) uploaded successfully",
        "saved_claims": total_saved,
        "policy_number": policy_number,
        "uploaded_files": uploaded_files,
    }