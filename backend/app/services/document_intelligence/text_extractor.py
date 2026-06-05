from __future__ import annotations

from pathlib import Path


def extract_text_from_pdf(file_path: str) -> tuple[str, dict]:
    """Extract text from a PDF, with optional OCR fallback when dependencies exist."""
    meta = {"method": "pypdf", "ocr_used": False, "warnings": []}
    text_parts: list[str] = []

    try:
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        for index, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
            text_parts.append(f"\n--- PAGE {index} ---\n{page_text}")
    except Exception as exc:
        meta["warnings"].append(f"pypdf extraction failed: {exc}")

    text = "\n".join(text_parts).strip()

    if len(text) < 80:
        try:
            from pdf2image import convert_from_path
            import pytesseract

            images = convert_from_path(file_path, dpi=220)
            ocr_parts: list[str] = []

            for index, image in enumerate(images, start=1):
                ocr_text = pytesseract.image_to_string(image) or ""
                ocr_parts.append(f"\n--- PAGE {index} OCR ---\n{ocr_text}")

            ocr_text = "\n".join(ocr_parts).strip()

            if len(ocr_text) > len(text):
                text = ocr_text
                meta["method"] = "ocr"
                meta["ocr_used"] = True

        except Exception as exc:
            meta["warnings"].append(f"OCR fallback unavailable: {exc}")

    return text, meta


def extract_text(file_path: str, filename: str = "") -> tuple[str, dict]:
    lower = (filename or file_path or "").lower()
    suffix = Path(lower).suffix

    if suffix == ".pdf":
        return extract_text_from_pdf(file_path)

    try:
        raw = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        return raw, {"method": "plain_text", "ocr_used": False, "warnings": []}
    except Exception as exc:
        return "", {"method": "unknown", "ocr_used": False, "warnings": [str(exc)]}