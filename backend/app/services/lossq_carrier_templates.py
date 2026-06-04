"""
LossQ carrier template engine.

Purpose:
- Phase 1: normalize common loss run column names across PDF/Excel/CSV outputs.
- Phase 2: provide carrier-specific aliases and expected columns for major carriers.

This file is intentionally dependency-light so it can be imported by your current
loss_run_pipeline.py without changing auth, DB models, or deployment settings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional


def clean_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


COMMON_COLUMN_ALIASES: Dict[str, List[str]] = {
    "claim_number": [
        "claim_number", "claim_no", "claim", "claim_id", "claim_identifier", "claim_num", "clm_no", "clm",
        "loss_number", "file_number", "claim_reference", "claim_ref",
    ],
    "policy_number": [
        "policy_number", "policy_no", "policy", "policy_num", "pol_no", "pol", "policy_id",
        "contract_number", "account_policy", "policy_symbol_number",
    ],
    "line_of_business": [
        "line_of_business", "lob", "line", "coverage", "coverage_line", "coverage_type", "policy_type",
        "class", "line_coverage", "business_line",
    ],
    "loss_date": [
        "loss_date", "date_of_loss", "dol", "accident_date", "occurrence_date", "incident_date", "date_loss",
    ],
    "reported_date": [
        "reported_date", "date_reported", "report_date", "notice_date", "reported", "claim_reported_date",
    ],
    "status": [
        "status", "claim_status", "open_closed", "claim_state", "open_close", "open_closed_status",
    ],
    "paid_amount": [
        "paid_amount", "paid", "total_paid", "payments", "loss_paid", "indemnity_paid", "expense_paid",
        "paid_loss", "amount_paid",
    ],
    "reserve_amount": [
        "reserve_amount", "reserve", "reserves", "outstanding_reserve", "case_reserve", "loss_reserve",
        "remaining_reserve", "total_reserve",
    ],
    "total_incurred": [
        "total_incurred", "incurred", "total", "gross_incurred", "total_loss_incurred", "loss_incurred",
        "incurred_total", "total_claim_incurred", "net_incurred",
    ],
    "claimant": [
        "claimant", "claimant_name", "employee", "injured_worker", "driver", "third_party", "name",
    ],
    "description": [
        "description", "loss_description", "accident_description", "cause", "cause_of_loss", "notes", "claim_summary",
    ],
}


@dataclass
class CarrierTemplate:
    carrier_key: str
    display_name: str
    aliases: List[str]
    column_aliases: Dict[str, List[str]] = field(default_factory=dict)
    policy_number_patterns: List[str] = field(default_factory=list)
    notes: str = ""

    def all_column_aliases(self) -> Dict[str, List[str]]:
        merged = {k: list(v) for k, v in COMMON_COLUMN_ALIASES.items()}
        for canonical, aliases in self.column_aliases.items():
            merged.setdefault(canonical, [])
            for alias in aliases:
                if alias not in merged[canonical]:
                    merged[canonical].append(alias)
        return merged


CARRIER_TEMPLATES: List[CarrierTemplate] = [
    CarrierTemplate(
        carrier_key="state_auto",
        display_name="State Auto",
        aliases=["state auto", "state automobile", "state auto insurance", "state auto mutual"],
        policy_number_patterns=[r"SA-[A-Z]+-[0-9-]+", r"SA-ACCT-[0-9]+"],
        notes="Supports account policies with child policies by line of coverage.",
    ),
    CarrierTemplate(
        carrier_key="travelers",
        display_name="Travelers",
        aliases=["travelers", "the travelers", "travelers casualty", "travelers indemnity"],
        policy_number_patterns=[r"[A-Z]{1,4}-?[0-9A-Z]{5,}-?[0-9A-Z]*"],
    ),
    CarrierTemplate(
        carrier_key="progressive",
        display_name="Progressive",
        aliases=["progressive", "progressive commercial", "progressive casualty"],
        policy_number_patterns=[r"[0-9]{6,12}", r"[A-Z]{2,5}[0-9]{5,}"],
    ),
    CarrierTemplate(
        carrier_key="liberty_mutual",
        display_name="Liberty Mutual",
        aliases=["liberty mutual", "liberty", "liberty insurance", "lm insurance"],
    ),
    CarrierTemplate(
        carrier_key="cna",
        display_name="CNA",
        aliases=["cna", "continental casualty", "cna insurance"],
    ),
    CarrierTemplate(
        carrier_key="the_hartford",
        display_name="The Hartford",
        aliases=["the hartford", "hartford", "hartford fire", "hartford casualty"],
    ),
    CarrierTemplate(
        carrier_key="zurich",
        display_name="Zurich",
        aliases=["zurich", "zurich american", "zurich north america"],
    ),
    CarrierTemplate(
        carrier_key="nationwide",
        display_name="Nationwide",
        aliases=["nationwide", "nationwide mutual", "nationwide insurance"],
    ),
    CarrierTemplate(
        carrier_key="chubb",
        display_name="Chubb",
        aliases=["chubb", "ace american", "federal insurance company"],
    ),
    CarrierTemplate(
        carrier_key="amtrust",
        display_name="AmTrust",
        aliases=["amtrust", "amtrust north america", "technology insurance company"],
    ),
    CarrierTemplate(
        carrier_key="berkshire",
        display_name="Berkshire Hathaway",
        aliases=["berkshire", "berkshire hathaway", "bi berkshire", "bhhc", "guard insurance"],
    ),
]


def detect_carrier(text: str, fallback: str = "generic") -> CarrierTemplate:
    haystack = str(text or "").lower()
    for template in CARRIER_TEMPLATES:
        if any(alias in haystack for alias in template.aliases):
            return template
    return CarrierTemplate(carrier_key=fallback, display_name="Generic Carrier", aliases=[fallback])


def build_header_map(headers: Iterable[Any], template: Optional[CarrierTemplate] = None) -> Dict[str, str]:
    """Return mapping from raw header -> canonical field name."""
    carrier_template = template or CarrierTemplate("generic", "Generic Carrier", ["generic"])
    aliases = carrier_template.all_column_aliases()
    alias_lookup: Dict[str, str] = {}

    for canonical, values in aliases.items():
        alias_lookup[clean_key(canonical)] = canonical
        for value in values:
            alias_lookup[clean_key(value)] = canonical

    header_map: Dict[str, str] = {}
    for header in headers:
        cleaned = clean_key(header)
        if cleaned in alias_lookup:
            header_map[str(header)] = alias_lookup[cleaned]
            continue

        # Fuzzy fallback for headers like "Total Incurred Amount".
        for alias, canonical in alias_lookup.items():
            if alias and alias in cleaned:
                header_map[str(header)] = canonical
                break

    return header_map


def normalize_row(row: Dict[str, Any], template: Optional[CarrierTemplate] = None) -> Dict[str, Any]:
    header_map = build_header_map(row.keys(), template)
    normalized: Dict[str, Any] = {}

    for raw_key, value in row.items():
        canonical = header_map.get(str(raw_key), clean_key(raw_key))
        normalized[canonical] = value

    return normalized


def extract_policy_numbers(text: str, template: Optional[CarrierTemplate] = None) -> List[str]:
    patterns = []
    if template:
        patterns.extend(template.policy_number_patterns)
    patterns.extend([
        r"[A-Z]{2,6}-[A-Z]{2,10}-[0-9]{3,}-[0-9]{2}",
        r"[A-Z]{2,6}-ACCT-[0-9]{3,}",
        r"[A-Z]{1,5}[0-9]{5,}[A-Z0-9-]*",
    ])

    found: List[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, str(text or ""), flags=re.IGNORECASE):
            value = str(match).strip().upper()
            if value and value not in found:
                found.append(value)
    return found