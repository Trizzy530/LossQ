from __future__ import annotations

import hashlib
import io
import re
from typing import Any, Iterable, Mapping


PROFILE_FIELDS = (
    "business_name", "policy_number", "account_number", "carrier_name",
    "writing_carrier", "report_run_date", "effective_date", "expiration_date",
)
CLAIM_FIELDS = (
    "claim_number", "policy_number", "date_of_loss", "date_reported", "status",
    "paid_amount", "reserve_amount", "total_incurred",
)


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _searchable(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", _clean(value).upper())


def _pages_from_content(content: bytes, filename: str) -> tuple[list[str], str]:
    if (filename or "").lower().endswith(".pdf") or content[:4] == b"%PDF":
        try:
            from pypdf import PdfReader

            pages = [page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages]
            if any(page.strip() for page in pages):
                return pages, "embedded_pdf_text"
        except Exception:
            pass

    decoded = content.decode("utf-8", errors="ignore")
    return ([decoded] if decoded.strip() else []), "decoded_text"


def _excerpt(text: str, start: int, end: int, radius: int = 90) -> str:
    return _clean(text[max(0, start - radius):min(len(text), end + radius)])


def _normalized_index(text: str) -> tuple[str, list[int]]:
    normalized: list[str] = []
    source_indexes: list[int] = []
    for index, char in enumerate(text.upper()):
        if char.isalnum():
            normalized.append(char)
            source_indexes.append(index)
    return "".join(normalized), source_indexes


def _value_candidates(value: Any) -> Iterable[str]:
    raw = _clean(value)
    if not raw:
        return ()
    candidates: list[str] = []
    try:
        amount = float(raw.replace("$", "").replace(",", ""))
        if "." in raw or "," in raw or "$" in raw:
            candidates.append(raw)
        candidates.extend([f"{amount:.2f}", f"{amount:,.2f}", f"${amount:,.2f}"])
    except (TypeError, ValueError):
        candidates.append(raw)
    return tuple(dict.fromkeys(candidates))


def locate_source_value(pages: list[str], value: Any) -> dict[str, Any] | None:
    """Return compact source evidence for a value without retaining the whole document."""
    candidates = tuple(_value_candidates(value))
    if not candidates:
        return None

    for page_number, page in enumerate(pages, start=1):
        folded = page.casefold()
        for candidate in candidates:
            start = folded.find(candidate.casefold())
            if start >= 0:
                return {
                    "page": page_number,
                    "excerpt": _excerpt(page, start, start + len(candidate)),
                    "match": "exact",
                    "verified": True,
                }

    for page_number, page in enumerate(pages, start=1):
        normalized_page, source_indexes = _normalized_index(page)
        for candidate in candidates:
            needle = _searchable(candidate)
            if len(needle) < 4:
                continue
            normalized_start = normalized_page.find(needle)
            if normalized_start < 0:
                continue
            start = source_indexes[normalized_start]
            end_index = min(normalized_start + len(needle) - 1, len(source_indexes) - 1)
            end = source_indexes[end_index] + 1
            return {
                "page": page_number,
                "excerpt": _excerpt(page, start, end),
                "match": "normalized",
                "verified": True,
            }
    return None


def _field_evidence(
    pages: list[str], item: Mapping[str, Any], fields: Iterable[str]
) -> dict[str, dict[str, Any]]:
    evidence: dict[str, dict[str, Any]] = {}
    for field in fields:
        match = locate_source_value(pages, item.get(field))
        if match:
            evidence[field] = match
    return evidence


def build_loss_run_evidence(
    *, content: bytes, filename: str, profile: Mapping[str, Any] | None,
    policies: Iterable[Mapping[str, Any]] | None,
    claims: Iterable[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    pages, extraction_method = _pages_from_content(content, filename)
    profile = dict(profile or {})
    policy_rows = [dict(row) for row in (policies or [])]
    claim_rows = [dict(row) for row in (claims or [])]

    profile_evidence = _field_evidence(pages, profile, PROFILE_FIELDS)
    policy_evidence = []
    claim_evidence = []
    matched_fields = len(profile_evidence)
    populated_fields = sum(1 for field in PROFILE_FIELDS if _clean(profile.get(field)))

    policy_fields = ("policy_number", "effective_date", "expiration_date", "carrier", "writing_carrier")
    for index, policy in enumerate(policy_rows):
        fields = _field_evidence(pages, policy, policy_fields)
        matched_fields += len(fields)
        populated_fields += sum(1 for field in policy_fields if _clean(policy.get(field)))
        policy_evidence.append({"index": index, "fields": fields})

    for index, claim in enumerate(claim_rows):
        fields = _field_evidence(pages, claim, CLAIM_FIELDS)
        matched_fields += len(fields)
        populated_fields += sum(1 for field in CLAIM_FIELDS if _clean(claim.get(field)))
        identity = f"{_clean(claim.get('policy_number'))}|{_clean(claim.get('claim_number'))}|{index}"
        claim_evidence.append({
            "index": index,
            "evidence_id": hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16],
            "claim_number": _clean(claim.get("claim_number")),
            "policy_number": _clean(claim.get("policy_number")),
            "fields": fields,
        })

    coverage = round((matched_fields / populated_fields) * 100, 1) if populated_fields else 0.0
    return {
        "version": "1.0", "filename": filename, "page_count": len(pages),
        "extraction_method": extraction_method, "profile": profile_evidence,
        "policies": policy_evidence, "claims": claim_evidence,
        "summary": {
            "matched_fields": matched_fields, "populated_fields": populated_fields,
            "coverage_percent": coverage, "has_source_text": bool(pages),
        },
    }
