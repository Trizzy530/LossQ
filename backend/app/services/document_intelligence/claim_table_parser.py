from __future__ import annotations

import re
from .utils import (
    compact_spaces,
    detect_lob,
    find_dates,
    is_non_claim_line,
    likely_claim_id_tokens,
    likely_policy_tokens,
    money_values,
    normalize_claim_number,
    normalize_date,
    normalize_policy_number,
    unique_by,
)


def _status_from_text(text: str) -> str:
    lower = text.lower()
    if re.search(r"\b(open|reopened|pending)\b", lower) and not re.search(r"closed same day|opened in error / closed|opened then closed", lower):
        return "Open"
    if re.search(r"\b(closed|closed\*|clsd)\b", lower):
        return "Closed"
    return "Open" if "reserve" in lower and any(v > 0 for v in money_values(text)[-2:-1]) else "Closed"


def _description_from_row(row: str, claim_no: str, policy_no: str) -> str:
    desc = row
    for token in [claim_no, policy_no]:
        if token:
            desc = desc.replace(token, " ")
            desc = desc.replace(token.replace("-", " "), " ")
    desc = re.sub(r"\$?\(?-?\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?\)?", " ", desc)
    for d in find_dates(desc):
        desc = desc.replace(d, " ")
    desc = re.sub(r"\b(CLOSED\*?|Closed|closed|OPEN|Open|pending|Pending)\b", " ", desc)
    return compact_spaces(desc)[:700]


def _row_candidates(lines: list[str]) -> list[str]:
    candidates: list[str] = []
    for i, line in enumerate(lines):
        if is_non_claim_line(line):
            continue
        claim_ids = likely_claim_id_tokens(line)
        if not claim_ids:
            continue
        combined = line
        # Some PDFs wrap description and money onto the next line(s).
        for j in range(i + 1, min(i + 3, len(lines))):
            nxt = lines[j]
            if likely_claim_id_tokens(nxt):
                break
            if "policy schedule" in nxt.lower() or "loss summary" in nxt.lower():
                break
            combined = compact_spaces(combined + " " + nxt)
            if len(money_values(combined)) >= 3:
                break
        candidates.append(combined)
    return candidates


def extract_claims(text: str, policies: list[dict] | None = None) -> tuple[list[dict], list[dict]]:
    lines = [compact_spaces(line) for line in (text or "").splitlines() if compact_spaces(line)]
    claims: list[dict] = []
    ignored_rows: list[dict] = []
    known_policies = [normalize_policy_number(p.get("policy_number")) for p in (policies or []) if p.get("policy_number")]

    for line in lines:
        if any(marker in line.lower() for marker in ["subtotal", "totals", "do not create a claim", "do not count as real claim"]):
            ignored_rows.append({"reason": "subtotal_or_total_row", "text": line[:300]})

    for row in _row_candidates(lines):
        lower = row.lower()
        if any(marker in lower for marker in ["subtotal", "totals", "do not create", "do not count"]):
            ignored_rows.append({"reason": "subtotal_or_total_row", "text": row[:300]})
            continue

        claim_tokens = likely_claim_id_tokens(row)
        if not claim_tokens:
            continue
        claim_no = normalize_claim_number(claim_tokens[0])

        policy_no = ""
        policy_tokens = [normalize_policy_number(t) for t in likely_policy_tokens(row)]
        # Prefer a known policy if present in the row.
        for token in policy_tokens:
            if token in known_policies and token != claim_no:
                policy_no = token
                break
        if not policy_no:
            for token in policy_tokens:
                if token != claim_no and not token.startswith(claim_no[:4]):
                    policy_no = token
                    break
        if not policy_no and known_policies:
            # Support rows that say "same as above".
            if "same as above" in lower and claims:
                policy_no = claims[-1].get("policy_number", "")

        dates = find_dates(row)
        amounts = money_values(row)
        if len(amounts) < 2:
            ignored_rows.append({"reason": "not_enough_financial_columns", "text": row[:300]})
            continue

        # Use the last three financial values as paid/reserve/incurred when available.
        if len(amounts) >= 3:
            paid, reserve, incurred = amounts[-3], amounts[-2], amounts[-1]
        else:
            paid, reserve = amounts[-2], 0.0
            incurred = amounts[-1]

        # Reject rows that look like summary lines rather than claim rows.
        if not claim_no or len(claim_no) < 5:
            ignored_rows.append({"reason": "weak_claim_number", "text": row[:300]})
            continue

        lob = detect_lob(row)
        if not lob and policy_no and known_policies:
            for p in policies or []:
                if normalize_policy_number(p.get("policy_number")) == policy_no:
                    lob = p.get("line_of_business") or p.get("policy_type") or p.get("line_coverage") or ""
                    break

        status = _status_from_text(row)
        description = _description_from_row(row, claim_no, policy_no)
        litigation = bool(re.search(r"\b(litigation|litigated|attorney|suit filed|lawsuit)\b", lower))
        flag = "Litigation exposure" if litigation else None

        claims.append({
            "claim_number": claim_no,
            "policy_number": policy_no,
            "line_of_business": lob or "Needs Review",
            "claim_type": lob or "Needs Review",
            "cause_of_loss": "Needs Review",
            "date_of_loss": normalize_date(dates[0]) if dates else "",
            "date_reported": normalize_date(dates[1]) if len(dates) > 1 else "",
            "status": status,
            "description": description,
            "paid_amount": paid,
            "reserve_amount": reserve,
            "total_incurred": incurred if incurred or paid or reserve else paid + reserve,
            "litigation": litigation,
            "litigation_status": "Litigation/attorney indicator found" if litigation else "No litigation indicator found",
            "attorney_assigned": litigation,
            "suit_filed": "suit" in lower or "lawsuit" in lower,
            "flag": flag,
            "parser_confidence": 0.75,
            "raw_row": row[:1000],
        })

    return unique_by(claims, lambda c: c.get("claim_number") + "|" + c.get("policy_number", "")), ignored_rows
