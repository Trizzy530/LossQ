from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Iterable

DATE_PATTERNS = [
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
    r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b",
    r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b",
]

MONEY_RE = re.compile(r"(?<![A-Za-z0-9])\$?\(?-?\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?\)?(?![A-Za-z0-9])")

NON_CLAIM_MARKERS = [
    "subtotal", "sub-total", "total ", "totals", "grand total", "summary", "metric",
    "header", "claim no", "claim number", "policy /", "date of loss", "do not create",
    "do not count", "not a claim", "page ", "generated:", "loss run summary",
]

LOB_ALIASES = {
    "commercial auto": ["commercial auto", "comm auto", "auto", "ca", "garage"],
    "general liability": ["general liability", "general liab", "gl", "premises", "liability"],
    "workers compensation": ["workers comp", "workers compensation", "wc", "work comp"],
    "motor truck cargo": ["motor truck cargo", "cargo"],
    "inland marine": ["inland marine", "inland", "equipment"],
    "property": ["property", "bpp", "building"],
}


def compact_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def normalize_money(value: Any) -> float:
    if value is None:
        return 0.0
    raw = str(value).strip()
    if raw == "":
        return 0.0
    negative = raw.startswith("(") and raw.endswith(")")
    raw = raw.replace("$", "").replace(",", "").replace("(", "").replace(")", "").strip()
    if raw in ["", "-", "."]:
        return 0.0
    try:
        val = float(raw)
        return -val if negative else val
    except Exception:
        return 0.0


def money_values(text: str) -> list[float]:
    values: list[float] = []
    for m in MONEY_RE.findall(text or ""):
        # Ignore bare years as money values.
        clean = m.replace("$", "").replace(",", "").replace("(", "").replace(")", "")
        if re.fullmatch(r"19\d{2}|20\d{2}", clean):
            continue
        values.append(normalize_money(m))
    return values


def find_dates(text: str) -> list[str]:
    dates: list[str] = []
    for pattern in DATE_PATTERNS:
        dates.extend(re.findall(pattern, text or ""))
    return dates


def normalize_date(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    raw = raw.replace(".", "/")
    formats = [
        "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%m-%d-%y",
        "%Y/%m/%d", "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except Exception:
            pass
    return raw


def normalize_claim_number(value: Any) -> str:
    raw = str(value or "").strip().upper().replace("?", "")
    raw = re.sub(r"\s+", "-", raw)
    # OCR cleanup: GL23O049 -> GL230049 only when O appears among digits.
    raw = re.sub(r"(?<=\d)O(?=\d)", "0", raw)
    raw = raw.replace("—", "-").replace("–", "-")
    raw = re.sub(r"-+", "-", raw).strip("-")
    return raw


def normalize_policy_number(value: Any) -> str:
    raw = str(value or "").strip().upper()
    raw = raw.replace("?", "")
    raw = re.sub(r"\s+", "-", raw)
    raw = re.sub(r"(?<=\d)O(?=\d)", "0", raw)
    raw = raw.replace("—", "-").replace("–", "-")
    raw = re.sub(r"-+", "-", raw).strip("-")
    return raw


def is_non_claim_line(text: str) -> bool:
    lower = compact_spaces(text).lower()
    if not lower:
        return True
    return any(marker in lower for marker in NON_CLAIM_MARKERS)


def detect_lob(text: str) -> str:
    lower = compact_spaces(text).lower()
    for canonical, aliases in LOB_ALIASES.items():
        for alias in aliases:
            if re.search(rf"\b{re.escape(alias)}\b", lower):
                return canonical.title()
    return ""


def likely_claim_id_tokens(text: str) -> list[str]:
    tokens = re.findall(r"\b[A-Z]{1,5}[A-Z0-9]*[\s-]?\d{2,4}[A-Z0-9\s-]{1,20}\b", str(text or "").upper())
    cleaned: list[str] = []
    for token in tokens:
        normalized = normalize_claim_number(token)
        if len(normalized) < 5:
            continue
        if any(word in normalized for word in ["POLICY", "ACCT", "ACCOUNT", "TOTAL", "PAGE"]):
            continue
        if normalized not in cleaned:
            cleaned.append(normalized)
    return cleaned


def likely_policy_tokens(text: str) -> list[str]:
    tokens = re.findall(r"\b[A-Z]{1,6}[A-Z0-9]*[\s-]?[A-Z]{0,6}[\s-]?\d{3,}[A-Z0-9\s-]*\b", str(text or "").upper())
    cleaned: list[str] = []
    for token in tokens:
        normalized = normalize_policy_number(token)
        if len(normalized) < 6:
            continue
        if any(word in normalized for word in ["CLAIM", "TOTAL", "PAGE", "DATE"]):
            continue
        if normalized not in cleaned:
            cleaned.append(normalized)
    return cleaned


def unique_by(items: Iterable[dict], key_fn) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for item in items:
        key = str(key_fn(item) or "").strip().upper()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
