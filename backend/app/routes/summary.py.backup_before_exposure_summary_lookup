from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
import json

from app.database import SessionLocal
from app.models.claim import Claim
from app.models.account_profile import AccountProfile
from app.auth_utils import get_current_user

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


def build_renewal_risk_engine(claims):
    total_claims = len(claims)
    open_claims = len([c for c in claims if is_open_claim(c)])
    closed_claims = max(total_claims - open_claims, 0)
    litigation_claims = len([c for c in claims if has_litigation(c)])
    flagged_claims = len([c for c in claims if is_flagged_claim(c)])
    total_paid = sum(money(getattr(c, "paid_amount", 0)) for c in claims)
    total_reserve = sum(money(getattr(c, "reserve_amount", 0)) for c in claims)
    total_incurred = sum(money(getattr(c, "total_incurred", 0)) for c in claims)
    average_severity = total_incurred / total_claims if total_claims else 0
    large_claims = len([c for c in claims if money(getattr(c, "total_incurred", 0)) >= 100000])
    severe_claims = len([c for c in claims if money(getattr(c, "total_incurred", 0)) >= 250000])
    open_reserve_pressure = total_reserve / total_incurred if total_incurred else 0

    if total_claims == 0:
        return {
            "renewal_score": None,
            "renewal_risk_level": "Insufficient Data",
            "renewal_drivers": ["No account-specific claims were found. LossQ cannot credibly rate renewal risk."],
            "carrier_concerns": ["Loss run extraction must be reviewed before carrier-facing outputs are used."],
            "broker_recommendation": "Do not rely on this renewal result until claims and policy schedule are populated.",
            "renewal_summary": "Insufficient claim data. Renewal risk has not been rated.",
            "renewal_metrics": {
                "total_claims": 0, "open_claims": 0, "closed_claims": 0, "litigation_claims": 0,
                "flagged_claims": 0, "large_claims": 0, "severe_claims": 0,
                "total_paid": 0, "total_reserve": 0, "total_incurred": 0,
                "average_severity": 0, "open_reserve_pressure": 0,
            },
        }

    score = 100
    score -= min(total_claims * 4, 24)
    score -= min(open_claims * 10, 30)
    score -= min(litigation_claims * 16, 36)
    score -= min(flagged_claims * 8, 24)
    score -= min(large_claims * 12, 24)
    score -= min(severe_claims * 18, 36)
    if total_incurred >= 1000000: score -= 30
    elif total_incurred >= 500000: score -= 22
    elif total_incurred >= 250000: score -= 14
    elif total_incurred >= 100000: score -= 7
    if total_reserve >= 250000: score -= 18
    elif total_reserve >= 100000: score -= 10
    elif total_reserve >= 50000: score -= 6
    if average_severity >= 100000: score -= 12
    elif average_severity >= 50000: score -= 6
    if open_reserve_pressure >= 0.50: score -= 10
    elif open_reserve_pressure >= 0.25: score -= 5
    score = max(0, min(100, round(score)))

    if score >= 80:
        level = "Low"
    elif score >= 60:
        level = "Moderate"
    elif score >= 40:
        level = "High"
    else:
        level = "Critical"

    drivers = [f"{total_claims} account-specific claim(s) identified.", f"Total incurred losses are ${total_incurred:,.2f}."]
    if open_claims: drivers.append(f"{open_claims} open claim(s) create renewal uncertainty.")
    if litigation_claims: drivers.append(f"{litigation_claims} litigated claim(s) increase severity uncertainty.")
    if total_reserve: drivers.append(f"Outstanding reserves total ${total_reserve:,.2f}.")
    if large_claims: drivers.append(f"{large_claims} large claim(s) exceed $100,000.")
    if flagged_claims: drivers.append(f"{flagged_claims} flagged/watch claim(s) require explanation.")

    concerns = []
    if open_claims: concerns.append("Open claims may continue to develop before renewal.")
    if litigation_claims: concerns.append("Litigation increases uncertainty around ultimate loss severity.")
    if total_reserve >= 50000: concerns.append("Outstanding reserves may affect loss development and pricing.")
    if total_claims >= 5: concerns.append("Claim frequency may raise carrier concerns about controls or operations.")
    if large_claims: concerns.append("Large losses require detailed claim narratives and corrective action.")
    if not concerns: concerns.append("No major carrier concerns detected from the account-specific loss data.")

    if level == "Low":
        rec = "Proceed with standard renewal marketing after confirming loss runs are currently valued."
    elif level == "Moderate":
        rec = "Prepare a broker narrative addressing open claims, reserves, and corrective actions."
    elif level == "High":
        rec = "Build detailed claim narratives, reserve updates, litigation status, and loss-control documentation before marketing."
    else:
        rec = "Treat as critical renewal. Obtain updated loss runs, litigation updates, reserve explanations, and corrective-action plan before approaching markets."

    return {
        "renewal_score": score,
        "renewal_risk_level": level,
        "renewal_drivers": drivers,
        "carrier_concerns": concerns,
        "broker_recommendation": rec,
        "renewal_summary": f"The selected account has a renewal score of {score}/100, indicating {level.lower()} renewal risk based on {total_claims} claims, {open_claims} open claims, ${total_incurred:,.2f} total incurred, ${total_reserve:,.2f} reserves, and {litigation_claims} litigated claims.",
        "renewal_metrics": {
            "total_claims": total_claims, "open_claims": open_claims, "closed_claims": closed_claims,
            "litigation_claims": litigation_claims, "flagged_claims": flagged_claims,
            "large_claims": large_claims, "severe_claims": severe_claims,
            "total_paid": total_paid, "total_reserve": total_reserve, "total_incurred": total_incurred,
            "average_severity": average_severity, "open_reserve_pressure": open_reserve_pressure,
        },
    }


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


@router.get("/underwriting")
def underwriting_summary(policy_number: str | None = Query(default=None), db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    claims, policy_numbers_used, profile_data = get_claims_for_account(db, current_user, policy_number)
    quality = data_quality(claims, policy_numbers_used, profile_data)
    result = lossq_summary_apply_exposure(build_underwriting_intelligence(claims), profile_data, claims)
    return {**result, "data_quality": quality, "is_credible": quality["is_credible"], "policy_number": policy_number, "policy_numbers_used": policy_numbers_used, "claims_used": len(claims), "account_profile": profile_data}
