from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
import json

from app.database import SessionLocal
from app.models.claim import Claim
from app.models.account_profile import AccountProfile
from app.auth_utils import get_current_user
from app.plan_limits import require_package_access

router = APIRouter(prefix="/summary", tags=["Summary"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def money(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def clean(value):
    return str(value or "").strip()


def normalize_policy(value):
    return clean(value).upper()


def parse_json(value, fallback):
    if value is None:
        return fallback
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if parsed is not None else fallback
        except Exception:
            return fallback
    return fallback


def is_open_claim(claim):
    return clean(getattr(claim, "status", "")).lower() in ["open", "reopened", "re-opened", "pending", "active"]


def has_litigation(claim):
    value = getattr(claim, 'litigation', False)
    if isinstance(value, bool) and value:
        return True
    if isinstance(value, str) and clean(value).lower() in ['true', 'yes', 'y', '1', 'litigation', 'litigated']:
        return True
    desc = clean(getattr(claim, 'description', '') or '').lower()
    if any(word in desc for word in ['litigat', 'attorney', 'lawsuit', 'counsel', 'legal action', 'represented']):
        return True
    return False


def is_flagged_claim(claim):
    value = getattr(claim, "flag", None)
    if value is None:
        value = getattr(claim, "flagged", None)
    if isinstance(value, bool):
        return value
    return bool(clean(value)) and clean(value).lower() not in ["false", "no", "0", "none"]


def profile_to_dict(profile):
    if not profile:
        return {}
    data = {}
    for key in [
        "id", "business_name", "carrier_name", "writing_carrier", "agency_name",
        "account_number", "customer_number", "producer_number", "policy_number",
        "effective_date", "expiration_date", "evaluation_date", "policies", "validation",
    ]:
        if hasattr(profile, key):
            data[key] = getattr(profile, key)
    data["policies"] = parse_json(data.get("policies"), [])
    data["validation"] = parse_json(data.get("validation"), {})
    return data


def get_profile_for_policy(db: Session, current_user: dict, policy_number: str | None):
    org_id = current_user["organization_id"]
    if policy_number:
        profile = (
            db.query(AccountProfile)
            .filter(AccountProfile.organization_id == org_id)
            .filter(func.upper(AccountProfile.policy_number) == normalize_policy(policy_number))
            .first()
        )
        if profile:
            return profile
    return (
        db.query(AccountProfile)
        .filter(AccountProfile.organization_id == org_id)
        .order_by(AccountProfile.id.desc())
        .first()
    )


def get_claims_for_account(db: Session, current_user: dict, policy_number: str | None = None):
    profile = get_profile_for_policy(db, current_user, policy_number)
    profile_data = profile_to_dict(profile)
    policies = profile_data.get("policies") if isinstance(profile_data.get("policies"), list) else []

    policy_numbers = []
    for p in policies:
        if isinstance(p, dict) and p.get("policy_number"):
            policy_numbers.append(normalize_policy(p.get("policy_number")))

    if not policy_numbers and policy_number:
        policy_numbers.append(normalize_policy(policy_number))
    if not policy_numbers and profile_data.get("policy_number"):
        policy_numbers.append(normalize_policy(profile_data.get("policy_number")))

    policy_numbers = list(dict.fromkeys([p for p in policy_numbers if p]))

    query = db.query(Claim).filter(Claim.organization_id == current_user["organization_id"])
    if policy_numbers:
        query = query.filter(func.upper(Claim.policy_number).in_(policy_numbers))
    else:
        query = query.filter(False)

    return query.all(), policy_numbers, profile_data


def data_quality(claims, policy_numbers=None, profile_data=None):
    policy_numbers = policy_numbers or []
    profile_data = profile_data or {}
    validation = profile_data.get("validation") if isinstance(profile_data.get("validation"), dict) else {}
    issues = list(validation.get("issues") or validation.get("warnings") or [])

    if not policy_numbers:
        issues.append("No policy schedule or policy numbers available for this account.")
    if len(claims) == 0:
        issues.append("No account-specific claims were found. Underwriting engines cannot produce a credible risk score.")

    credible = len(claims) > 0 and len(policy_numbers) > 0
    return {
        "is_credible": credible,
        "status": "Credible" if credible else "Insufficient Data",
        "issues": issues,
    }



# LOSSQ_REALISTIC_RENEWAL_RISK_MODEL_V1
def lossq_original_build_renewal_risk_engine(claims):
    claims = claims or []

    def m(value):
        try:
            return money(value)
        except Exception:
            try:
                return float(str(value or "0").replace("$", "").replace(",", "").strip() or 0)
            except Exception:
                return 0.0

    def claim_line(c):
        line = clean(
            getattr(c, "line_of_business", "")
            or getattr(c, "claim_type", "")
            or getattr(c, "coverage", "")
            or getattr(c, "policy_type", "")
            or getattr(c, "policy_number", "")
        ).lower()

        policy = clean(getattr(c, "policy_number", "")).upper()

        if "worker" in line or "comp" in line or "-WC-" in policy:
            return "Workers Compensation"
        if "liquor" in line:
            return "Liquor Liability"
        if "auto" in line or "-AL-" in policy or "-AUTO-" in policy:
            return "Commercial Auto"
        if "cargo" in line or "-CG-" in policy or "-CARGO-" in policy:
            return "Cargo"
        if "property" in line or "-CP-" in policy or "-PROP-" in policy:
            return "Commercial Property"
        if "bop" in line or "businessowner" in line or "-BOP-" in policy:
            return "BOP"
        if "cyber" in line or "-CY-" in policy or "-CYBER-" in policy:
            return "Cyber"
        if "employment" in line or "epli" in line or "-EPLI-" in policy:
            return "EPLI"
        if "director" in line or "officer" in line or "d&o" in line or "-DO-" in policy:
            return "D&O"
        if "professional" in line or "errors" in line or "omissions" in line or "-PL-" in policy or "-EO-" in policy:
            return "Professional Liability"
        if "inland" in line or "marine" in line or "-IM-" in policy:
            return "Inland Marine"
        if "crime" in line or "-CRIME-" in policy:
            return "Crime"
        if "umbrella" in line or "excess" in line or "-UMB-" in policy or "-XS-" in policy:
            return "Umbrella / Excess"
        if "general" in line or "liability" in line or "-GL-" in policy:
            return "General Liability"

        return "Other Commercial Line"

    def incurred(c):
        paid = m(getattr(c, "paid_amount", 0))
        reserve = m(getattr(c, "reserve_amount", 0))
        total = m(getattr(c, "total_incurred", 0))
        if total <= 0 and (paid > 0 or reserve > 0):
            total = paid + reserve
        return paid, reserve, total

    total_claims = len(claims)
    open_claims = len([c for c in claims if is_open_claim(c)])
    closed_claims = max(total_claims - open_claims, 0)
    litigation_claims = len([c for c in claims if has_litigation(c)])
    flagged_claims = len([c for c in claims if is_flagged_claim(c)])

    total_paid = 0.0
    total_reserve = 0.0
    total_incurred = 0.0
    largest_loss = 0.0
    line_summary = {}

    for c in claims:
        paid, reserve, total = incurred(c)
        total_paid += paid
        total_reserve += reserve
        total_incurred += total
        largest_loss = max(largest_loss, total)

        line = claim_line(c)
        if line not in line_summary:
            line_summary[line] = {
                "claim_count": 0,
                "open_claims": 0,
                "litigation_claims": 0,
                "paid_amount": 0.0,
                "reserve_amount": 0.0,
                "total_incurred": 0.0,
                "largest_loss": 0.0,
            }

        line_summary[line]["claim_count"] += 1
        line_summary[line]["paid_amount"] += paid
        line_summary[line]["reserve_amount"] += reserve
        line_summary[line]["total_incurred"] += total
        line_summary[line]["largest_loss"] = max(line_summary[line]["largest_loss"], total)

        if is_open_claim(c):
            line_summary[line]["open_claims"] += 1
        if has_litigation(c):
            line_summary[line]["litigation_claims"] += 1

    average_severity = total_incurred / total_claims if total_claims else 0
    large_claims = len([c for c in claims if incurred(c)[2] >= 50000])
    large_claims_100k = len([c for c in claims if incurred(c)[2] >= 100000])
    severe_claims = len([c for c in claims if incurred(c)[2] >= 250000])
    open_reserve_pressure = total_reserve / total_incurred if total_incurred else 0
    closure_rate = closed_claims / total_claims if total_claims else 0
    largest_loss_ratio = largest_loss / total_incurred if total_incurred else 0
    line_count = len(line_summary)

    if total_claims == 0:
        return {
            "renewal_score": None,
            "renewal_risk_level": "Insufficient Data",
            "renewal_drivers": ["No account-specific claims were found. LossQ cannot credibly rate renewal risk."],
            "carrier_concerns": ["Loss run extraction must be reviewed before carrier-facing outputs are used."],
            "broker_recommendation": "Do not rely on this renewal result until claims and policy schedule are populated.",
            "renewal_summary": "Insufficient claim data. Renewal risk has not been rated.",
            "renewal_metrics": {
                "total_claims": 0,
                "open_claims": 0,
                "closed_claims": 0,
                "litigation_claims": 0,
                "flagged_claims": 0,
                "large_claims": 0,
                "large_claims_100k": 0,
                "severe_claims": 0,
                "total_paid": 0,
                "total_reserve": 0,
                "total_incurred": 0,
                "average_severity": 0,
                "largest_loss": 0,
                "open_reserve_pressure": 0,
                "closure_rate": 0,
                "largest_loss_ratio": 0,
                "line_summary": [],
            },
        }

    score = 100

    # Frequency pressure. Carriers tolerate isolated losses better than recurring patterns.
    if total_claims >= 12:
        score -= 26
    elif total_claims >= 8:
        score -= 20
    elif total_claims >= 5:
        score -= 14
    elif total_claims >= 3:
        score -= 7
    else:
        score -= total_claims * 2

    # Open claim development pressure.
    score -= min(open_claims * 8, 30)

    # Litigation pressure. Litigation creates ultimate-loss uncertainty.
    score -= min(litigation_claims * 12, 34)

    # Severity and shock-loss pressure.
    if largest_loss >= 500000:
        score -= 28
    elif largest_loss >= 250000:
        score -= 20
    elif largest_loss >= 100000:
        score -= 12
    elif largest_loss >= 50000:
        score -= 6

    # Total incurred load.
    if total_incurred >= 1500000:
        score -= 32
    elif total_incurred >= 1000000:
        score -= 26
    elif total_incurred >= 500000:
        score -= 18
    elif total_incurred >= 250000:
        score -= 11
    elif total_incurred >= 100000:
        score -= 5

    # Outstanding reserve pressure.
    if open_reserve_pressure >= 0.60:
        score -= 16
    elif open_reserve_pressure >= 0.40:
        score -= 11
    elif open_reserve_pressure >= 0.25:
        score -= 6

    if total_reserve >= 500000:
        score -= 18
    elif total_reserve >= 250000:
        score -= 12
    elif total_reserve >= 100000:
        score -= 8
    elif total_reserve >= 50000:
        score -= 4

    # Average severity and concentration.
    if average_severity >= 150000:
        score -= 13
    elif average_severity >= 75000:
        score -= 8
    elif average_severity >= 40000:
        score -= 4

    if largest_loss_ratio >= 0.70 and total_claims >= 2:
        score -= 5

    if flagged_claims:
        score -= min(flagged_claims * 6, 18)

    if closure_rate >= 0.80 and total_reserve <= 0:
        score += 6
    elif closure_rate >= 0.65 and open_claims <= 1:
        score += 3

    score = max(0, min(100, round(score)))

    if score >= 82:
        level = "Low"
    elif score >= 65:
        level = "Moderate"
    elif score >= 45:
        level = "High"
    else:
        level = "Critical"

    if score >= 82:
        premium_pressure = "Flat to +5%"
        carrier_reaction = "Standard renewal review with normal underwriting questions."
    elif score >= 65:
        premium_pressure = "+5% to +15%"
        carrier_reaction = "Marketable, but underwriter will expect claim explanations and current loss valuation."
    elif score >= 45:
        premium_pressure = "+15% to +35%"
        carrier_reaction = "Terms may tighten. Expect deductible, retention, pricing, or coverage limitations."
    else:
        premium_pressure = "+35% or higher / possible non-renewal concern"
        carrier_reaction = "Restricted appetite. Carrier may require corrective-action documentation before quoting."

    drivers = [
        f"{total_claims} account-specific claim(s) identified across {line_count} commercial line(s).",
        f"Total incurred losses are ${total_incurred:,.0f}; largest loss is ${largest_loss:,.0f}.",
        f"Open reserve pressure is {open_reserve_pressure:.0%} with ${total_reserve:,.0f} outstanding.",
    ]

    if open_claims:
        drivers.append(f"{open_claims} open claim(s) may continue developing before renewal.")
    if litigation_claims:
        drivers.append(f"{litigation_claims} litigated claim(s) increase ultimate-loss uncertainty.")
    if large_claims_100k:
        drivers.append(f"{large_claims_100k} claim(s) exceed $100,000 and require large-loss narratives.")
    elif large_claims:
        drivers.append(f"{large_claims} claim(s) exceed $50,000 and should be explained.")
    if closure_rate >= 0.75:
        drivers.append(f"Closure rate is {closure_rate:.0%}, which helps reduce uncertainty if closed claims are fully resolved.")

    concerns = []
    if open_claims:
        concerns.append("Open claims may continue to develop and should be supported with adjuster notes and reserve rationale.")
    if litigation_claims:
        concerns.append("Litigation increases uncertainty around venue, defense costs, settlement posture, and ultimate loss severity.")
    if total_reserve >= 50000:
        concerns.append("Outstanding reserves may affect loss development, pricing, and carrier willingness to quote.")
    if total_claims >= 5:
        concerns.append("Claim frequency may raise carrier questions about controls, operations, staffing, maintenance, or safety procedures.")
    if large_claims:
        concerns.append("Large losses require detailed narratives, corrective actions, and recurrence-prevention documentation.")
    if not concerns:
        concerns.append("No major carrier concerns detected from the validated account-specific loss data.")

    followups = [
        "Current valued loss runs by line and policy year",
        "Large loss narratives for severity claims",
        "Corrective action taken after each material loss",
    ]
    if open_claims:
        followups.append("Adjuster status, reserve basis, and expected closure timeline for open claims")
    if litigation_claims:
        followups.append("Litigation status, defense counsel update, venue, and settlement posture")

    if level == "Low":
        rec = "Proceed with standard renewal marketing after confirming currently valued loss runs and exposure basis."
    elif level == "Moderate":
        rec = "Market the account with a broker narrative addressing frequency, open reserves, and corrective actions."
    elif level == "High":
        rec = "Build detailed claim narratives, reserve updates, litigation status, and loss-control documentation before broad market release."
    else:
        rec = "Treat as critical renewal. Obtain updated loss runs, litigation updates, reserve explanations, and a corrective-action plan before approaching standard markets."

    line_output = []
    for line, values in line_summary.items():
        line_output.append({
            "line_of_business": line,
            "claim_count": values["claim_count"],
            "open_claims": values["open_claims"],
            "litigation_claims": values["litigation_claims"],
            "paid_amount": values["paid_amount"],
            "reserve_amount": values["reserve_amount"],
            "total_incurred": values["total_incurred"],
            "largest_loss": values["largest_loss"],
        })
    line_output.sort(key=lambda item: item["total_incurred"], reverse=True)

    return {
        "renewal_score": score,
        "renewal_risk_level": level,
        "renewal_drivers": drivers,
        "carrier_concerns": concerns,
        "broker_recommendation": rec,
        "renewal_summary": (
            f"The selected account has a renewal score of {score}/100, indicating {level.lower()} renewal risk. "
            f"The model considered {total_claims} claims, {open_claims} open claims, {litigation_claims} litigated claims, "
            f"${total_incurred:,.0f} total incurred, ${total_reserve:,.0f} reserves, {closure_rate:.0%} closure rate, "
            f"and largest-loss concentration of {largest_loss_ratio:.0%}. Expected pricing pressure is {premium_pressure}."
        ),
        "predicted_carrier_reaction": carrier_reaction,
        "expected_premium_pressure": premium_pressure,
        "required_underwriting_followups": followups,
        "renewal_metrics": {
            "total_claims": total_claims,
            "open_claims": open_claims,
            "closed_claims": closed_claims,
            "litigation_claims": litigation_claims,
            "flagged_claims": flagged_claims,
            "large_claims": large_claims,
            "large_claims_100k": large_claims_100k,
            "severe_claims": severe_claims,
            "total_paid": total_paid,
            "total_reserve": total_reserve,
            "total_incurred": total_incurred,
            "average_severity": average_severity,
            "largest_loss": largest_loss,
            "open_reserve_pressure": open_reserve_pressure,
            "closure_rate": closure_rate,
            "largest_loss_ratio": largest_loss_ratio,
            "line_summary": line_output,
        },
    }



# LOSSQ_SAFETY_RISK_AND_CLAIM_STORY_ENGINE_V1
def lossq_story_money(value):
    try:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        cleaned = str(value).replace("$", "").replace(",", "").strip()
        cleaned = "".join(ch for ch in cleaned if ch.isdigit() or ch in ".-")
        return float(cleaned) if cleaned not in {"", ".", "-", "-."} else 0.0
    except Exception:
        return 0.0


def lossq_story_text(value):
    return str(value or "").strip()


def lossq_story_field(claim, *names):
    for name in names:
        try:
            if isinstance(claim, dict):
                value = claim.get(name)
            else:
                value = getattr(claim, name, None)
            if value not in (None, ""):
                return value
        except Exception:
            continue
    return ""


def lossq_story_claim_number(claim):
    return lossq_story_text(
        lossq_story_field(
            claim,
            "claim_number",
            "claimNumber",
            "claim_no",
            "claim_id",
            "number",
        )
    ) or "Unnumbered Claim"


def lossq_story_line(claim):
    raw = lossq_story_text(
        lossq_story_field(
            claim,
            "line_of_business",
            "lineOfBusiness",
            "policy_type",
            "coverage",
            "coverage_type",
            "lob",
            "claim_type",
            "type",
        )
    )
    upper = raw.upper()

    if any(term in upper for term in ["WORKERS", "WORK COMP", "WC"]):
        return "Workers Compensation"
    if any(term in upper for term in ["AUTO", "VEHICLE", "TRUCK", "FLEET"]):
        return "Commercial Auto"
    if any(term in upper for term in ["CARGO", "MOTOR TRUCK", "MTC"]):
        return "Cargo"
    if any(term in upper for term in ["PROPERTY", "BUILDING", "BOP", "CPP", "CP "]):
        return "Property"
    if any(term in upper for term in ["CYBER", "DATA", "BREACH"]):
        return "Cyber"
    if any(term in upper for term in ["EPLI", "EMPLOYMENT", "HARASSMENT", "DISCRIMINATION"]):
        return "Employment Practices Liability"
    if any(term in upper for term in ["D&O", "DIRECTORS", "OFFICERS"]):
        return "Directors & Officers"
    if any(term in upper for term in ["PROFESSIONAL", "E&O", "ERRORS", "OMISSIONS"]):
        return "Professional Liability"
    if any(term in upper for term in ["LIQUOR", "DRAM"]):
        return "Liquor Liability"
    if any(term in upper for term in ["UMB", "UMBRELLA", "EXCESS"]):
        return "Umbrella / Excess"
    if any(term in upper for term in ["GENERAL", "GL", "LIABILITY", "PREMISES"]):
        return "General Liability"

    return raw or "Commercial Lines"


def lossq_story_status(claim):
    raw = lossq_story_text(lossq_story_field(claim, "status", "claim_status", "open_closed"))
    return raw or "Status Not Set"


def lossq_story_is_open(claim):
    status = lossq_story_status(claim).upper()
    return any(term in status for term in ["OPEN", "PENDING", "ACTIVE", "REOPEN"])


def lossq_story_litigation(claim):
    raw = lossq_story_text(
        lossq_story_field(
            claim,
            "litigation",
            "litigated",
            "lawsuit",
            "attorney_involved",
            "represented",
        )
    ).upper()
    return raw in {"YES", "Y", "TRUE", "1"} or any(term in raw for term in ["LITIGATION", "LAWSUIT", "ATTORNEY", "COUNSEL"])


def lossq_story_paid(claim):
    return lossq_story_money(lossq_story_field(claim, "paid", "paid_amount", "total_paid", "indemnity_paid"))


def lossq_story_reserve(claim):
    return lossq_story_money(lossq_story_field(claim, "reserve", "reserve_amount", "total_reserve", "outstanding_reserve"))


def lossq_story_incurred(claim):
    incurred = lossq_story_money(
        lossq_story_field(
            claim,
            "incurred",
            "total_incurred",
            "gross_incurred",
            "net_incurred",
            "loss_incurred",
        )
    )
    if incurred > 0:
        return incurred
    return lossq_story_paid(claim) + lossq_story_reserve(claim)


def lossq_story_description(claim):
    return lossq_story_text(
        lossq_story_field(
            claim,
            "description",
            "loss_description",
            "claim_description",
            "cause_of_loss",
            "accident_description",
            "notes",
            "summary",
        )
    )


def lossq_story_date(claim):
    return lossq_story_text(
        lossq_story_field(
            claim,
            "loss_date",
            "date_of_loss",
            "claim_date",
            "accident_date",
            "reported_date",
        )
    )


def lossq_format_money(value):
    return "${:,.0f}".format(lossq_story_money(value))


def lossq_build_safety_recommendations(claims):
    claims = claims or []
    total_claims = len(claims)
    open_claims = [claim for claim in claims if lossq_story_is_open(claim)]
    litigated_claims = [claim for claim in claims if lossq_story_litigation(claim)]
    high_severity_claims = [claim for claim in claims if lossq_story_incurred(claim) >= 50000]
    lines = sorted(set(lossq_story_line(claim) for claim in claims))

    recommendations = []

    if total_claims == 0:
        return ["No validated claims are available yet. Upload loss runs before generating safety and risk recommendations."]

    if open_claims:
        recommendations.append(
            f"Request current adjuster status notes on {len(open_claims)} open claim(s), including reserve rationale, next action date, and expected closure timeline."
        )

    if litigated_claims:
        recommendations.append(
            f"Prepare a litigation management update for {len(litigated_claims)} litigated claim(s), including defense counsel status, mediation dates, settlement authority, and expected disposition."
        )

    if high_severity_claims:
        recommendations.append(
            f"Create large-loss narratives for {len(high_severity_claims)} claim(s) over $50,000 and document corrective actions taken after each event."
        )

    for line in lines:
        upper = line.upper()

        if "WORKERS" in upper:
            recommendations.extend([
                "Implement or document return-to-work procedures, supervisor accident reporting, employee safety training, and post-incident corrective action.",
                "Request OSHA logs, safety meeting records, job hazard analysis, and updated workers compensation loss-control materials.",
            ])

        elif "AUTO" in upper:
            recommendations.extend([
                "Document driver qualification standards, MVR review cadence, telematics use, vehicle inspection procedures, and accident review process.",
                "Request driver roster, vehicle schedule, safety manual, maintenance logs, and any fleet safety corrective actions.",
            ])

        elif "CARGO" in upper:
            recommendations.extend([
                "Document cargo securement procedures, theft prevention controls, driver check-in process, and high-value load protocols.",
                "Request cargo contracts, bill-of-lading procedures, warehouse/yard security controls, and cargo claim prevention steps.",
            ])

        elif "PROPERTY" in upper or "BOP" in upper:
            recommendations.extend([
                "Complete property risk-control review focused on maintenance, life safety, water intrusion prevention, fire protection, and inspection logs.",
                "Request property photos, COPE details, roof/plumbing/electrical updates, sprinkler/alarm documentation, and maintenance records.",
            ])

        elif "CYBER" in upper:
            recommendations.extend([
                "Document MFA, backups, endpoint protection, employee phishing training, vendor controls, and incident response procedures.",
                "Request cyber application updates, network security controls, backup testing evidence, and breach response improvements.",
            ])

        elif "EMPLOYMENT" in upper or "EPLI" in upper:
            recommendations.extend([
                "Review HR policies, anti-harassment training, termination procedures, complaint handling, and manager documentation practices.",
                "Request employee handbook, training logs, HR incident documentation, and corrective employment-practice controls.",
            ])

        elif "LIQUOR" in upper:
            recommendations.extend([
                "Document alcohol service training, ID verification, incident logs, security procedures, and intoxication refusal protocols.",
                "Request server training certificates, liquor liability controls, event procedures, and management oversight documentation.",
            ])

        elif "UMBRELLA" in upper or "EXCESS" in upper:
            recommendations.extend([
                "Prepare umbrella-facing claim explanations for all severe/open underlying losses and document controls reducing future severity.",
                "Confirm underlying limits, open reserves, litigation status, and any claim expected to pierce primary coverage.",
            ])

        elif "GENERAL" in upper or "LIABILITY" in upper:
            recommendations.extend([
                "Document premises safety controls, inspection procedures, maintenance logs, incident reporting, and customer/visitor hazard prevention.",
                "Request corrective-action evidence, photos, maintenance records, contracts, certificates of insurance, and claim prevention procedures.",
            ])

    # Universal recommendations
    recommendations.extend([
        "Prepare a carrier-facing improvement letter explaining what changed after the loss experience and how future frequency/severity will be reduced.",
        "Create a renewal document package with updated loss runs, claim status notes, safety controls, exposure changes, and management response.",
    ])

    cleaned = []
    for item in recommendations:
        if item and item not in cleaned:
            cleaned.append(item)

    return cleaned[:12]


def lossq_build_risk_control_plan(claims):
    claims = claims or []
    if not claims:
        return ["No claim activity was available to build a risk-control plan."]

    total_incurred = sum(lossq_story_incurred(claim) for claim in claims)
    total_reserve = sum(lossq_story_reserve(claim) for claim in claims)
    open_count = sum(1 for claim in claims if lossq_story_is_open(claim))
    litigation_count = sum(1 for claim in claims if lossq_story_litigation(claim))

    plan = [
        f"Review {len(claims)} claim(s) totaling {lossq_format_money(total_incurred)} incurred and {lossq_format_money(total_reserve)} reserved.",
        "Separate claim issues into frequency drivers, severity drivers, open reserve issues, and documentation gaps.",
    ]

    if open_count:
        plan.append(f"Prioritize closure strategy for {open_count} open claim(s) before renewal submission.")
    if litigation_count:
        plan.append(f"Obtain litigation action plans for {litigation_count} claim(s) before marketing the account.")
    if total_reserve > 0:
        plan.append("Request reserve review and expected development comments from the adjuster/carrier.")
    if total_incurred >= 100000:
        plan.append("Prepare executive-level narrative explaining large-loss controls and management response.")

    plan.append("Submit evidence of corrective action with the renewal packet to improve carrier confidence.")
    return plan


def lossq_build_underwriting_documents(claims):
    claims = claims or []
    docs = [
        "Updated valued loss runs with open/closed status.",
        "Current open claim notes and reserve rationale.",
        "Large-loss narratives for significant claims.",
        "Management corrective-action letter.",
    ]

    lines = " ".join(lossq_story_line(claim).upper() for claim in claims)

    if "WORKERS" in lines:
        docs.extend(["OSHA logs.", "Safety training records.", "Return-to-work policy."])
    if "AUTO" in lines:
        docs.extend(["Driver roster.", "Vehicle schedule.", "MVR review evidence.", "Fleet safety policy."])
    if "PROPERTY" in lines or "BOP" in lines:
        docs.extend(["Property photos.", "COPE details.", "Maintenance logs.", "Roof/plumbing/electrical updates."])
    if "CYBER" in lines:
        docs.extend(["Cyber controls summary.", "MFA/backups confirmation.", "Incident response plan."])
    if "EMPLOYMENT" in lines or "EPLI" in lines:
        docs.extend(["Employee handbook.", "HR training logs.", "Complaint/discipline procedure summary."])
    if "LIQUOR" in lines:
        docs.extend(["Alcohol service training records.", "Incident/refusal logs.", "Security procedures."])

    cleaned = []
    for doc in docs:
        if doc not in cleaned:
            cleaned.append(doc)
    return cleaned


def lossq_build_claim_stories(claims):
    stories = []

    for claim in claims or []:
        number = lossq_story_claim_number(claim)
        line = lossq_story_line(claim)
        status = lossq_story_status(claim)
        paid = lossq_story_paid(claim)
        reserve = lossq_story_reserve(claim)
        incurred = lossq_story_incurred(claim)
        description = lossq_story_description(claim)
        loss_date = lossq_story_date(claim)
        is_open = lossq_story_is_open(claim)
        litigated = lossq_story_litigation(claim)

        concern_parts = []
        if is_open:
            concern_parts.append("open claim development")
        if reserve > 0:
            concern_parts.append("reserve adequacy")
        if litigated:
            concern_parts.append("litigation exposure")
        if incurred >= 50000:
            concern_parts.append("large-loss severity")
        if not concern_parts:
            concern_parts.append("claim frequency and final loss outcome")

        story = (
            f"Claim {number} is a {line} claim"
            f"{f' with a loss date of {loss_date}' if loss_date else ''}. "
            f"The claim is currently reported as {status}, with {lossq_format_money(paid)} paid, "
            f"{lossq_format_money(reserve)} reserved, and {lossq_format_money(incurred)} total incurred. "
        )

        if description:
            story += f"The reported loss description indicates: {description}. "

        story += (
            f"From an underwriting standpoint, the main items to address are {', '.join(concern_parts)}. "
            "Broker positioning should include current claim status, expected resolution timeline, reserve rationale, "
            "and any corrective actions taken to reduce repeat losses."
        )

        stories.append({
            "claim_number": number,
            "line_of_business": line,
            "status": status,
            "paid": paid,
            "reserve": reserve,
            "incurred": incurred,
            "litigation": litigated,
            "carrier_facing_story": story,
            "broker_positioning": (
                "Provide updated claim notes, explain corrective action, and show why the loss is controlled or unlikely to repeat."
            ),
        })

    return stories


def lossq_build_claim_story_summary(stories):
    if not stories:
        return "No claim stories are available because no validated claims were found."

    open_count = sum(1 for story in stories if str(story.get("status", "")).upper().find("OPEN") >= 0)
    litigated_count = sum(1 for story in stories if story.get("litigation"))
    total_incurred = sum(lossq_story_money(story.get("incurred")) for story in stories)

    return (
        f"LossQ generated carrier-facing narratives for {len(stories)} claim(s), including "
        f"{open_count} open claim(s), {litigated_count} litigated claim(s), and "
        f"{lossq_format_money(total_incurred)} total incurred. These narratives are designed to help brokers explain "
        "loss development, reserve posture, corrective actions, and renewal positioning."
    )


def build_renewal_risk_engine(claims):
    result = lossq_original_build_renewal_risk_engine(claims)

    if not isinstance(result, dict):
        result = {}

    claim_stories = lossq_build_claim_stories(claims or [])
    safety_recommendations = lossq_build_safety_recommendations(claims or [])
    risk_control_plan = lossq_build_risk_control_plan(claims or [])
    recommended_docs = lossq_build_underwriting_documents(claims or [])

    large_loss_narratives = [
        story for story in claim_stories
        if lossq_story_money(story.get("incurred")) >= 50000 or story.get("litigation")
    ]

    result["safety_recommendations"] = safety_recommendations
    result["risk_control_recommendations"] = safety_recommendations
    result["loss_control_plan"] = risk_control_plan
    result["carrier_risk_improvement_plan"] = risk_control_plan
    result["recommended_underwriting_documents"] = recommended_docs
    result["ai_claim_stories"] = claim_stories
    result["large_loss_narratives"] = large_loss_narratives
    result["claim_story_summary"] = lossq_build_claim_story_summary(claim_stories)

    return result



def build_underwriting_intelligence(claims):
    renewal = build_renewal_risk_engine(claims)
    metrics = renewal.get("renewal_metrics", {})
    if len(claims) == 0:
        return {
            **renewal,
            "submission_strength": "Insufficient Data",
            "missing_items": ["Parsed claim rows", "Policy schedule", "Validated loss totals"],
            "recommended_actions": ["Review parser output and re-upload or manually correct the loss run before using underwriting outputs."],
            "summary": "No account-specific claims were available for underwriting analysis.",
            "risk_level": "Insufficient Data",
            "risk_score": None,
            "renewal_risk": "INSUFFICIENT DATA",
            "recommendation": renewal["broker_recommendation"],
            "carrier_narrative": "Insufficient data. Do not send this as a carrier-facing underwriting narrative.",
            "client_narrative": "LossQ needs validated loss run data before producing a client-facing risk summary.",
            "metrics": metrics,
        }

    risk_score = max(0, 100 - int(renewal.get("renewal_score") or 0))
    if risk_score >= 70: risk_level, renewal_risk = "High", "RED"
    elif risk_score >= 40: risk_level, renewal_risk = "Moderate", "YELLOW"
    else: risk_level, renewal_risk = "Low", "GREEN"

    return {
        **renewal,
        "submission_strength": "Weak" if renewal_risk == "RED" else "Moderate" if renewal_risk == "YELLOW" else "Strong",
        "missing_items": [],
        "recommended_actions": renewal.get("renewal_drivers", []),
        "summary": f"{metrics.get('total_claims',0)} claim(s) identified. {metrics.get('open_claims',0)} open. Total incurred is ${metrics.get('total_incurred',0):,.2f}. {metrics.get('litigation_claims',0)} litigation-related claim(s) detected.",
        "risk_level": risk_level,
        "risk_score": risk_score,
        "renewal_risk": renewal_risk,
        "recommendation": renewal.get("broker_recommendation"),
        "carrier_narrative": renewal.get("renewal_summary"),
        "client_narrative": renewal.get("renewal_summary"),
        "metrics": metrics,
    }




# LOSSQ_EXPOSURE_AWARE_UNDERWRITING_SUMMARY_V1
def lossq_summary_money_value(value):
    try:
        cleaned = str(value or "").replace("$", "").replace(",", "").replace("%", "").strip()
        if cleaned in {"", "-", "None", "none", "null"}:
            return 0.0
        return float(cleaned)
    except Exception:
        return 0.0

def lossq_summary_int_value(value):
    try:
        cleaned = str(value or "").replace(",", "").strip()
        if cleaned in {"", "-", "None", "none", "null"}:
            return 0
        return int(float(cleaned))
    except Exception:
        return 0

def lossq_summary_apply_exposure(result, profile_data, claims):
    result = dict(result or {})
    profile_data = profile_data or {}

    current_premium = lossq_summary_money_value(profile_data.get("current_premium") or profile_data.get("expiring_premium"))
    target_premium = lossq_summary_money_value(profile_data.get("target_renewal_premium"))
    payroll = lossq_summary_money_value(profile_data.get("payroll"))
    revenue = lossq_summary_money_value(profile_data.get("revenue") or profile_data.get("sales") or profile_data.get("receipts"))
    property_tiv = lossq_summary_money_value(profile_data.get("property_tiv") or profile_data.get("tiv"))
    coverage_limit = lossq_summary_money_value(profile_data.get("coverage_limit") or profile_data.get("limits"))
    vehicle_count = lossq_summary_int_value(profile_data.get("vehicle_count"))
    driver_count = lossq_summary_int_value(profile_data.get("driver_count"))
    employee_count = lossq_summary_int_value(profile_data.get("employee_count"))
    experience_mod = lossq_summary_money_value(profile_data.get("experience_mod") or profile_data.get("mod"))
    line_of_business = str(profile_data.get("line_of_business") or profile_data.get("exposure_basis") or "").strip()

    exposure_drivers = []
    risk_delta = 0

    if current_premium:
        exposure_drivers.append(f"Current premium considered: ${current_premium:,.0f}.")
    if target_premium:
        exposure_drivers.append(f"Target renewal premium considered: ${target_premium:,.0f}.")
    if payroll:
        exposure_drivers.append(f"Payroll exposure considered: ${payroll:,.0f}.")
    if revenue:
        exposure_drivers.append(f"Revenue or sales exposure considered: ${revenue:,.0f}.")
    if vehicle_count:
        exposure_drivers.append(f"Vehicle count considered: {vehicle_count}.")
    if driver_count:
        exposure_drivers.append(f"Driver count considered: {driver_count}.")
    if employee_count:
        exposure_drivers.append(f"Employee count considered: {employee_count}.")
    if property_tiv:
        exposure_drivers.append(f"Property TIV considered: ${property_tiv:,.0f}.")
    if coverage_limit:
        exposure_drivers.append(f"Coverage limit considered: ${coverage_limit:,.0f}.")
    if experience_mod:
        exposure_drivers.append(f"Experience mod considered: {experience_mod:.2f}.")

    if not exposure_drivers and not line_of_business:
        result["exposure_inputs_used"] = False
    return result

    total_incurred = 0.0
    for claim in claims or []:
        total_incurred += lossq_summary_money_value(
            getattr(claim, "total_incurred", None)
            or getattr(claim, "incurred", None)
            or getattr(claim, "loss_amount", None)
        )

    if current_premium > 0 and total_incurred > 0:
        loss_ratio = total_incurred / current_premium
        if loss_ratio >= 0.75:
            risk_delta += 10
            exposure_drivers.append(f"Loss ratio pressure: {loss_ratio * 100:.1f}% of saved current premium.")
        elif loss_ratio <= 0.35:
            risk_delta -= 5
            exposure_drivers.append(f"Favorable loss ratio: {loss_ratio * 100:.1f}% of saved current premium.")

    if experience_mod >= 1.25:
        risk_delta += 8
    elif 0 < experience_mod <= 0.90:
        risk_delta -= 4

    if vehicle_count >= 25 or driver_count >= 25:
        risk_delta += 5

    if property_tiv >= 10000000:
        risk_delta += 3

    score = result.get("renewal_score")
    try:
        score = int(score)
        score = max(0, min(100, score + risk_delta))
        result["renewal_score"] = score

        if score >= 70:
            result["renewal_risk_level"] = "High"
            result["renewal_risk"] = "RED"
        elif score >= 40:
            result["renewal_risk_level"] = "Moderate"
            result["renewal_risk"] = "YELLOW"
        else:
            result["renewal_risk_level"] = "Low"
            result["renewal_risk"] = "GREEN"
    except Exception:
        pass

    result["exposure_inputs_used"] = True
    result["exposure_drivers"] = exposure_drivers
    result["exposure_profile"] = {
        "line_of_business": line_of_business,
        "current_premium": current_premium,
        "target_renewal_premium": target_premium,
        "payroll": payroll,
        "revenue": revenue,
        "vehicle_count": vehicle_count,
        "driver_count": driver_count,
        "employee_count": employee_count,
        "property_tiv": property_tiv,
        "coverage_limit": coverage_limit,
        "experience_mod": experience_mod,
    }

    result["renewal_summary"] = (
        str(result.get("renewal_summary") or result.get("summary") or "").rstrip()
        + f" Saved Exposure Inputs were included in the renewal risk review for {line_of_business or 'the selected account'}."
    ).strip()

    return result




# LOSSQ_SUMMARY_DIRECT_FULL_ACCOUNT_PROFILE_EXPOSURE_LOOKUP_V1
def lossq_summary_profile_get(profile_data, key, default=None):
    if profile_data is None:
        return default

    if isinstance(profile_data, dict):
        value = profile_data.get(key, default)
        return default if value is None else value

    try:
        value = getattr(profile_data, key, default)
        return default if value is None else value
    except Exception:
        return default


def lossq_summary_normalize_profile_data(profile_data):
    if profile_data is None:
        return {}

    if isinstance(profile_data, dict):
        normalized = dict(profile_data)
    else:
        normalized = {}

    keys = [
        "id",
        "business_name",
        "carrier_name",
        "writing_carrier",
        "agency_name",
        "policy_number",
        "account_number",
        "customer_number",
        "effective_date",
        "expiration_date",
        "evaluation_date",
        "state",
        "current_premium",
        "expiring_premium",
        "target_renewal_premium",
        "line_of_business",
        "exposure_basis",
        "class_code",
        "class_codes",
        "limits",
        "coverage_limit",
        "deductible",
        "retention",
        "payroll",
        "revenue",
        "sales",
        "receipts",
        "employee_count",
        "vehicle_count",
        "driver_count",
        "experience_mod",
        "mod",
        "property_tiv",
        "tiv",
        "building_value",
        "contents_value",
        "square_footage",
        "location_count",
        "unit_count",
        "umbrella_limit",
        "cargo_limit",
        "underwriter_notes",
        "policies",
    ]

    for key in keys:
        if not normalized.get(key):
            value = lossq_summary_profile_get(profile_data, key)
            if value not in (None, ""):
                normalized[key] = value

    return normalized


def lossq_summary_safe_policy_json(value):
    if isinstance(value, list):
        return value

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []

    return []


def lossq_summary_full_profile_for_exposure(db, current_user, policy_number, result=None):
    organization_id = current_user.get("organization_id") if isinstance(current_user, dict) else None

    result_profile = {}
    try:
        result_profile = dict((result or {}).get("account_profile") or {})
    except Exception:
        result_profile = {}

    if not organization_id:
        return lossq_summary_normalize_profile_data(result_profile)

    profile_id = result_profile.get("id")

    try:
        if profile_id:
            profile = (
                db.query(AccountProfile)
                .filter(AccountProfile.organization_id == organization_id)
                .filter(AccountProfile.id == int(profile_id))
                .first()
            )
            if profile:
                return lossq_summary_normalize_profile_data(profile)
    except Exception:
        pass

    selected_policy = str(policy_number or "").strip().upper()

    candidate_values = set()
    for key in ["policy_number", "account_number", "customer_number"]:
        value = str(result_profile.get(key) or "").strip().upper()
        if value:
            candidate_values.add(value)

    if selected_policy:
        candidate_values.add(selected_policy)

    try:
        profiles = (
            db.query(AccountProfile)
            .filter(AccountProfile.organization_id == organization_id)
            .all()
        )

        for profile in profiles:
            profile_values = {
                str(getattr(profile, "policy_number", "") or "").strip().upper(),
                str(getattr(profile, "account_number", "") or "").strip().upper(),
                str(getattr(profile, "customer_number", "") or "").strip().upper(),
            }

            policies = lossq_summary_safe_policy_json(getattr(profile, "policies", None))
            for item in policies:
                if isinstance(item, dict):
                    pnum = str(
                        item.get("policy_number")
                        or item.get("policyNumber")
                        or item.get("policy")
                        or ""
                    ).strip().upper()
                    if pnum:
                        profile_values.add(pnum)

            if candidate_values & profile_values:
                return lossq_summary_normalize_profile_data(profile)

    except Exception:
        pass

    return lossq_summary_normalize_profile_data(result_profile)



def lossq_summary_force_exposure_from_full_profile(db, current_user, policy_number, result, claims):
    result = dict(result or {})
    profile_data = lossq_summary_full_profile_for_exposure(db, current_user, policy_number, result)

    result["account_profile"] = profile_data

    current_premium = lossq_summary_money_value(profile_data.get("current_premium") or profile_data.get("expiring_premium"))
    target_premium = lossq_summary_money_value(profile_data.get("target_renewal_premium"))
    payroll = lossq_summary_money_value(profile_data.get("payroll"))
    revenue = lossq_summary_money_value(profile_data.get("revenue") or profile_data.get("sales") or profile_data.get("receipts"))
    property_tiv = lossq_summary_money_value(profile_data.get("property_tiv") or profile_data.get("tiv"))
    coverage_limit = lossq_summary_money_value(profile_data.get("coverage_limit") or profile_data.get("limits"))
    deductible = lossq_summary_money_value(profile_data.get("deductible"))
    retention = lossq_summary_money_value(profile_data.get("retention"))
    experience_mod = lossq_summary_money_value(profile_data.get("experience_mod") or profile_data.get("mod"))

    vehicle_count = lossq_summary_int_value(profile_data.get("vehicle_count"))
    driver_count = lossq_summary_int_value(profile_data.get("driver_count"))
    employee_count = lossq_summary_int_value(profile_data.get("employee_count"))
    location_count = lossq_summary_int_value(profile_data.get("location_count"))

    line_of_business = str(profile_data.get("line_of_business") or profile_data.get("exposure_basis") or "").strip()

    exposure_drivers = []

    if current_premium:
        exposure_drivers.append(f"Current premium considered: ${current_premium:,.0f}.")
    if target_premium:
        exposure_drivers.append(f"Target renewal premium considered: ${target_premium:,.0f}.")
    if payroll:
        exposure_drivers.append(f"Payroll exposure considered: ${payroll:,.0f}.")
    if revenue:
        exposure_drivers.append(f"Revenue or sales exposure considered: ${revenue:,.0f}.")
    if vehicle_count:
        exposure_drivers.append(f"Vehicle count considered: {vehicle_count}.")
    if driver_count:
        exposure_drivers.append(f"Driver count considered: {driver_count}.")
    if employee_count:
        exposure_drivers.append(f"Employee count considered: {employee_count}.")
    if location_count:
        exposure_drivers.append(f"Location count considered: {location_count}.")
    if property_tiv:
        exposure_drivers.append(f"Property TIV considered: ${property_tiv:,.0f}.")
    if deductible:
        exposure_drivers.append(f"Deductible considered: ${deductible:,.0f}.")
    if retention:
        exposure_drivers.append(f"Retention or SIR considered: ${retention:,.0f}.")
    if experience_mod:
        exposure_drivers.append(f"Experience mod considered: {experience_mod:.2f}.")

    total_incurred = 0.0
    for claim in claims or []:
        total_incurred += lossq_summary_money_value(
            getattr(claim, "total_incurred", None)
            or getattr(claim, "incurred", None)
            or getattr(claim, "loss_amount", None)
        )

    if current_premium > 0 and total_incurred > 0:
        loss_ratio = total_incurred / current_premium
        exposure_drivers.append(f"Loss ratio using saved current premium: {loss_ratio * 100:.1f}%.")

    if not exposure_drivers and not line_of_business:
        result["exposure_inputs_used"] = False
        result["lossq_exposure_patch_version"] = "LOSSQ_SUMMARY_FORCE_EXPOSURE_PROFILE_V2_NO_EXPOSURE_FOUND"
        return result

    result["exposure_inputs_used"] = True
    result["exposure_profile"] = {
        "primary_line_of_business": line_of_business or "Not specified",
        "current_premium": current_premium,
        "target_renewal_premium": target_premium,
        "payroll": payroll,
        "revenue": revenue,
        "vehicle_count": vehicle_count,
        "driver_count": driver_count,
        "employee_count": employee_count,
        "location_count": location_count,
        "property_tiv": property_tiv,
        "coverage_limit": coverage_limit,
        "deductible": deductible,
        "retention": retention,
        "experience_mod": experience_mod,
    }
    result["exposure_drivers"] = exposure_drivers
    result["lossq_exposure_patch_version"] = "LOSSQ_SUMMARY_FORCE_EXPOSURE_PROFILE_V2"

    summary_text = str(result.get("renewal_summary") or result.get("summary") or "").rstrip()
    result["renewal_summary"] = (
        summary_text
        + f" Saved Exposure Inputs were included in the renewal risk review for {line_of_business or 'the selected account'}."
    ).strip()

    return result


# LOSSQ_SUMMARY_FORCE_RESULT_ACCOUNT_PROFILE_EXPOSURE_V1
def lossq_summary_profile_has_exposure(profile_data):
    if not isinstance(profile_data, dict):
        return False

    keys = [
        "current_premium",
        "expiring_premium",
        "target_renewal_premium",
        "payroll",
        "revenue",
        "sales",
        "receipts",
        "vehicle_count",
        "driver_count",
        "employee_count",
        "experience_mod",
        "mod",
        "line_of_business",
        "class_code",
        "class_codes",
        "limits",
        "coverage_limit",
        "deductible",
        "retention",
        "property_tiv",
        "tiv",
    ]

    for key in keys:
        value = profile_data.get(key)
        if value not in (None, "", "0", "$0", 0):
            return True

    return False


def lossq_summary_force_exposure_from_result_profile(result, claims):
    result = dict(result or {})
    profile_data = result.get("account_profile") or {}

    if not lossq_summary_profile_has_exposure(profile_data):
        result["exposure_inputs_used"] = False
        result["lossq_exposure_patch_version"] = "LOSSQ_SUMMARY_FORCE_RESULT_ACCOUNT_PROFILE_EXPOSURE_V1_NO_EXPOSURE_FOUND"
        return result

    result = lossq_summary_apply_exposure(result, profile_data, claims)
    result["lossq_exposure_patch_version"] = "LOSSQ_SUMMARY_FORCE_RESULT_ACCOUNT_PROFILE_EXPOSURE_V1"
    return result


@router.get("/underwriting")
def underwriting_summary(policy_number: str | None = Query(default=None), db: Session = Depends(get_db), current_user: dict = Depends(require_package_access)):
    claims, policy_numbers_used, profile_data = get_claims_for_account(db, current_user, policy_number)
    quality = data_quality(claims, policy_numbers_used, profile_data)

    result = lossq_summary_apply_exposure(build_underwriting_intelligence(claims), profile_data, claims)
    result = {
        **result,
        "data_quality": quality,
        "is_credible": quality["is_credible"],
        "policy_number": policy_number,
        "policy_numbers_used": policy_numbers_used,
        "claims_used": len(claims),
        "account_profile": profile_data,
    }

    result = lossq_summary_force_exposure_from_full_profile(db, current_user, policy_number, result, claims)
    return result
