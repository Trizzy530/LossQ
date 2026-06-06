from __future__ import annotations

from pathlib import Path


def _looks_like_weak_pdf_text(text: str) -> bool:
    cleaned = (text or "").strip()
    if len(cleaned) < 120:
        return True

    alpha_numeric = sum(1 for char in cleaned if char.isalnum())
    return alpha_numeric < 80


def extract_text_from_pdf(file_path: str) -> tuple[str, dict]:
    # Extract text from a PDF, with OCR fallback for image-only/scanned loss runs.
    meta = {
        "method": "pypdf",
        "ocr_used": False,
        "warnings": [],
        "page_count": 0,
        "embedded_text_length": 0,
        "ocr_text_length": 0,
    }

    text_parts: list[str] = []

    try:
        from pypdf import PdfReader

        reader = PdfReader(file_path)
        meta["page_count"] = len(reader.pages)

        for index, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
            text_parts.append(f"\n--- PAGE {index} ---\n{page_text}")
    except Exception as exc:
        meta["warnings"].append(f"pypdf extraction failed: {exc}")

    text = "\n".join(text_parts).strip()
    meta["embedded_text_length"] = len(text)

    if _looks_like_weak_pdf_text(text):
        try:
            from pdf2image import convert_from_path
            import pytesseract

            images = convert_from_path(file_path, dpi=300)
            meta["page_count"] = max(meta.get("page_count") or 0, len(images))

            ocr_parts: list[str] = []
            config = "--oem 3 --psm 6 -c preserve_interword_spaces=1"

            for index, image in enumerate(images, start=1):
                ocr_text = pytesseract.image_to_string(image, config=config) or ""

                if len(ocr_text.strip()) < 40:
                    ocr_text = pytesseract.image_to_string(
                        image,
                        config="--oem 3 --psm 4 -c preserve_interword_spaces=1",
                    ) or ocr_text

                ocr_parts.append(f"\n--- PAGE {index} OCR ---\n{ocr_text}")

            ocr_text = "\n".join(ocr_parts).strip()
            meta["ocr_text_length"] = len(ocr_text)

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
