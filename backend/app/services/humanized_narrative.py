from __future__ import annotations

from typing import Any, Dict, List
import re


# LOSSQ_HUMANIZED_NARRATIVE_ENGINE_V1


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).strip(" :-|")


def _money(value: Any) -> float:
    raw = _clean(value)
    if not raw:
        return 0.0

    raw = (
        raw.replace("$", "")
        .replace(",", "")
        .replace("(", "-")
        .replace(")", "")
        .strip()
    )

    try:
        return float(raw)
    except Exception:
        return 0.0


def _money_display(value: Any) -> str:
    amount = _money(value)
    return "${:,.0f}".format(amount)


def _first(*values: Any) -> str:
    for value in values:
        cleaned = _clean(value)
        if cleaned:
            return cleaned
    return ""


def _status_is_open(value: Any) -> bool:
    status = _clean(value).lower()
    if not status:
        return False
    return any(token in status for token in ["open", "pending", "active", "reopened"])


def _claim_total(claim: Dict[str, Any]) -> float:
    incurred = _money(
        claim.get("total_incurred")
        or claim.get("incurred")
        or claim.get("total")
        or claim.get("total_amount")
    )

    if incurred > 0:
        return incurred

    return _money(claim.get("paid_amount") or claim.get("paid")) + _money(
        claim.get("reserve_amount") or claim.get("reserve")
    )


def _claim_reserve(claim: Dict[str, Any]) -> float:
    return _money(claim.get("reserve_amount") or claim.get("reserve"))


def _claim_line(claim: Dict[str, Any]) -> str:
    return _first(
        claim.get("line_of_business"),
        claim.get("claim_type"),
        claim.get("policy_type"),
        claim.get("coverage"),
        "Unknown line",
    )


def _claim_number(claim: Dict[str, Any]) -> str:
    return _first(claim.get("claim_number"), claim.get("claim_no"), "Unnumbered claim")


def _claim_description(claim: Dict[str, Any]) -> str:
    return _first(
        claim.get("description"),
        claim.get("claim_description"),
        claim.get("loss_description"),
        claim.get("cause_of_loss"),
        claim.get("notes"),
    )


def _policy_line(policy: Dict[str, Any]) -> str:
    return _first(
        policy.get("line_of_business"),
        policy.get("policy_type"),
        policy.get("coverage"),
        policy.get("line"),
        "Policy",
    )


def _policy_number(policy: Dict[str, Any]) -> str:
    return _first(policy.get("policy_number"), policy.get("policy"), "")


def _risk_level(total_claims: int, open_claims: int, total_incurred: float, reserve_total: float) -> str:
    if total_claims >= 8 or open_claims >= 4 or total_incurred >= 250000 or reserve_total >= 150000:
        return "Critical"

    if total_claims >= 5 or open_claims >= 2 or total_incurred >= 100000 or reserve_total >= 50000:
        return "High"

    if total_claims >= 2 or open_claims >= 1 or total_incurred >= 25000:
        return "Moderate"

    return "Low"


def _tone_from_risk(risk_level: str) -> str:
    if risk_level == "Critical":
        return "requires a direct underwriting explanation before renewal or market submission"
    if risk_level == "High":
        return "should be positioned carefully with claim context and corrective action"
    if risk_level == "Moderate":
        return "is manageable but still needs a clear explanation of the loss activity"
    return "appears favorable from a loss activity standpoint, subject to normal underwriting review"


def _top_claims(claims: List[Dict[str, Any]], limit: int = 3) -> List[Dict[str, Any]]:
    sorted_claims = sorted(claims, key=_claim_total, reverse=True)
    return sorted_claims[:limit]


