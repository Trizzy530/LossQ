
from __future__ import annotations

import re
from io import BytesIO
from typing import Any, Dict, List, Optional

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None


DATE_RE = re.compile(r"\b(?:\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})\b")
MONEY_TOKEN_RE = re.compile(r"\(?\$[\s]*[0-9]{1,3}(?:,[0-9]{3})*(?:\.\d{2})?\)?|\(?\$[\s]*[0-9]+(?:\.\d{2})?\)?")
CLAIM_RE = re.compile(r"\b(?:AL|GL|WC|CG|AUTO|CARGO|MT)[-\s][A-Z0-9]{2,25}\b", re.IGNORECASE)
POLICY_RE = re.compile(r"\b[A-Z]{2,6}[-\s]*(?:AL|GL|WC|CG|AUTO|CARGO|MT)[-\s]*[A-Z0-9]{3,12}(?:[-\s]*\d{1,4})?\b", re.IGNORECASE)

FAKE_CLAIM_VALUES = {
    "AUTO-LIABILITY", "AUTO LIABILITY",
    "GENERAL-LIABILITY", "GENERAL LIABILITY",
    "WORKERS-COMP", "WORKERS COMP", "WORKERS-COMPENSATION", "WORKERS COMPENSATION",
    "MOTOR-TRUCK-CARGO", "MOTOR TRUCK CARGO",
    "CARGO", "CLAIM-NO", "CLAIM-NUMBER", "LOSS-RUN",
    "GL-GATE", "AL-GATE", "WC-GATE", "CG-GATE",
}


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalize_policy(value: Any) -> str:
    text = _clean_text(value).upper().replace(" ", "-")
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def _money(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    neg = text.startswith("(") and text.endswith(")")
    text = text.replace("$", "").replace(",", "").replace("(", "").replace(")", "").strip()

    try:
        amount = float(text)
        return -amount if neg else amount
    except Exception:
        return 0.0


def _pdf_text(filename: str, content: Optional[bytes]) -> str:
    if not content or not filename.lower().endswith(".pdf") or PdfReader is None:
        return ""

    try:
        reader = PdfReader(BytesIO(content))
        parts = []
        for page_index, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
            if page_text.strip():
                parts.append(f"--- PAGE {page_index} ---\n{page_text}")
        return "\n\n".join(parts)
    except Exception as exc:
        print("LossQ cleanup PDF text fallback failed:", str(exc))
        return ""


def _raw_text(parsed: Dict[str, Any], filename: str, content: Optional[bytes]) -> str:
    profile = _as_dict(parsed.get("profile"))
    account = _as_dict(parsed.get("account"))

    candidates = [
        parsed.get("raw_text_preview"),
        parsed.get("raw_text"),
        parsed.get("text"),
        parsed.get("extracted_text"),
        profile.get("raw_text_preview"),
        profile.get("raw_text"),
        account.get("raw_text_preview"),
        account.get("raw_text"),
    ]

    for item in candidates:
        if isinstance(item, str) and item.strip():
            return item.strip()

    return _pdf_text(filename, content)


def _label_value(raw_text: str, labels: List[str]) -> str:
    for label in labels:
        match = re.search(rf"{re.escape(label)}\s*[:\-]\s*(.+?)(?:\n|$)", raw_text, re.IGNORECASE)
        if match:
            value = _clean_text(match.group(1))
            if value:
                return value
    return ""


def _business_name(raw_text: str) -> str:
    return _label_value(raw_text, ["Named Insured", "Insured Name", "Business Name", "Account Name", "Applicant"])


def _carrier_name(raw_text: str) -> str:
    return _label_value(raw_text, ["Writing Carrier", "Carrier Name", "Insurer Name", "Insurer", "Insurance Company"])


def _lob_from_text(text: str) -> str:
    upper = text.upper()
    if "WC" in upper or "WORKERS" in upper:
        return "Workers Comp"
    if "GL" in upper or "GENERAL" in upper:
        return "General Liability"
    if "CG" in upper or "CARGO" in upper or "MOTOR TRUCK" in upper:
        return "Motor Truck Cargo"
    if "AL" in upper or "AUTO" in upper:
        return "Auto Liability"
    return "Unknown"


def _extract_policies(raw_text: str) -> List[Dict[str, Any]]:
    compact = re.sub(r"\s+", " ", raw_text or "")
    policies: List[Dict[str, Any]] = []
    seen = set()

    generic = re.compile(r"\b([A-Z]{2,6})[-\s]*(AL|GL|WC|CG|AUTO|CARGO|MT)[-\s]*([A-Z0-9]{3,12})(?:[-\s]*(\d{1,4}))?\b", re.IGNORECASE)

    for match in generic.finditer(compact):
        carrier_prefix = match.group(1).upper()
        code = match.group(2).upper()
        middle = match.group(3).upper()
        suffix = match.group(4)

        if code == "AUTO":
            code = "AL"
        if code in {"CARGO", "MT"}:
            code = "CG"

        if suffix:
            policy_number = f"{carrier_prefix}-{code}-{middle}-{suffix.zfill(2)}"
        else:
            policy_number = f"{carrier_prefix}-{code}-{middle}"

        policy_number = _normalize_policy(policy_number)

        fake_policy_values = {"GENERAL-LIABILITY", "AUTO-LIABILITY", "WORKERS-COMP", "MOTOR-TRUCK-CARGO", "MUTUAL-INSURANCE"}
        if policy_number in fake_policy_values:
            continue

        if policy_number not in seen:
            policies.append({
                "policy_number": policy_number,
                "line_of_business": _lob_from_text(policy_number),
            })
            seen.add(policy_number)

    return policies


def _policy_for_claim(claim_number: str, policies: List[Dict[str, Any]]) -> str:
    upper = claim_number.upper()

    for policy in policies:
        policy_number = _normalize_policy(policy.get("policy_number"))
        if upper.startswith("AL-") and "-AL-" in policy_number:
            return policy_number
        if upper.startswith("GL-") and "-GL-" in policy_number:
            return policy_number
        if upper.startswith("WC-") and "-WC-" in policy_number:
            return policy_number
        if upper.startswith(("CG-", "MT-", "CARGO-")) and "-CG-" in policy_number:
            return policy_number

    return policies[0]["policy_number"] if policies else ""


def _inside_policy(line: str, match: re.Match[str]) -> bool:
    start, end = match.start(), match.end()
    for policy_match in POLICY_RE.finditer(line):
        if policy_match.start() <= start and end <= policy_match.end():
            return True
    before = line[max(0, start - 4):start].upper()
    after = line[end:end + 4].upper()
    if before.endswith(("GP-", "GP ")):
        return True
    if re.match(r"[-\s]?\d{1,4}\b", after):
        return True
    return False


def _extract_claims_from_text(raw_text: str, policies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not raw_text:
        return []

    normalized = raw_text.replace("\r", "\n")
    lines = [_clean_text(line) for line in normalized.splitlines() if _clean_text(line)]
    claims: List[Dict[str, Any]] = []
    seen = set()

    for index, line in enumerate(lines):
        matches = list(CLAIM_RE.finditer(line))
        if not matches:
            continue

        for match in matches:
            if _inside_policy(line, match):
                continue

            claim_number = _clean_text(match.group(0)).upper().replace(" ", "-")
            claim_number = re.sub(r"-+", "-", claim_number)

            if claim_number in FAKE_CLAIM_VALUES:
                continue
            if claim_number in seen:
                continue

            window_lines = lines[index:index + 5]
            block = " ".join(window_lines)

            if claim_number in FAKE_CLAIM_VALUES:
                continue

            money_values = [_money(m.group(0)) for m in MONEY_TOKEN_RE.finditer(block)]
            money_values = [m for m in money_values if m != 0]

            if not money_values:
                continue

            dates = DATE_RE.findall(block)
            policy_number = _policy_for_claim(claim_number, policies)
            lob = _lob_from_text(f"{claim_number} {policy_number}")

            total_incurred = money_values[-1]
            reserve = money_values[-2] if len(money_values) >= 2 else 0.0
            paid = money_values[-3] if len(money_values) >= 3 else max(total_incurred - reserve, 0.0)

            status = "Closed"
            if re.search(r"\bopen\b", block, re.IGNORECASE) or reserve > 0:
                status = "Open"
            elif re.search(r"\bclosed\b", block, re.IGNORECASE):
                status = "Closed"

            description = block
            description = CLAIM_RE.sub("", description)
            description = DATE_RE.sub("", description)
            description = MONEY_TOKEN_RE.sub("", description)
            description = re.sub(r"\b(open|closed|pending)\b", "", description, flags=re.IGNORECASE)
            description = _clean_text(description)

            claims.append({
                "claim_number": claim_number,
                "policy_number": policy_number,
                "line_of_business": lob,
                "date_of_loss": dates[0] if dates else "",
                "date_reported": dates[1] if len(dates) > 1 else "",
                "description": description,
                "loss_description": description,
                "paid": round(paid, 2),
                "reserve": round(reserve, 2),
                "total_incurred": round(total_incurred, 2),
                "status": status,
            })
            seen.add(claim_number)

    return claims


def _clean_existing_claims(claims: Any, policies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(claims, list):
        return []

    cleaned = []
    seen = set()
    policy_numbers = {_normalize_policy(p.get("policy_number")) for p in policies}

    for item in claims:
        if not isinstance(item, dict):
            continue

        claim = dict(item)
        claim_number = _clean_text(claim.get("claim_number") or claim.get("claimNumber")).upper().replace(" ", "-")

        if not claim_number:
            continue
        if claim_number in FAKE_CLAIM_VALUES:
            continue
        if claim_number in policy_numbers:
            continue
        if claim_number in seen:
            continue

        total = _money(claim.get("total_incurred") or claim.get("incurred") or claim.get("amount"))
        paid = _money(claim.get("paid") or claim.get("paid_amount"))
        reserve = _money(claim.get("reserve") or claim.get("reserve_amount"))

        if total == 0 and paid == 0 and reserve == 0:
            continue

        policy_number = _normalize_policy(claim.get("policy_number") or claim.get("policyNumber"))
        if not policy_number or policy_number in {"GENERAL-LIABILITY", "AUTO-LIABILITY", "WORKERS-COMP", "MUTUAL-INSURANCE"}:
            policy_number = _policy_for_claim(claim_number, policies)

        claim["claim_number"] = claim_number
        claim["policy_number"] = policy_number
        claim["line_of_business"] = claim.get("line_of_business") or _lob_from_text(f"{claim_number} {policy_number}")
        claim["paid"] = round(paid, 2)
        claim["reserve"] = round(reserve, 2)
        claim["total_incurred"] = round(total, 2)
        claim["status"] = claim.get("status") or ("Open" if reserve > 0 else "Closed")

        cleaned.append(claim)
        seen.add(claim_number)

    return cleaned


def _claim_total(claims: List[Dict[str, Any]]) -> float:
    return round(sum(_money(claim.get("total_incurred")) for claim in claims), 2)


def cleanup_loss_run_extraction(
    parsed: Dict[str, Any],
    filename: str = "",
    content: bytes | None = None,
) -> Dict[str, Any]:
    if not isinstance(parsed, dict):
        return parsed

    raw_text = _raw_text(parsed, filename or "", content)

    if raw_text:
        parsed["raw_text_preview"] = raw_text[:12000]

    business_name = _business_name(raw_text) if raw_text else ""
    carrier_name = _carrier_name(raw_text) if raw_text else ""
    policies = _extract_policies(raw_text) if raw_text else []

    existing_claims = parsed.get("claims") or parsed.get("parsed_claims") or parsed.get("claim_rows") or parsed.get("losses") or []
    cleaned_existing = _clean_existing_claims(existing_claims, policies)
    rebuilt_claims = _extract_claims_from_text(raw_text, policies) if raw_text else []

    final_claims = rebuilt_claims if len(rebuilt_claims) >= len(cleaned_existing) else cleaned_existing

    profile = parsed.get("profile") if isinstance(parsed.get("profile"), dict) else {}
    account = parsed.get("account") if isinstance(parsed.get("account"), dict) else {}

    if business_name:
        parsed["business_name"] = business_name
        parsed["named_insured"] = business_name
        profile["business_name"] = business_name
        profile["named_insured"] = business_name
        account["business_name"] = business_name

    if carrier_name:
        parsed["carrier_name"] = carrier_name
        parsed["writing_carrier"] = carrier_name
        profile["carrier_name"] = carrier_name
        profile["writing_carrier"] = carrier_name
        account["carrier_name"] = carrier_name

    if policies:
        parsed["policies"] = policies
        profile["policies"] = policies
        parsed["policy_count"] = len(policies)

        current_policy = _normalize_policy(parsed.get("policy_number"))
        bad_policy_values = {
            "", "UPLOAD", "MUTUAL-INSURANCE", "GENERAL-LIABILITY",
            "AUTO-LIABILITY", "WORKERS-COMP", "MOTOR-TRUCK-CARGO", "CARGO",
        }

        if current_policy.startswith("UPLOAD-") or current_policy in bad_policy_values:
            parsed["policy_number"] = policies[0]["policy_number"]
            profile["policy_number"] = policies[0]["policy_number"]
            account["policy_number"] = policies[0]["policy_number"]

    if final_claims:
        parsed["claims"] = final_claims
        parsed["parsed_claims"] = final_claims
        parsed["claim_count"] = len(final_claims)
        parsed["total_incurred"] = _claim_total(final_claims)

    parsed["profile"] = profile
    parsed["account"] = account

    return parsed
