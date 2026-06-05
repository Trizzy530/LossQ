from __future__ import annotations

import re
from datetime import datetime
from typing import Any


DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}|\d{1,2}\.\d{1,2}\.\d{2,4})\b"
)

POLICY_RE = re.compile(
    r"\b[A-Z]{1,6}[-\s]?[A-Z]{1,6}[-\s]?\d{3,8}(?:[-\s]?[A-Z0-9]{1,6})?\b",
    re.I,
)

CLAIM_RE = re.compile(
    r"\b(?:GL|WC|CA|IM|CG|AUTO|AL|BI|PD|PROP)[-\s]?(?:1[0-9]|2[0-9])[-\s]?[A-Z0-9]{3,8}\??\b",
    re.I,
)


def clean_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_money(value: Any) -> float:
    if value is None:
        return 0.0
    raw = str(value).strip()
    if not raw:
        return 0.0
    negative = raw.startswith("(") and raw.endswith(")")
    raw = raw.replace("$", "").replace(",", "").replace("(", "").replace(")", "").strip()
    try:
        amount = float(raw)
        return -amount if negative else amount
    except Exception:
        return 0.0


def money_values(line: str) -> list[float]:
    """
    Extract true financial column values.

    Fixes:
    - claim IDs and policy IDs are scrubbed before money parsing
    - currency values are not double-counted as plain numeric values
    - zeros are kept because reserve columns are often $0
    """
    text = clean_text(line)
    scrubbed = CLAIM_RE.sub(" ", text)
    scrubbed = POLICY_RE.sub(" ", scrubbed)
    scrubbed = DATE_RE.sub(" ", scrubbed)
    values: list[float] = []
    currency_pattern = re.compile(r"\(?\$[\s]*-?\d[\d,]*(?:\.\d{1,2})?\)?")
    scrubbed_without_currency = currency_pattern.sub(" ", scrubbed)
    for match in currency_pattern.finditer(scrubbed):
        values.append(normalize_money(match.group(0)))
    for token in re.findall(
        r"(?<![A-Za-z0-9-])\(?-?\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?\)?(?![A-Za-z0-9-])",
        scrubbed_without_currency,
    ):
        value = normalize_money(token)
        if value == 0 or abs(value) >= 100:
            values.append(value)
    return values


def parse_date(value: Any) -> str | None:
    raw = clean_text(value)
    if not raw:
        return None
    formats = [
        "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%m-%d-%y",
        "%Y-%m-%d", "%Y/%m/%d", "%m.%d.%Y", "%m.%d.%y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except Exception:
            pass
    match = DATE_RE.search(raw)
    if match:
        return parse_date(match.group(0))
    return None


def date_values(line: str) -> list[str]:
    dates = []
    for match in DATE_RE.findall(line or ""):
        parsed = parse_date(match)
        if parsed:
            dates.append(parsed)
    return dates


def normalize_policy_number(value: Any) -> str:
    raw = clean_text(value).upper()
    raw = raw.replace(" ", "-")
    raw = re.sub(r"[^A-Z0-9\-]", "", raw)
    raw = re.sub(r"-{2,}", "-", raw).strip("-")
    return raw


def normalize_claim_number(value: Any) -> str:
    raw = clean_text(value).upper()
    raw = raw.replace("?", "")
    raw = raw.replace(" ", "-")
    raw = re.sub(r"[^A-Z0-9\-]", "", raw)
    raw = re.sub(r"-{2,}", "-", raw).strip("-")
    compact = raw.replace("-", "")
    match = re.match(r"^(GL|WC|CA|IM|CG|AUTO|AL|BI|PD|PROP)(1[0-9]|2[0-9])([A-Z0-9]{3,8})$", compact)
    if match:
        prefix, year, tail = match.groups()
        tail = tail.replace("O", "0")
        raw = f"{prefix}-{year}-{tail}"
    parts = raw.split("-")
    fixed_parts = []
    for part in parts:
        if re.search(r"\d", part) and len(part) >= 3:
            fixed_parts.append(part.replace("O", "0"))
        else:
            fixed_parts.append(part)
    return "-".join(fixed_parts)


def looks_like_total_row(line: str) -> bool:
    lower = clean_text(line).lower()
    if "do not create a claim" in lower:
        return True
    total_words = ["subtotal", "sub-total", "totals", "grand total"]
    if any(word in lower for word in total_words):
        return True
    return False


def looks_like_header_row(line: str) -> bool:
    lower = clean_text(line).lower()
    header_terms = ["claim number", "claim no", "claim id", "policy", "paid", "reserve", "incurred"]
    return sum(term in lower for term in header_terms) >= 3


def find_first(patterns: list[str], text: str, flags: int = re.I) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            for group in match.groups():
                if group:
                    return clean_text(group)
    return ""


def clamp_score(value: int | float) -> int:
    return max(0, min(100, int(round(value))))


def split_lines(text: str) -> list[str]:
    return [clean_text(line) for line in normalize_whitespace(text).splitlines() if clean_text(line)]