def _line_mix(claims: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    mix: Dict[str, Dict[str, Any]] = {}

    for claim in claims:
        line = _claim_line(claim)
        if line not in mix:
            mix[line] = {"claim_count": 0, "total_incurred": 0.0, "open_claims": 0}

        mix[line]["claim_count"] += 1
        mix[line]["total_incurred"] += _claim_total(claim)

        if _status_is_open(claim.get("status") or claim.get("claim_status")):
            mix[line]["open_claims"] += 1

    return mix


def _sentence_list(items: List[str]) -> str:
    cleaned = [_clean(item) for item in items if _clean(item)]
    if not cleaned:
        return ""

    if len(cleaned) == 1:
        return cleaned[0]

    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"

    return ", ".join(cleaned[:-1]) + f", and {cleaned[-1]}"


def _business_description(profile: Dict[str, Any], policies: List[Dict[str, Any]], claims: List[Dict[str, Any]]) -> str:
    explicit = _first(
        profile.get("business_description"),
        profile.get("operations"),
        profile.get("scope_of_work"),
        profile.get("business_operations"),
        profile.get("industry"),
    )

    if explicit:
        return explicit

    policy_lines = [_policy_line(policy) for policy in policies if _policy_line(policy)]
    claim_lines = [_claim_line(claim) for claim in claims if _claim_line(claim)]

    unique_lines = []
    for line in policy_lines + claim_lines:
        if line and line not in unique_lines and line.lower() != "policy":
            unique_lines.append(line)

    if unique_lines:
        return f"an account with { _sentence_list(unique_lines[:5]) } exposure"

    return "a commercial insurance account"


def build_humanized_narrative(
    profile: Dict[str, Any] | None = None,
    claims: List[Dict[str, Any]] | None = None,
    policies: List[Dict[str, Any]] | None = None,
    exposure_inputs: Dict[str, Any] | None = None,
    source_context: str = "",
    website_text: str = "",
    scope_of_work: str = "",
) -> Dict[str, Any]:
    profile = profile if isinstance(profile, dict) else {}
    claims = claims if isinstance(claims, list) else []
    policies = policies if isinstance(policies, list) else []
    exposure_inputs = exposure_inputs if isinstance(exposure_inputs, dict) else {}

    business_name = _first(
        profile.get("business_name"),
        profile.get("named_insured"),
        profile.get("insured_name"),
        profile.get("insured"),
        "This account",
    )

    carrier_name = _first(
        profile.get("writing_carrier"),
        profile.get("carrier_name"),
        profile.get("carrier"),
        "the current carrier",
    )

    account_number = _first(profile.get("account_number"), profile.get("customer_number"))
    effective_date = _first(profile.get("effective_date"), profile.get("policy_effective_date"))
    expiration_date = _first(profile.get("expiration_date"), profile.get("policy_expiration_date"))
    evaluation_date = _first(profile.get("evaluation_date"), profile.get("valuation_date"))

    total_claims = len(claims)
    open_claims = sum(1 for claim in claims if _status_is_open(claim.get("status") or claim.get("claim_status")))
    closed_claims = max(total_claims - open_claims, 0)
    total_incurred = sum(_claim_total(claim) for claim in claims)
    reserve_total = sum(_claim_reserve(claim) for claim in claims)
    paid_total = sum(_money(claim.get("paid_amount") or claim.get("paid")) for claim in claims)

    risk_level = _risk_level(total_claims, open_claims, total_incurred, reserve_total)
    risk_tone = _tone_from_risk(risk_level)

    top_claims = _top_claims(claims)
    line_mix = _line_mix(claims)

    policy_lines = []
    for policy in policies:
        line = _policy_line(policy)
        number = _policy_number(policy)
        if line and number:
            policy_lines.append(f"{line} ({number})")
        elif line:
            policy_lines.append(line)

    policy_sentence = _sentence_list(policy_lines[:6])
    operations = _clean(scope_of_work) or _clean(website_text) or _business_description(profile, policies, claims)

    largest_claim = top_claims[0] if top_claims else {}
    largest_claim_text = ""
    if largest_claim:
        largest_claim_text = (
            f"The largest reported loss is {_claim_number(largest_claim)} on "
            f"{_claim_line(largest_claim)} with {_money_display(_claim_total(largest_claim))} incurred."
        )

    open_claim_text = (
        f"{open_claims} claim remains open"
        if open_claims == 1
        else f"{open_claims} claims remain open"
    )

    account_intro_parts = [
        f"{business_name} is {operations}.",
    ]

    if policy_sentence:
        account_intro_parts.append(f"The account includes {policy_sentence}.")

    if carrier_name and carrier_name != "the current carrier":
        account_intro_parts.append(f"The current writing carrier is {carrier_name}.")

    if effective_date or expiration_date:
        account_intro_parts.append(
            f"The policy term reviewed is {_first(effective_date, 'not specified')} to {_first(expiration_date, 'not specified')}."
        )

    if evaluation_date:
        account_intro_parts.append(f"The loss information appears valued as of {evaluation_date}.")

    account_story = " ".join(account_intro_parts)

    account_story += (
        f" The loss run reflects {total_claims} claim"
        f"{'' if total_claims == 1 else 's'}, {open_claims} open and {closed_claims} closed, "
        f"with {_money_display(total_incurred)} in total incurred and {_money_display(reserve_total)} in reserves."
    )

    if largest_claim_text:
        account_story += f" {largest_claim_text}"

    account_story += f" Overall, the account {risk_tone}."

    underwriter_bullets: List[str] = []

    if total_claims == 0:
        underwriter_bullets.append("No claim activity is reflected in the provided loss run.")
    else:
        underwriter_bullets.append(
            f"The account has {total_claims} reported claim{'' if total_claims == 1 else 's'} with {_money_display(total_incurred)} total incurred."
        )

    if open_claims > 0:
        underwriter_bullets.append(f"{open_claim_text}, so reserve development should be reviewed before submission.")
    else:
        underwriter_bullets.append("No open claims are currently reflected, which is favorable from a renewal standpoint.")

    if reserve_total > 0:
        underwriter_bullets.append(f"Outstanding reserves total {_money_display(reserve_total)}, which may affect renewal pricing and carrier appetite.")

    if largest_claim:
        underwriter_bullets.append(
            f"The largest loss is {_claim_number(largest_claim)} at {_money_display(_claim_total(largest_claim))}, which should be explained clearly."
        )

    for line, data in sorted(line_mix.items(), key=lambda item: item[1]["total_incurred"], reverse=True)[:4]:
        underwriter_bullets.append(
            f"{line} represents {data['claim_count']} claim{'' if data['claim_count'] == 1 else 's'} and {_money_display(data['total_incurred'])} incurred."
        )

    broker_positioning = (
        f"{business_name} should be presented as {operations} with a clear explanation of the loss activity. "
        f"The submission should lead with the facts: {total_claims} claim"
        f"{'' if total_claims == 1 else 's'}, {_money_display(total_incurred)} total incurred, "
        f"and {open_claims} open claim{'' if open_claims == 1 else 's'}. "
    )

    if open_claims > 0 or reserve_total > 0:
        broker_positioning += (
            "The broker should address open claims and reserves directly instead of letting the carrier infer deterioration. "
        )

    broker_positioning += (
        "The most effective positioning will include management response, corrective actions, current controls, and any documentation that shows the account is actively managing the exposure."
    )

    carrier_concerns: List[str] = []

    if open_claims > 0:
        carrier_concerns.append("Open claim development and reserve adequacy")
    if total_claims >= 5:
        carrier_concerns.append("Claim frequency across the policy term")
    if total_incurred >= 100000:
        carrier_concerns.append("Overall incurred severity")
    if reserve_total >= 25000:
        carrier_concerns.append("Outstanding reserves")
    if any("auto" in line.lower() for line in line_mix):
        carrier_concerns.append("Driver controls, vehicle use, and accident prevention")
    if any("cargo" in line.lower() for line in line_mix):
        carrier_concerns.append("Cargo handling procedures and loss prevention")
    if any("workers" in line.lower() or "comp" in line.lower() for line in line_mix):
        carrier_concerns.append("Employee safety controls and return-to-work procedures")
    if any("liquor" in line.lower() for line in line_mix):
        carrier_concerns.append("Liquor service controls, incident prevention, and staff training")
    if not carrier_concerns:
        carrier_concerns.append("No major claim concerns identified from the provided loss run")

    claim_narrative_parts: List[str] = []

    if top_claims:
        for claim in top_claims:
            description = _claim_description(claim)
            status = _first(claim.get("status"), claim.get("claim_status"), "Status not stated")
            claim_text = (
                f"{_claim_number(claim)} is a {status.lower()} {_claim_line(claim)} claim with "
                f"{_money_display(_claim_total(claim))} incurred"
            )

            reserve = _claim_reserve(claim)
            if reserve > 0:
                claim_text += f" and {_money_display(reserve)} reserved"

            if description:
                claim_text += f". Notes indicate: {description}"
            else:
                claim_text += ". No detailed claim notes were detected."

            claim_narrative_parts.append(claim_text)

    claim_narrative = " ".join(claim_narrative_parts) if claim_narrative_parts else (
        "No claim narrative was generated because no claim detail was provided."
    )

    corrective_actions = [
        "Confirm open claim status, current reserves, and expected closure timeline.",
        "Document post-loss corrective actions for the largest and most recent claims.",
        "Include updated safety, training, maintenance, or operational controls with the submission.",
        "Have a licensed insurance professional review the final carrier-facing language before sending.",
    ]

    if any("auto" in concern.lower() for concern in carrier_concerns):
        corrective_actions.append("Provide driver screening, MVR review, vehicle maintenance, and accident-prevention details.")

    if any("cargo" in concern.lower() for concern in carrier_concerns):
        corrective_actions.append("Provide cargo handling, loading, securement, and delivery quality-control procedures.")

    if any("workers" in concern.lower() or "employee" in concern.lower() for concern in carrier_concerns):
        corrective_actions.append("Provide employee safety training, injury prevention, and return-to-work procedures.")

    human_review_note = (
        "AI draft — review before sending. LossQ generated this narrative from the uploaded account profile, policy schedule, "
        "claims, and exposure inputs. A human insurance professional should verify the business operations, claim context, "
        "reserves, corrective actions, and carrier-facing language before using this in a submission."
    )

    carrier_ready_summary = (
        f"{business_name} is {operations} with policy coverage reflected across "
        f"{len(policies)} policy line{'' if len(policies) == 1 else 's'}. "
        f"The reviewed loss information shows {total_claims} claim{'' if total_claims == 1 else 's'}, "
        f"{open_claims} open and {closed_claims} closed, with {_money_display(total_incurred)} total incurred. "
    )

    if largest_claim_text:
        carrier_ready_summary += f"{largest_claim_text} "

    carrier_ready_summary += (
        "The account should be reviewed with emphasis on current claim status, reserve development, "
        "and corrective actions taken by management. Subject to verification, the account can be positioned "
        "with a clear underwriting explanation rather than submitted as raw loss data alone."
    )

    confidence_notes = []

    if business_name == "This account":
        confidence_notes.append("Business name was not available from the supplied profile.")
    if not policies:
        confidence_notes.append("No policy schedule was provided to the narrative engine.")
    if not claims:
        confidence_notes.append("No claim rows were provided to the narrative engine.")
    if not exposure_inputs:
        confidence_notes.append("No exposure inputs were provided to the narrative engine.")
    if source_context:
        confidence_notes.append(f"Source context: {source_context}")

    if not confidence_notes:
        confidence_notes.append("Narrative generated from structured profile, policy, claim, and exposure data.")

    return {
        "humanized": True,
        "engine_version": "LOSSQ_HUMANIZED_NARRATIVE_ENGINE_V1",
        "account_snapshot": {
            "business_name": business_name,
            "account_number": account_number,
            "carrier_name": carrier_name,
            "effective_date": effective_date,
            "expiration_date": expiration_date,
            "evaluation_date": evaluation_date,
            "total_claims": total_claims,
            "open_claims": open_claims,
            "closed_claims": closed_claims,
            "paid_total": paid_total,
            "reserve_total": reserve_total,
            "total_incurred": total_incurred,
            "risk_level": risk_level,
        },
        "account_story": account_story,
        "underwriter_view": underwriter_bullets,
        "broker_positioning": broker_positioning,
        "carrier_concerns": carrier_concerns,
        "claim_narrative": claim_narrative,
        "corrective_actions": corrective_actions,
        "human_review_note": human_review_note,
        "carrier_ready_summary": carrier_ready_summary,
        "confidence_notes": confidence_notes,
    }
