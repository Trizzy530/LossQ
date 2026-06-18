from collections import defaultdict
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.plan_limits import require_package_access
from app.routes.summary import (
    build_underwriting_intelligence,
    get_claims_for_account,
    data_quality,
)
from app.routes.renewal import (
    build_underwriter_decision_engine,
    build_carrier_appetite_engine,
    build_carrier_match_engine,
    build_premium_forecast_engine,
    money,
    is_open,
    is_litigated,
)

router = APIRouter(prefix="/submission-builder", tags=["Submission Builder"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def safe_text(value, fallback="Not provided"):
    value = str(value or "").strip()
    return value if value else fallback


def safe_money(value):
    try:
        return money(value)
    except Exception:
        try:
            raw = str(value or "").replace("$", "").replace(",", "").strip()
            return float(raw or 0)
        except Exception:
            return 0.0


def format_money(value):
    return f"${safe_money(value):,.0f}"


def attr(obj, name, fallback=None):
    try:
        value = getattr(obj, name, fallback)
        return fallback if value is None else value
    except Exception:
        return fallback


def claim_description(claim):
    return safe_text(
        attr(claim, "description", None)
        or attr(claim, "loss_description", None)
        or attr(claim, "cause_of_loss", None)
        or attr(claim, "claim_description", None),
        "No claim description provided",
    )


def claim_number(claim):
    return safe_text(
        attr(claim, "claim_number", None)
        or attr(claim, "claim_id", None)
        or attr(claim, "claim_no", None),
        "Claim number not provided",
    )


def claim_policy_number(claim):
    return safe_text(attr(claim, "policy_number", None), "Policy not provided")


def claim_line(claim):
    return safe_text(
        attr(claim, "line_of_business", None)
        or attr(claim, "claim_type", None)
        or attr(claim, "coverage", None)
        or attr(claim, "policy_type", None),
        "Line not provided",
    )


def claim_status(claim):
    return safe_text(attr(claim, "status", None) or attr(claim, "claim_status", None), "Unknown")


def claim_loss_date(claim):
    return safe_text(
        attr(claim, "date_of_loss", None)
        or attr(claim, "loss_date", None)
        or attr(claim, "accident_date", None),
        "Not provided",
    )


def normalize_policies(profile_data, policy_numbers_used):
    raw_policies = (
        profile_data.get("policies")
        or profile_data.get("policy_schedule")
        or profile_data.get("policySchedule")
        or []
    )

    policies = []
    seen = set()

    if isinstance(raw_policies, list):
        for item in raw_policies:
            if not isinstance(item, dict):
                continue

            policy_number = safe_text(
                item.get("policy_number")
                or item.get("Policy Number")
                or item.get("policy")
                or item.get("number"),
                "",
            )
            if not policy_number:
                continue

            key = policy_number.upper()
            if key in seen:
                continue
            seen.add(key)

            policies.append({
                "policy_number": policy_number,
                "line_of_business": safe_text(
                    item.get("line_of_business")
                    or item.get("coverage")
                    or item.get("Coverage / Line")
                    or item.get("policy_type")
                    or item.get("line"),
                    "Line not provided",
                ),
                "carrier": safe_text(
                    item.get("carrier")
                    or item.get("carrier_name")
                    or item.get("writing_carrier")
                    or profile_data.get("writing_carrier")
                    or profile_data.get("carrier_name"),
                    "Carrier not provided",
                ),
                "effective_date": safe_text(
                    item.get("effective_date")
                    or item.get("effective")
                    or item.get("Effective"),
                    "Not provided",
                ),
                "expiration_date": safe_text(
                    item.get("expiration_date")
                    or item.get("expiration")
                    or item.get("Expiration"),
                    "Not provided",
                ),
                "premium": format_money(item.get("premium") or item.get("Premium") or 0),
                "exposure_basis": safe_text(
                    item.get("exposure_basis")
                    or item.get("Exposure Basis")
                    or item.get("basis"),
                    "Not provided",
                ),
                "exposure_value": safe_text(
                    item.get("exposure_value")
                    or item.get("Exposure Value")
                    or item.get("exposure"),
                    "Not provided",
                ),
            })

    for policy_number in policy_numbers_used or []:
        if not policy_number:
            continue
        key = str(policy_number).upper()
        if key not in seen:
            policies.append({
                "policy_number": policy_number,
                "line_of_business": "Line not provided",
                "carrier": safe_text(
                    profile_data.get("writing_carrier") or profile_data.get("carrier_name"),
                    "Carrier not provided",
                ),
                "effective_date": safe_text(profile_data.get("effective_date"), "Not provided"),
                "expiration_date": safe_text(profile_data.get("expiration_date"), "Not provided"),
                "premium": "$0",
                "exposure_basis": "Not provided",
                "exposure_value": "Not provided",
            })
            seen.add(key)

    return policies


def build_claim_summaries(claims):
    rows = []

    for claim in claims:
        paid = safe_money(attr(claim, "paid_amount", 0))
        reserve = safe_money(attr(claim, "reserve_amount", 0))
        incurred = safe_money(attr(claim, "total_incurred", 0))
        if incurred <= 0 and (paid > 0 or reserve > 0):
            incurred = paid + reserve

        rows.append({
            "claim_number": claim_number(claim),
            "policy_number": claim_policy_number(claim),
            "line_of_business": claim_line(claim),
            "status": claim_status(claim),
            "loss_date": claim_loss_date(claim),
            "paid_amount": paid,
            "reserve_amount": reserve,
            "total_incurred": incurred,
            "paid_amount_display": format_money(paid),
            "reserve_amount_display": format_money(reserve),
            "total_incurred_display": format_money(incurred),
            "litigation": bool(is_litigated(claim)),
            "description": claim_description(claim),
            "underwriter_note": build_claim_note(claim, paid, reserve, incurred),
        })

    rows.sort(key=lambda item: item["total_incurred"], reverse=True)
    return rows


def build_claim_note(claim, paid, reserve, incurred):
    status = claim_status(claim)
    line = claim_line(claim)
    desc = claim_description(claim)
    litigated = bool(is_litigated(claim))

    concern_parts = []

    if is_open(claim):
        concern_parts.append(f"open {line} matter with {format_money(reserve)} currently reserved")
    else:
        concern_parts.append(f"closed {line} matter with {format_money(incurred)} total incurred")

    if litigated:
        concern_parts.append("litigation involvement noted")

    if incurred >= 100000:
        concern_parts.append("large-loss threshold exceeded")

    return f"{claim_number(claim)} is an {', '.join(concern_parts)}. Loss detail: {desc}."


def summarize_by_line(claim_rows):
    grouped = defaultdict(lambda: {
        "claim_count": 0,
        "open_claims": 0,
        "litigation_claims": 0,
        "paid_amount": 0.0,
        "reserve_amount": 0.0,
        "total_incurred": 0.0,
    })

    for row in claim_rows:
        key = row["line_of_business"]
        grouped[key]["claim_count"] += 1
        grouped[key]["paid_amount"] += row["paid_amount"]
        grouped[key]["reserve_amount"] += row["reserve_amount"]
        grouped[key]["total_incurred"] += row["total_incurred"]

        if str(row["status"]).lower() == "open":
            grouped[key]["open_claims"] += 1

        if row["litigation"]:
            grouped[key]["litigation_claims"] += 1

    output = []
    for line, values in grouped.items():
        output.append({
            "line_of_business": line,
            **values,
            "paid_amount_display": format_money(values["paid_amount"]),
            "reserve_amount_display": format_money(values["reserve_amount"]),
            "total_incurred_display": format_money(values["total_incurred"]),
        })

    output.sort(key=lambda item: item["total_incurred"], reverse=True)
    return output


def build_large_loss_explanations(claim_rows, total_incurred):
    if not claim_rows:
        return []

    threshold = max(50000, total_incurred * 0.20)
    large_losses = [row for row in claim_rows if row["total_incurred"] >= threshold]

    if not large_losses and claim_rows:
        large_losses = claim_rows[:3]

    explanations = []
    for row in large_losses[:6]:
        explanations.append({
            "claim_number": row["claim_number"],
            "line_of_business": row["line_of_business"],
            "status": row["status"],
            "total_incurred": row["total_incurred"],
            "total_incurred_display": row["total_incurred_display"],
            "reserve_amount_display": row["reserve_amount_display"],
            "litigation": row["litigation"],
            "description": row["description"],
            "carrier_positioning": build_large_loss_positioning(row),
        })

    return explanations


def build_large_loss_positioning(row):
    if row["status"].lower() == "closed" and row["reserve_amount"] <= 0:
        return (
            f"Position as a known and closed loss. Emphasize final resolution, "
            f"absence of current reserve exposure, and any corrective action tied to the cause of loss."
        )

    if row["litigation"]:
        return (
            f"Position with updated litigation status, defense plan, venue information, "
            f"reserve rationale, and expected resolution timeline."
        )

    if row["reserve_amount"] > 0:
        return (
            f"Position with current adjuster notes, reserve basis, mitigation steps, "
            f"and expected closure path."
        )

    return (
        f"Position as part of the account loss narrative with cause-of-loss controls, "
        f"corrective action, and recurrence prevention."
    )


def build_open_claim_concerns(claim_rows):
    open_rows = [row for row in claim_rows if row["status"].lower() == "open"]
    concerns = []

    for row in open_rows:
        concerns.append({
            "claim_number": row["claim_number"],
            "line_of_business": row["line_of_business"],
            "reserve_amount_display": row["reserve_amount_display"],
            "total_incurred_display": row["total_incurred_display"],
            "litigation": row["litigation"],
            "underwriter_concern": (
                f"Open {row['line_of_business']} claim with {row['reserve_amount_display']} in reserves. "
                f"Carrier will likely request adjuster status, reserve basis, and expected closure timeline."
            ),
        })

    return concerns


def build_litigation_concerns(claim_rows):
    litigated = [row for row in claim_rows if row["litigation"]]
    concerns = []

    for row in litigated:
        concerns.append({
            "claim_number": row["claim_number"],
            "line_of_business": row["line_of_business"],
            "status": row["status"],
            "total_incurred_display": row["total_incurred_display"],
            "underwriter_concern": (
                f"Litigation is noted on {row['claim_number']}. Provide complaint status, counsel assignment, "
                f"settlement posture, venue, and expected next milestone."
            ),
        })

    return concerns


def build_strengths(profile_data, claim_rows, total_claims, open_claims, litigation_claims):
    strengths = []

    if profile_data.get("business_name"):
        strengths.append("Named insured and account profile are available for carrier review.")

    if profile_data.get("policies") or profile_data.get("policy_schedule"):
        strengths.append("Policy schedule is available and can be tied to loss experience by line.")

    closed_claims = total_claims - open_claims
    if total_claims and closed_claims >= open_claims:
        strengths.append(f"{closed_claims} of {total_claims} claims are closed, reducing uncertainty in the loss picture.")

    if litigation_claims == 0:
        strengths.append("No litigation involvement is currently indicated in the validated claim set.")

    if any(row["reserve_amount"] <= 0 and row["status"].lower() == "closed" for row in claim_rows):
        strengths.append("Closed claims with no remaining reserves can be positioned as resolved loss events.")

    if not strengths:
        strengths.append("Submission contains structured loss data that can be packaged for underwriting review.")

    return strengths


def build_weaknesses(claim_rows, open_claims, litigation_claims, total_reserve, total_incurred):
    weaknesses = []

    if open_claims:
        weaknesses.append(f"{open_claims} open claim(s) require current adjuster status and reserve support.")

    if litigation_claims:
        weaknesses.append(f"{litigation_claims} litigated claim(s) may trigger carrier questions on severity and resolution timing.")

    if total_reserve > 0:
        reserve_ratio = total_reserve / total_incurred if total_incurred else 0
        weaknesses.append(f"Outstanding reserves total {format_money(total_reserve)} ({reserve_ratio:.0%} of total incurred).")

    large = [row for row in claim_rows if row["total_incurred"] >= 100000]
    if large:
        weaknesses.append(f"{len(large)} large loss(es) exceed $100,000 and should be explained before market approach.")

    if not weaknesses:
        weaknesses.append("No major submission weaknesses identified from the validated claim data.")

    return weaknesses


def build_underwriter_questions(open_claims, litigation_claims, large_losses, line_summary):
    questions = [
        "Can you provide currently valued loss runs with valuation date shown?",
        "Have there been operational or risk-control changes since the reported losses?",
        "Are any claims expected to develop materially before renewal?",
    ]

    if open_claims:
        questions.extend([
            "What is the current adjuster status for each open claim?",
            "What is the reserve basis and expected closure timeline for open claims?",
        ])

    if litigation_claims:
        questions.extend([
            "What is the current litigation posture, venue, counsel assignment, and settlement authority?",
            "Are any litigated claims expected to exceed current reserves?",
        ])

    if large_losses:
        questions.append("What corrective action was taken after each large loss to prevent recurrence?")

    if len(line_summary) > 1:
        questions.append("Which lines should be remarketed aggressively versus renewed with incumbent markets?")

    return questions


def build_missing_documents_checklist(open_claims, litigation_claims, claim_rows):
    checklist = [
        "Current valued carrier loss runs by policy year and line of business",
        "Completed ACORD applications or carrier supplemental applications",
        "Current exposure schedule matching the requested policy period",
        "Current premium and expiring premium by line of business",
        "Policy schedule with effective dates, expiration dates, limits, and deductibles",
    ]

    if open_claims:
        checklist.append("Open-claim adjuster notes and reserve rationale")

    if litigation_claims:
        checklist.append("Litigation status report, defense counsel notes, venue, and expected next steps")

    if any(row["total_incurred"] >= 100000 for row in claim_rows):
        checklist.append("Large loss narratives with corrective action and recurrence prevention")

    checklist.extend([
        "Risk-control improvements or safety procedures implemented since losses",
        "Target renewal date and requested quote timeline",
    ])

    return checklist


def score_submission_readiness(quality, profile_data, total_claims, open_claims, litigation_claims, total_reserve, total_incurred):
    score = 100

    if not quality.get("is_credible"):
        return 0

    if not profile_data.get("business_name"):
        score -= 10

    if not (profile_data.get("policies") or profile_data.get("policy_schedule")):
        score -= 15

    if total_claims <= 0:
        score -= 35

    if open_claims:
        score -= min(25, open_claims * 6)

    if litigation_claims:
        score -= min(25, litigation_claims * 8)

    if total_incurred and total_reserve / total_incurred >= 0.35:
        score -= 10

    return max(0, min(100, score))


def readiness_level(score):
    if score >= 85:
        return "Market Ready"
    if score >= 70:
        return "Ready With Follow-Up"
    if score >= 50:
        return "Needs Broker Cleanup"
    return "Not Ready"


def build_broker_strategy(insured, readiness, open_claims, litigation_claims, large_losses, appetite):
    base = [
        f"Lead with a clean, organized submission for {insured} that ties policy schedule, exposure base, and claim experience together.",
        "Address the loss story before the carrier asks for it. Include large loss narratives and corrective actions up front.",
    ]

    if open_claims:
        base.append("Do not approach key markets without updated open-claim status and reserve support.")

    if litigation_claims:
        base.append("Package litigated claims with defense status, settlement posture, and expected resolution timing.")

    if large_losses:
        base.append("Separate one-time severity events from recurring operational issues where the facts support that position.")

    market_strategy = appetite.get("market_strategy") if isinstance(appetite, dict) else None
    if market_strategy:
        base.append(str(market_strategy))

    if readiness in {"Needs Broker Cleanup", "Not Ready"}:
        base.append("Hold broad market release until missing documents and claim explanations are completed.")

    return " ".join(base)


def build_carrier_email(insured, profile_data, policy_text, total_claims, open_claims, litigation_claims, total_incurred, total_reserve, readiness, strengths, weaknesses):
    agency = safe_text(
        profile_data.get("producing_agency")
        or profile_data.get("agency_name")
        or profile_data.get("producer_name"),
        "our agency",
    )

    subject = f"Renewal Submission - {insured}"

    body = f"""Subject: {subject}

Hello,

Please find attached the renewal submission package for {insured}. The submission includes the account profile, policy schedule, exposure information, loss experience, and LossQ underwriting summary.

Submission Snapshot:
- Producing Agency: {agency}
- Policies Reviewed: {policy_text}
- Claims Reviewed: {total_claims}
- Open Claims: {open_claims}
- Litigation Claims: {litigation_claims}
- Total Incurred: {format_money(total_incurred)}
- Outstanding Reserves: {format_money(total_reserve)}
- Submission Readiness: {readiness}

Key Positioning Points:
{chr(10).join(f"- {item}" for item in strengths[:5])}

Items Addressed Up Front:
{chr(10).join(f"- {item}" for item in weaknesses[:5])}

Please let us know if you need updated loss runs, supplemental applications, open-claim status, or large-loss narratives to continue underwriting review.

Thank you,
{agency}
"""

    return body


@router.get("/")
def submission_builder(
    policy_number: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_package_access),
):
    claims, policy_numbers_used, profile_data = get_claims_for_account(db, current_user, policy_number)
    quality = data_quality(claims, policy_numbers_used, profile_data)

    if not quality["is_credible"]:
        return {
            "policy_number": policy_number,
            "claims_used": len(claims),
            "policy_numbers_used": policy_numbers_used,
            "account_profile": profile_data,
            "is_credible": False,
            "data_quality": quality,
            "submission_readiness_score": 0,
            "submission_readiness_level": "Not Ready",
            "underwriter_narrative": "INSUFFICIENT DATA: Do not send to underwriters until claims and policy schedule are validated.",
            "carrier_submission_email": "Submission blocked by LossQ data-quality guardrail. Validate loss run extraction first.",
            "executive_summary": "Insufficient validated loss data. Submission package not generated.",
            "loss_explanations": [],
            "large_loss_explanations": [],
            "open_claim_concerns": [],
            "litigation_concerns": [],
            "broker_marketing_memo": "Not ready for market.",
            "renewal_strategy": "Correct parser/upload data first, then regenerate the submission package.",
            "missing_documents_checklist": [
                "Validated loss runs",
                "Policy schedule",
                "Named insured/account profile",
                "Exposure basis and values",
            ],
            "underwriter_questions_to_expect": [
                "Can you provide validated loss runs and policy schedule before submission review?",
            ],
            "supporting_intelligence": {},
        }

    intelligence = build_underwriting_intelligence(claims)
    decision = build_underwriter_decision_engine(claims, policy_number)
    appetite = build_carrier_appetite_engine(claims, policy_number)
    carrier_match = build_carrier_match_engine(claims, policy_number)
    forecast = build_premium_forecast_engine(claims, policy_number)

    claim_rows = build_claim_summaries(claims)
    line_summary = summarize_by_line(claim_rows)
    policies = normalize_policies(profile_data, policy_numbers_used)

    total_claims = len(claims)
    open_claims = len([c for c in claims if is_open(c)])
    closed_claims = total_claims - open_claims
    litigation_claims = len([c for c in claims if is_litigated(c)])
    total_paid = sum(row["paid_amount"] for row in claim_rows)
    total_reserve = sum(row["reserve_amount"] for row in claim_rows)
    total_incurred = sum(row["total_incurred"] for row in claim_rows)

    insured = safe_text(
        profile_data.get("business_name")
        or profile_data.get("named_insured")
        or profile_data.get("insured_name"),
        "Selected Account",
    )

    carrier = safe_text(
        profile_data.get("writing_carrier")
        or profile_data.get("carrier_name")
        or profile_data.get("carrier"),
        "Carrier not provided",
    )

    producing_agency = safe_text(
        profile_data.get("producing_agency")
        or profile_data.get("agency_name")
        or profile_data.get("producer_name"),
        "Producing agency not provided",
    )

    policy_text = ", ".join(policy_numbers_used or []) or "Policy not provided"

    large_loss_explanations = build_large_loss_explanations(claim_rows, total_incurred)
    open_claim_concerns = build_open_claim_concerns(claim_rows)
    litigation_concerns = build_litigation_concerns(claim_rows)
    strengths = build_strengths(profile_data, claim_rows, total_claims, open_claims, litigation_claims)
    weaknesses = build_weaknesses(claim_rows, open_claims, litigation_claims, total_reserve, total_incurred)

    readiness_score = score_submission_readiness(
        quality=quality,
        profile_data=profile_data,
        total_claims=total_claims,
        open_claims=open_claims,
        litigation_claims=litigation_claims,
        total_reserve=total_reserve,
        total_incurred=total_incurred,
    )
    readiness = readiness_level(readiness_score)

    underwriter_questions = build_underwriter_questions(
        open_claims=open_claims,
        litigation_claims=litigation_claims,
        large_losses=large_loss_explanations,
        line_summary=line_summary,
    )

    missing_documents = build_missing_documents_checklist(
        open_claims=open_claims,
        litigation_claims=litigation_claims,
        claim_rows=claim_rows,
    )

    broker_strategy = build_broker_strategy(
        insured=insured,
        readiness=readiness,
        open_claims=open_claims,
        litigation_claims=litigation_claims,
        large_losses=large_loss_explanations,
        appetite=appetite if isinstance(appetite, dict) else {},
    )

    executive_summary = (
        f"{insured} is presented with {total_claims} validated claim(s) across {len(policies)} policy line(s). "
        f"The account shows {format_money(total_incurred)} in total incurred losses, including "
        f"{format_money(total_paid)} paid and {format_money(total_reserve)} in outstanding reserves. "
        f"There are {open_claims} open claim(s), {closed_claims} closed claim(s), and {litigation_claims} litigated claim(s). "
        f"Submission readiness is {readiness} at {readiness_score}/100."
    )

    underwriter_narrative = (
        f"{insured} has validated loss experience across {policy_text}. "
        f"The loss profile is driven primarily by "
        f"{line_summary[0]['line_of_business'] if line_summary else 'the submitted lines'} "
        f"with total incurred of {line_summary[0]['total_incurred_display'] if line_summary else format_money(total_incurred)}. "
        f"Open reserve exposure is {format_money(total_reserve)}, and carrier review should focus on "
        f"large-loss explanations, open-claim development, litigation status, and corrective action documentation."
    )

    carrier_email = build_carrier_email(
        insured=insured,
        profile_data=profile_data,
        policy_text=policy_text,
        total_claims=total_claims,
        open_claims=open_claims,
        litigation_claims=litigation_claims,
        total_incurred=total_incurred,
        total_reserve=total_reserve,
        readiness=readiness,
        strengths=strengths,
        weaknesses=weaknesses,
    )

    account_snapshot = {
        "named_insured": insured,
        "producing_agency": producing_agency,
        "writing_carrier": carrier,
        "account_number": safe_text(
            profile_data.get("account_number")
            or profile_data.get("customer_number"),
            "Not provided",
        ),
        "evaluation_date": safe_text(profile_data.get("evaluation_date"), "Not provided"),
        "effective_date": safe_text(profile_data.get("effective_date"), "Not provided"),
        "expiration_date": safe_text(profile_data.get("expiration_date"), "Not provided"),
    }

    loss_summary = {
        "total_claims": total_claims,
        "open_claims": open_claims,
        "closed_claims": closed_claims,
        "litigation_claims": litigation_claims,
        "total_paid": total_paid,
        "total_reserve": total_reserve,
        "total_incurred": total_incurred,
        "total_paid_display": format_money(total_paid),
        "total_reserve_display": format_money(total_reserve),
        "total_incurred_display": format_money(total_incurred),
    }

    return {
        "policy_number": policy_number,
        "policy_numbers_used": policy_numbers_used,
        "claims_used": total_claims,
        "account_profile": profile_data,
        "account_snapshot": account_snapshot,
        "is_credible": True,
        "data_quality": quality,

        "submission_readiness_score": readiness_score,
        "submission_readiness_level": readiness,
        "submission_strength": readiness,
        "submission_score": readiness_score,

        "executive_summary": executive_summary,
        "underwriter_narrative": underwriter_narrative,
        "carrier_submission_email": carrier_email,

        "policy_schedule_summary": policies,
        "line_of_business_summary": line_summary,
        "loss_summary": loss_summary,
        "claim_summaries": claim_rows,

        "loss_explanations": large_loss_explanations,
        "large_loss_explanations": large_loss_explanations,
        "open_claim_concerns": open_claim_concerns,
        "litigation_concerns": litigation_concerns,

        "risk_strengths": strengths,
        "risk_weaknesses": weaknesses,
        "underwriter_questions_to_expect": underwriter_questions,
        "missing_documents_checklist": missing_documents,
        "recommended_attachments": missing_documents,

        "broker_marketing_memo": broker_strategy,
        "broker_positioning_strategy": broker_strategy,
        "renewal_strategy": decision.get("submission_readiness") if isinstance(decision, dict) else broker_strategy,

        "supporting_intelligence": {
            "summary": intelligence,
            "decision": decision,
            "carrier_appetite": appetite,
            "carrier_match": carrier_match,
            "premium_forecast": forecast,
        },
    }
