from __future__ import annotations

import re
from .utils import compact_spaces, detect_lob, find_dates, likely_policy_tokens, money_values, normalize_date, normalize_policy_number, unique_by


def extract_policies(text: str) -> list[dict]:
    lines = [compact_spaces(line) for line in (text or "").splitlines() if compact_spaces(line)]
    policies: list[dict] = []

    for line in lines:
        lower = line.lower()
        if any(marker in lower for marker in ["claim detail", "detailed claims", "claim no", "loss summary", "supplement table"]):
            continue
        dates = find_dates(line)
        policy_tokens = likely_policy_tokens(line)
        lob = detect_lob(line)
        if not policy_tokens or not lob:
            continue
        # A schedule row usually has at least one date or financial/unit context.
        if len(dates) < 1 and not any(word in lower for word in ["expired", "active", "sales", "payroll", "units", "equip"]):
            continue

        policy_number = normalize_policy_number(policy_tokens[0])
        eff = normalize_date(dates[0]) if len(dates) >= 1 else ""
        exp = normalize_date(dates[1]) if len(dates) >= 2 else ""
        amounts = money_values(line)

        carrier_part = line.split(policy_tokens[0])[0].strip(" -|:") if policy_tokens[0] in line else ""
        carrier = carrier_part
        if carrier.lower() in ["carrier", "co.", "company", "policy type / coverage", "policy type"]:
            carrier = ""

        policies.append({
            "policy_number": policy_number,
            "policy_type": lob,
            "line_coverage": lob,
            "line_of_business": lob,
            "writing_carrier": carrier,
            "carrier": carrier,
            "effective_date": eff,
            "expiration_date": exp,
            "status": "Expired" if "expired" in lower else ("Active" if "active" in lower else ""),
            "total_paid": amounts[-3] if len(amounts) >= 3 else 0,
            "total_reserve": amounts[-2] if len(amounts) >= 3 else 0,
            "total_incurred": amounts[-1] if len(amounts) >= 3 else 0,
        })

    return unique_by(policies, lambda p: p.get("policy_number"))
