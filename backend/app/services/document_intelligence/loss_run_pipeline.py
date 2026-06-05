from __future__ import annotations

from .text_extractor import extract_text
from .policy_schedule_parser import extract_policies
from .claim_table_parser import extract_claims
from .field_normalizer import extract_profile
from .validation_engine import validate_loss_run
from .confidence_engine import score_document


def parse_loss_run_file(file_path: str, filename: str = "") -> dict:
    text, meta = extract_text(file_path, filename)
    policies = extract_policies(text)
    claims, ignored_rows = extract_claims(text, policies)
    profile = extract_profile(text, policies)
    profile["policies"] = policies

    validation = validate_loss_run(
        text=text,
        profile=profile,
        policies=policies,
        claims=claims,
        ignored_rows=ignored_rows,
        extraction_meta=meta,
    )
    validation = score_document(profile, policies, claims, validation)

    return {
        "profile": profile,
        "policies": policies,
        "claims": claims,
        "validation": validation,
        "raw_text_preview": (text or "")[:8000],
        "extraction_meta": meta,
    }
