from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime

from app.database import SessionLocal
from app.auth_utils import get_current_user
from app.routes.summary import build_underwriting_intelligence, get_claims_for_account, data_quality, money, is_open_claim, has_litigation, is_flagged_claim
from app.models.claim import Claim
from app.models.account_profile import AccountProfile
import json
import re

router = APIRouter(prefix="/renewal", tags=["Renewal"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def is_open(claim):
    return is_open_claim(claim)


def is_litigated(claim):
    return has_litigation(claim)


def claim_year(claim):
    raw = getattr(claim, "date_of_loss", None) or getattr(claim, "loss_date", None)
    if not raw:
        return None
    raw = str(raw).strip()
    for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%m-%d-%y"]:
        try:
            return datetime.strptime(raw, fmt).year
        except Exception:
            pass
    return None


def get_loss_metrics(claims):
    total_claims = len(claims)
    open_claims = len([c for c in claims if is_open(c)])
    litigation_claims = len([c for c in claims if is_litigated(c)])
    flagged_claims = len([c for c in claims if is_flagged_claim(c)])
    total_paid = sum(money(getattr(c, "paid_amount", 0)) for c in claims)
    total_reserve = sum(money(getattr(c, "reserve_amount", 0)) for c in claims)
    total_incurred = sum(money(getattr(c, "total_incurred", 0)) for c in claims)
    largest_loss = max([money(getattr(c, "total_incurred", 0)) for c in claims], default=0)
    average_claim_size = total_incurred / total_claims if total_claims else 0
    large_claims = len([c for c in claims if money(getattr(c, "total_incurred", 0)) >= 100000])
    severe_claims = len([c for c in claims if money(getattr(c, "total_incurred", 0)) >= 250000])
    yearly = {}
    for claim in claims:
        year = claim_year(claim)
        if year:
            yearly[year] = yearly.get(year, 0) + money(getattr(claim, "total_incurred", 0))
    trend = "Stable"
    years = sorted(yearly)
    if len(years) >= 2 and yearly[years[0]] > 0:
        if yearly[years[-1]] > yearly[years[0]] * 1.35:
            trend = "Deteriorating"
        elif yearly[years[-1]] < yearly[years[0]] * 0.75:
            trend = "Improving"
    return {
        "total_claims": total_claims, "open_claims": open_claims, "closed_claims": max(total_claims-open_claims,0),
        "litigation_claims": litigation_claims, "flagged_claims": flagged_claims,
        "total_paid": total_paid, "total_reserve": total_reserve, "total_incurred": total_incurred,
        "largest_loss": largest_loss, "average_claim_size": average_claim_size,
        "large_claims": large_claims, "severe_claims": severe_claims,
        "open_claim_percentage": (open_claims/total_claims*100) if total_claims else 0,
        "yearly_incurred": yearly, "trend": trend,
    }


def insufficient_response(policy_number=None, engine="engine"):
    return {
        "policy_number": policy_number,
        "is_credible": False,
        "data_quality": {"is_credible": False, "status": "Insufficient Data", "issues": ["No validated account-specific claims are available."]},
        "claims_used": 0,
        "engine_status": "Insufficient Data",
        "warning": "LossQ cannot produce a credible underwriting result until claims are parsed and saved for the selected account/policies.",
    }


def build_underwriter_decision_engine(claims, policy_number=None):
    if len(claims) == 0:
        return {**insufficient_response(policy_number, "decision"), "renewal_probability": None, "expected_premium_impact": "Insufficient Data", "carrier_appetite": "Insufficient Data", "marketability_score": None, "submission_readiness": "Needs validated claims before marketing", "underwriting_concerns": ["No claims available for underwriting decision."], "best_market_types": [], "underwriter_decision_summary": "Insufficient claim data. Do not rely on this decision."}
    intelligence = build_underwriting_intelligence(claims)
    metrics = get_loss_metrics(claims)
    renewal_score = int(intelligence.get("renewal_score") or 0)
    probability = renewal_score
    if metrics["open_claims"] >= 3: probability -= 8
    if metrics["litigation_claims"] > 0: probability -= min(metrics["litigation_claims"]*10, 25)
    if metrics["severe_claims"] > 0: probability -= 10
    if metrics["total_claims"] >= 10: probability -= 8
    elif metrics["total_claims"] >= 5: probability -= 4
    if metrics["trend"] == "Deteriorating": probability -= 8
    # Floor at 15 for accounts with real claims - 0% implies uninsurable which is rare
    probability = max(15, min(100, probability)) if len(claims) > 0 else 0
    probability = min(100, probability)
    marketability = probability - (min(metrics["flagged_claims"]*5, 15) if metrics["flagged_claims"] else 0)
    if metrics["total_reserve"] > 100000: marketability -= 8
    marketability = max(0, min(100, marketability))
    if probability >= 85: impact, appetite, ready = "Flat to +5%", "Strong", "Ready for standard renewal marketing"
    elif probability >= 70: impact, appetite, ready = "+5% to +15%", "Moderate", "Marketable with broker narrative"
    elif probability >= 50: impact, appetite, ready = "+15% to +35%", "Limited", "Needs claim narratives and reserve explanations before marketing"
    else: impact, appetite, ready = "+35% or higher / possible non-renewal concern", "Restricted", "Not ready without corrective-action documentation"
    concerns = []
    if metrics["open_claims"]: concerns.append(f"{metrics['open_claims']} open claim(s) may continue developing.")
    if metrics["litigation_claims"]: concerns.append(f"{metrics['litigation_claims']} litigated claim(s) create uncertainty.")
    if metrics["total_reserve"]: concerns.append(f"${metrics['total_reserve']:,.2f} in reserves may pressure renewal terms.")
    if metrics["large_claims"]: concerns.append(f"{metrics['large_claims']} large claim(s) exceed $100,000.")
    if metrics["total_claims"] >= 5: concerns.append("Claim frequency may raise carrier concerns.")
    return {"policy_number": policy_number, "is_credible": True, "renewal_probability": probability, "expected_premium_impact": impact, "carrier_appetite": appetite, "marketability_score": marketability, "submission_readiness": ready, "underwriting_concerns": concerns or ["No major underwriting concerns detected."], "best_market_types": ["Regional commercial markets", "Middle-market carriers", "Specialty markets if standard appetite is limited"], "decision_metrics": metrics, "underwriter_decision_summary": f"LossQ estimates a {probability}% renewal probability based on {metrics['total_claims']} account-specific claims, {metrics['open_claims']} open claims, ${metrics['total_incurred']:,.2f} incurred, ${metrics['total_reserve']:,.2f} reserves, and {metrics['litigation_claims']} litigated claims."}


def build_carrier_appetite_engine(claims, policy_number=None):
    if len(claims) == 0:
        return {**insufficient_response(policy_number, "carrier-appetite"), "carrier_appetite_score": None, "carrier_appetite_level": "Insufficient Data", "best_fit_carriers": [], "poor_fit_carriers": [], "carrier_match_reasons": ["No validated claims available."], "market_strategy": "Do not market until loss data is validated.", "placement_summary": "Insufficient claim data. Carrier appetite has not been rated."}
    decision = build_underwriter_decision_engine(claims, policy_number)
    metrics = get_loss_metrics(claims)
    score = int(decision.get("marketability_score") or 0)
    if metrics["litigation_claims"]: score -= min(metrics["litigation_claims"]*8, 20)
    if metrics["severe_claims"]: score -= 10
    if metrics["open_claims"] >= 3: score -= 6
    if metrics["total_reserve"] >= 250000: score -= 10
    elif metrics["total_reserve"] >= 100000: score -= 5
    if metrics["total_claims"] >= 10: score -= 8
    elif metrics["total_claims"] >= 5: score -= 4
    score = max(0, min(100, score))
    level = "Preferred" if score >= 85 else "Strong" if score >= 70 else "Moderate" if score >= 55 else "Limited" if score >= 40 else "Distressed"
    return {"policy_number": policy_number, "is_credible": True, "carrier_appetite_score": score, "carrier_appetite_level": level, "best_fit_carriers": [], "poor_fit_carriers": [], "carrier_match_reasons": [f"Total claims reviewed: {metrics['total_claims']}", f"Open claims reviewed: {metrics['open_claims']}", f"Litigation claims reviewed: {metrics['litigation_claims']}", f"Reserve exposure: ${metrics['total_reserve']:,.0f}"], "market_strategy": "Use account-specific claim narratives and target markets whose appetite matches the actual loss profile.", "placement_summary": f"Carrier appetite is {score}/100, rated {level}, based on {metrics['total_claims']} account-specific claims and ${metrics['total_incurred']:,.2f} incurred.", "appetite_metrics": metrics}


def build_carrier_match_engine(claims, policy_number=None):
    """
    Real named carrier matching engine.

    This is not a quote engine and does not guarantee carrier eligibility.
    It ranks named carrier options from a rules-based appetite directory using
    actual validated claim data: coverage lines, open claims, reserves, severity,
    total incurred, and litigation indicators.
    """

    if not claims:
        return {
            **insufficient_response(policy_number, "carrier-match"),
            "carrier_database_enabled": True,
            "real_carrier_database_enabled": True,
            "result_type": "no_validated_claims",
            "top_carriers": [],
            "recommended_carrier": "Insufficient Data",
            "recommended_score": None,
            "carrier_match_summary": "No carrier match generated because claims were not parsed or validated.",
        }

    metrics = get_loss_metrics(claims)

    total_claims = int(metrics.get("total_claims") or 0)
    open_claims = int(metrics.get("open_claims") or 0)
    litigation_claims = int(metrics.get("litigation_claims") or 0)
    total_incurred = float(metrics.get("total_incurred") or 0)
    total_reserve = float(metrics.get("total_reserve") or 0)

    large_loss_count = 0
    lines = set()

    for claim in claims:
        incurred = money(
            getattr(claim, "total_incurred", None)
            or getattr(claim, "incurred", None)
            or getattr(claim, "total_amount", None)
            or 0
        )

        if incurred >= 50000:
            large_loss_count += 1

        line_text = str(
            getattr(claim, "line_of_business", "")
            or getattr(claim, "claim_type", "")
            or getattr(claim, "coverage", "")
            or ""
        ).lower()

        policy_text = str(getattr(claim, "policy_number", "") or "").upper()

        if "auto" in line_text or "-AL-" in policy_text:
            lines.add("auto")
        if "general" in line_text or "liability" in line_text or "-GL-" in policy_text:
            lines.add("gl")
        if "worker" in line_text or "comp" in line_text or "-WC-" in policy_text:
            lines.add("wc")
        if "cargo" in line_text or "-CG-" in policy_text:
            lines.add("cargo")

    # If line extraction is weak, infer from policy number patterns.
    if not lines:
        for claim in claims:
            policy_text = str(getattr(claim, "policy_number", "") or "").upper()
            if "-AL-" in policy_text:
                lines.add("auto")
            elif "-GL-" in policy_text:
                lines.add("gl")
            elif "-WC-" in policy_text:
                lines.add("wc")
            elif "-CG-" in policy_text:
                lines.add("cargo")

    has_auto = "auto" in lines
    has_gl = "gl" in lines
    has_wc = "wc" in lines
    has_cargo = "cargo" in lines

    open_claim_pressure = open_claims * 4
    reserve_pressure = 8 if total_reserve >= 50000 else 4 if total_reserve >= 25000 else 0
    severity_pressure = large_loss_count * 7
    litigation_pressure = litigation_claims * 10
    frequency_pressure = max(0, total_claims - 3) * 2

    overall_pressure = min(
        45,
        open_claim_pressure
        + reserve_pressure
        + severity_pressure
        + litigation_pressure
        + frequency_pressure,
    )

    carrier_directory = [
        {
            "carrier": "Berkley Transportation",
            "group": "W. R. Berkley / Berkley",
            "lines": ["auto", "gl", "cargo"],
            "market_category": "Transportation specialty",
            "base_score": 82,
            "open_claim_sensitivity": 0.75,
            "severity_sensitivity": 0.75,
            "litigation_sensitivity": 0.70,
            "best_for": "Transportation, trucking, auto liability, cargo, and casualty accounts.",
        },
        {
            "carrier": "National General",
            "group": "National General",
            "lines": ["auto"],
            "market_category": "Commercial auto",
            "base_score": 76,
            "open_claim_sensitivity": 0.90,
            "severity_sensitivity": 0.85,
            "litigation_sensitivity": 0.90,
            "best_for": "Commercial vehicle and auto-driven accounts.",
        },
        {
            "carrier": "Progressive Commercial",
            "group": "Progressive",
            "lines": ["auto"],
            "market_category": "Commercial auto / trucking",
            "base_score": 78,
            "open_claim_sensitivity": 0.85,
            "severity_sensitivity": 0.80,
            "litigation_sensitivity": 0.85,
            "best_for": "Commercial auto and transportation accounts with documented controls.",
        },
        {
            "carrier": "Great West Casualty",
            "group": "Great West",
            "lines": ["auto", "cargo"],
            "market_category": "Trucking specialty",
            "base_score": 80,
            "open_claim_sensitivity": 0.80,
            "severity_sensitivity": 0.75,
            "litigation_sensitivity": 0.75,
            "best_for": "Trucking-focused accounts with auto liability and cargo exposure.",
        },
        {
            "carrier": "Travelers",
            "group": "Travelers",
            "lines": ["auto", "gl", "wc"],
            "market_category": "Standard commercial / middle market",
            "base_score": 74,
            "open_claim_sensitivity": 1.00,
            "severity_sensitivity": 0.95,
            "litigation_sensitivity": 0.95,
            "best_for": "Standard commercial accounts with controlled loss activity.",
        },
        {
            "carrier": "The Hartford",
            "group": "The Hartford",
            "lines": ["auto", "gl", "wc"],
            "market_category": "Small commercial / middle market",
            "base_score": 72,
            "open_claim_sensitivity": 1.00,
            "severity_sensitivity": 0.95,
            "litigation_sensitivity": 0.95,
            "best_for": "Small commercial and middle-market accounts with complete submission data.",
        },
        {
            "carrier": "Liberty Mutual / State Auto",
            "group": "Liberty Mutual / State Auto",
            "lines": ["auto", "gl", "wc"],
            "market_category": "Regional / standard commercial",
            "base_score": 70,
            "open_claim_sensitivity": 1.00,
            "severity_sensitivity": 1.00,
            "litigation_sensitivity": 1.00,
            "best_for": "Regional commercial accounts with standard underwriting characteristics.",
        },
        {
            "carrier": "CNA",
            "group": "CNA",
            "lines": ["gl", "wc", "auto"],
            "market_category": "Middle market casualty",
            "base_score": 70,
            "open_claim_sensitivity": 1.05,
            "severity_sensitivity": 1.00,
            "litigation_sensitivity": 1.00,
            "best_for": "Middle-market casualty accounts with complete risk documentation.",
        },
        {
            "carrier": "Zurich",
            "group": "Zurich",
            "lines": ["auto", "gl", "wc", "cargo"],
            "market_category": "Middle market / large account",
            "base_score": 68,
            "open_claim_sensitivity": 1.05,
            "severity_sensitivity": 1.00,
            "litigation_sensitivity": 1.00,
            "best_for": "Larger or more complex accounts with strong submission support.",
        },
        {
            "carrier": "biBerk",
            "group": "Berkshire Hathaway / biBerk",
            "lines": ["gl", "wc"],
            "market_category": "Small business direct",
            "base_score": 66,
            "open_claim_sensitivity": 1.10,
            "severity_sensitivity": 1.10,
            "litigation_sensitivity": 1.10,
            "best_for": "Smaller business GL/WC risks. Less ideal for heavier transportation severity.",
        },
    ]

    account_lines = []
    if has_auto:
        account_lines.append("auto")
    if has_gl:
        account_lines.append("gl")
    if has_wc:
        account_lines.append("wc")
    if has_cargo:
        account_lines.append("cargo")

    matches = []

    for carrier in carrier_directory:
        carrier_lines = set(carrier["lines"])
        matching_lines = [line for line in account_lines if line in carrier_lines]

        if not matching_lines:
            # Keep a low score if there is no line fit; do not recommend as top match.
            line_fit_score = -18
        else:
            line_fit_score = len(matching_lines) * 8

        missing_line_penalty = max(0, len(account_lines) - len(matching_lines)) * 5

        adjusted_pressure = (
            open_claim_pressure * carrier["open_claim_sensitivity"]
            + severity_pressure * carrier["severity_sensitivity"]
            + litigation_pressure * carrier["litigation_sensitivity"]
            + reserve_pressure
            + frequency_pressure
        )

        score = round(
            carrier["base_score"]
            + line_fit_score
            - missing_line_penalty
            - min(45, adjusted_pressure)
        )

        score = int(max(20, min(95, score)))

        if score >= 75:
            fit = "Strong rules-based fit"
        elif score >= 60:
            fit = "Moderate rules-based fit"
        elif score >= 45:
            fit = "Conditional fit"
        else:
            fit = "Poor fit"

        reasons = []

        if matching_lines:
            reasons.append(
                "Line fit: "
                + ", ".join(
                    {
                        "auto": "Auto Liability",
                        "gl": "General Liability",
                        "wc": "Workers Comp",
                        "cargo": "Motor Truck Cargo",
                    }.get(line, line)
                    for line in matching_lines
                )
            )
        else:
            reasons.append("Limited line-of-business fit for this account.")

        if open_claims > 0:
            reasons.append(f"{open_claims} open claim(s) reduce appetite.")
        if large_loss_count > 0:
            reasons.append(f"{large_loss_count} large loss claim(s) require underwriting narrative.")
        if litigation_claims > 0:
            reasons.append(f"{litigation_claims} litigation/attorney indicator(s) require review.")
        if total_reserve > 0:
            reasons.append(f"Outstanding reserve exposure: ${total_reserve:,.0f}.")
        if total_incurred > 0:
            reasons.append(f"Total incurred reviewed: ${total_incurred:,.2f}.")

        matches.append(
            {
                "carrier": carrier["carrier"],
                "carrier_group": carrier["group"],
                "market_category": carrier["market_category"],
                "match_score": score,
                "fit": fit,
                "line_fit": matching_lines,
                "reason": " ".join(reasons),
                "best_for": carrier["best_for"],
                "verification_note": "Rules-based LossQ match only. Final appetite, eligibility, appointment access, and quote availability must be verified with the carrier or broker market.",
            }
        )

    matches = sorted(matches, key=lambda item: item["match_score"], reverse=True)

    recommended = matches[0] if matches else None

    if not recommended:
        return {
            **insufficient_response(policy_number, "carrier-match"),
            "carrier_database_enabled": True,
            "real_carrier_database_enabled": True,
            "result_type": "no_match",
            "top_carriers": [],
            "recommended_carrier": "No carrier match available",
            "recommended_score": None,
            "carrier_match_summary": "No carrier match could be generated from the available claims.",
        }

    return {
        "policy_number": policy_number,
        "is_credible": True,
        "carrier_database_enabled": True,
        "real_carrier_database_enabled": True,
        "result_type": "rules_based_named_carrier_match",
        "top_carriers": matches[:5],
        "recommended_carrier": recommended["carrier"],
        "recommended_score": recommended["match_score"],
        "carrier_match_summary": (
            f"LossQ recommends {recommended['carrier']} with a {recommended['match_score']}/100 "
            f"rules-based match. The match used {total_claims} validated claim(s), "
            f"${total_incurred:,.2f} total incurred, {open_claims} open claim(s), "
            f"{large_loss_count} large loss claim(s), and {litigation_claims} litigation/attorney indicator(s). "
            "This is not a guaranteed quote or carrier acceptance; final appetite must be verified."
        ),
        "carrier_match_metrics": {
            **metrics,
            "coverage_lines_detected": sorted(account_lines),
            "large_loss_count": large_loss_count,
            "overall_pressure": overall_pressure,
        },
    }


def build_premium_forecast_engine(claims, policy_number=None):
    if len(claims) == 0:
        return {**insufficient_response(policy_number, "premium-forecast"), "current_premium": None, "expected_renewal_premium": None, "expected_increase_percent": None, "best_case_percent": None, "likely_range_percent": "Insufficient Data", "worst_case_percent": None, "confidence_score": 0, "forecast_drivers": ["No validated claims were available."], "forecast_summary": "Premium forecast not generated. LossQ needs parsed claims and preferably current premium/exposure data."}
    intelligence = build_underwriting_intelligence(claims)
    decision = build_underwriter_decision_engine(claims, policy_number)
    metrics = get_loss_metrics(claims)
    total_incurred = metrics["total_incurred"]
    modeled_current = max(25000, int((total_incurred * 0.65) + 50000))
    loss_ratio = total_incurred / modeled_current if modeled_current else 0
    increase = 3
    if loss_ratio >= 2.0: increase += 45
    elif loss_ratio >= 1.25: increase += 32
    elif loss_ratio >= 0.75: increase += 20
    elif loss_ratio >= 0.50: increase += 12
    elif loss_ratio <= 0.20: increase -= 2
    if metrics["total_claims"] >= 10: increase += 12
    elif metrics["total_claims"] >= 5: increase += 7
    if metrics["largest_loss"] >= 250000: increase += 15
    elif metrics["largest_loss"] >= 100000: increase += 8
    if metrics["open_claims"]: increase += min(metrics["open_claims"]*4, 16)
    if metrics["litigation_claims"]: increase += min(metrics["litigation_claims"]*10, 25)
    if metrics["total_reserve"] >= 250000: increase += 12
    elif metrics["total_reserve"] >= 100000: increase += 8
    if metrics["trend"] == "Deteriorating": increase += 10
    renewal_score = int(intelligence.get("renewal_score") or 0)
    if renewal_score < 50: increase += 15
    elif renewal_score < 70: increase += 8
    if int(decision.get("marketability_score") or 0) < 50: increase += 10
    increase = int(max(-5, min(125, increase)))
    expected = int(modeled_current * (1 + increase/100))
    confidence = 55 + (10 if metrics["total_claims"] >= 3 else 0) + (10 if metrics["yearly_incurred"] else 0) + (5 if metrics["total_reserve"] else 0)
    confidence = max(35, min(85, confidence))
    drivers = [f"Modeled loss ratio: {loss_ratio*100:.1f}%", f"{metrics['total_claims']} account-specific claim(s)", f"Open claims: {metrics['open_claims']}", f"Litigated claims: {metrics['litigation_claims']}", f"Reserve exposure: ${metrics['total_reserve']:,.0f}", f"Largest loss: ${metrics['largest_loss']:,.0f}"]
    return {"policy_number": policy_number, "is_credible": True, "current_premium": modeled_current, "expected_renewal_premium": expected, "expected_increase_percent": increase, "best_case_percent": max(-5, increase-10), "likely_range_percent": f"{max(-5, increase-10)}% to {min(150, increase+25)}%", "worst_case_percent": min(150, increase+25), "confidence_score": confidence, "forecast_drivers": drivers, "forecast_metrics": metrics, "forecast_summary": f"LossQ projects ${expected:,.0f}, an estimated {increase}% change from modeled current premium of ${modeled_current:,.0f}. This is a modeled forecast, not a carrier quote, based on loss ratio, claim frequency, open claim load, litigation, reserves, and renewal score."}


def _safe_policy_json(value):
    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, dict):
        return [value]

    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
    except Exception:
        return []

    return []


def _policy_family_prefix(policy_number):
    text = str(policy_number or "").strip().upper()

    # Example: GP-AL-240177-01 -> GP
    match = re.match(r"^([A-Z0-9]+)-(?:AL|GL|WC|CG)-", text)
    if match:
        return match.group(1)

    # Fallback: use first token before dash.
    if "-" in text:
        return text.split("-", 1)[0]

    return ""


def _claim_policy_number(claim):
    return str(
        getattr(claim, "policy_number", None)
        or getattr(claim, "policy_no", None)
        or getattr(claim, "policy", None)
        or ""
    ).strip().upper()


def _resolve_related_claims_for_renewal(db, current_user, policy_number):
    """
    Recovery resolver for renewal engines.

    The normal summary.get_claims_for_account() can return zero when the selected
    account policy is only one child policy, such as GP-AL-240177-01, while saved
    claims exist under sibling policies GP-GL, GP-WC, and GP-CG.

    This resolver only uses real saved database claims. It does not create demo
    claims or synthetic scoring data.
    """

    organization_id = current_user.get("organization_id") if isinstance(current_user, dict) else None
    selected_policy = str(policy_number or "").strip().upper()

    if not organization_id or not selected_policy:
        return [], [], {}

    related_policy_numbers = set()

    # 1. Find saved account profiles whose primary policy/account/policy schedule
    # references the selected policy. Then include the whole policy schedule.
    try:
        profiles = (
            db.query(AccountProfile)
            .filter(AccountProfile.organization_id == organization_id)
            .all()
        )

        for profile in profiles:
            profile_policy_values = {
                str(getattr(profile, "policy_number", "") or "").strip().upper(),
                str(getattr(profile, "account_number", "") or "").strip().upper(),
                str(getattr(profile, "customer_number", "") or "").strip().upper(),
            }

            policies = _safe_policy_json(getattr(profile, "policies", None))
            schedule_policy_values = set()

            for item in policies:
                if not isinstance(item, dict):
                    continue

                pnum = str(
                    item.get("policy_number")
                    or item.get("policyNumber")
                    or item.get("policy")
                    or ""
                ).strip().upper()

                if pnum:
                    schedule_policy_values.add(pnum)

            all_profile_values = profile_policy_values | schedule_policy_values

            if selected_policy in all_profile_values:
                related_policy_numbers.update(value for value in all_profile_values if value)

                # LOSSQ_PROFILE_EXPOSURE_FIELDS_FOR_RENEWAL_ENGINES_V1
                profile_data = {
                    "id": getattr(profile, "id", None),
                    "business_name": getattr(profile, "business_name", None),
                    "insured": getattr(profile, "business_name", None),
                    "carrier_name": getattr(profile, "carrier_name", None),
                    "writing_carrier": getattr(profile, "writing_carrier", None),
                    "agency_name": getattr(profile, "agency_name", None),
                    "policy_number": getattr(profile, "policy_number", None),
                    "account_number": getattr(profile, "account_number", None),
                    "customer_number": getattr(profile, "customer_number", None),
                    "effective_date": getattr(profile, "effective_date", None),
                    "expiration_date": getattr(profile, "expiration_date", None),
                    "evaluation_date": getattr(profile, "evaluation_date", None),
                    "state": getattr(profile, "state", None),

                    # Saved Exposure Inputs
                    "current_premium": getattr(profile, "current_premium", None),
                    "expiring_premium": getattr(profile, "expiring_premium", None),
                    "target_renewal_premium": getattr(profile, "target_renewal_premium", None),
                    "line_of_business": getattr(profile, "line_of_business", None),
                    "exposure_basis": getattr(profile, "exposure_basis", None),
                    "class_code": getattr(profile, "class_code", None),
                    "class_codes": getattr(profile, "class_codes", None),
                    "limits": getattr(profile, "limits", None),
                    "coverage_limit": getattr(profile, "coverage_limit", None),
                    "deductible": getattr(profile, "deductible", None),
                    "retention": getattr(profile, "retention", None),
                    "payroll": getattr(profile, "payroll", None),
                    "revenue": getattr(profile, "revenue", None),
                    "sales": getattr(profile, "sales", None),
                    "receipts": getattr(profile, "receipts", None),
                    "employee_count": getattr(profile, "employee_count", None),
                    "vehicle_count": getattr(profile, "vehicle_count", None),
                    "driver_count": getattr(profile, "driver_count", None),
                    "experience_mod": getattr(profile, "experience_mod", None),
                    "mod": getattr(profile, "mod", None),
                    "property_tiv": getattr(profile, "property_tiv", None),
                    "tiv": getattr(profile, "tiv", None),
                    "building_value": getattr(profile, "building_value", None),
                    "contents_value": getattr(profile, "contents_value", None),
                    "square_footage": getattr(profile, "square_footage", None),
                    "location_count": getattr(profile, "location_count", None),
                    "unit_count": getattr(profile, "unit_count", None),
                    "umbrella_limit": getattr(profile, "umbrella_limit", None),
                    "cargo_limit": getattr(profile, "cargo_limit", None),
                    "underwriter_notes": getattr(profile, "underwriter_notes", None),

                    "policies": policies,
                }

                break
        else:
            profile_data = {}
    except Exception:
        profile_data = {}

    # 2. If no profile schedule was found, use policy family pattern.
    # Example: GP-AL-240177-01 should include GP-GL, GP-WC, GP-CG sibling policies
    # saved in the same organization.
    if not related_policy_numbers:
        family_prefix = _policy_family_prefix(selected_policy)

        if family_prefix:
            try:
                family_claims = (
                    db.query(Claim)
                    .filter(Claim.organization_id == organization_id)
                    .filter(Claim.policy_number.ilike(f"{family_prefix}-%"))
                    .all()
                )

                for claim in family_claims:
                    pnum = _claim_policy_number(claim)
                    if pnum:
                        related_policy_numbers.add(pnum)
            except Exception:
                pass

    related_policy_numbers.add(selected_policy)

    # 3. Pull real saved claims for the related policy set.
    try:
        claims = (
            db.query(Claim)
            .filter(Claim.organization_id == organization_id)
            .filter(Claim.policy_number.in_(list(related_policy_numbers)))
            .all()
        )
    except Exception:
        claims = []

    # 4. If strict related set still finds nothing, do one final family-prefix
    # database lookup. This is still real saved claims only.
    if not claims:
        family_prefix = _policy_family_prefix(selected_policy)

        if family_prefix:
            try:
                claims = (
                    db.query(Claim)
                    .filter(Claim.organization_id == organization_id)
                    .filter(Claim.policy_number.ilike(f"{family_prefix}-%"))
                    .all()
                )

                related_policy_numbers.update(
                    _claim_policy_number(claim) for claim in claims if _claim_policy_number(claim)
                )
            except Exception:
                claims = []

    return claims, sorted(value for value in related_policy_numbers if value), profile_data



def engine_response(builder, db, current_user, policy_number):
    claims, policy_numbers_used, profile_data = get_claims_for_account(db, current_user, policy_number)

    if not claims and policy_number:
        recovered_claims, recovered_policy_numbers, recovered_profile = _resolve_related_claims_for_renewal(
            db,
            current_user,
            policy_number,
        )

        if recovered_claims:
            claims = recovered_claims
            policy_numbers_used = recovered_policy_numbers
            profile_data = recovered_profile or profile_data or {}

    quality = data_quality(claims, policy_numbers_used, profile_data)
    result = builder(claims, policy_number)

    return {
        **result,
        "data_quality": quality,
        "is_credible": quality["is_credible"],
        "claims_used": len(claims),
        "policy_numbers_used": policy_numbers_used,
        "account_profile": profile_data,
    }





# LOSSQ_PROFILE_DATA_NORMALIZER_FOR_EXPOSURE_V1
def lossq_profile_get(profile_data, key, default=None):
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


def lossq_normalize_profile_data(profile_data):
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
        "state",
        "policies",
    ]

    for key in keys:
        if not normalized.get(key):
            value = lossq_profile_get(profile_data, key)
            if value not in (None, ""):
                normalized[key] = value

    return normalized


# LOSSQ_EXPOSURE_AWARE_RENEWAL_INTELLIGENCE_V1
def lossq_clean_text(value):
    return str(value or "").strip()

def lossq_money_value(value):
    try:
        cleaned = str(value or "").replace("$", "").replace(",", "").replace("%", "").strip()
        if cleaned in {"", "-", "None", "none", "null"}:
            return 0.0
        return float(cleaned)
    except Exception:
        return 0.0

def lossq_int_value(value):
    try:
        cleaned = str(value or "").replace(",", "").strip()
        if cleaned in {"", "-", "None", "none", "null"}:
            return 0
        return int(float(cleaned))
    except Exception:
        return 0

def lossq_exposure_context(profile_data):
    profile_data = lossq_normalize_profile_data(profile_data)

    line_text = " ".join([
        lossq_clean_text(profile_data.get("line_of_business")),
        lossq_clean_text(profile_data.get("class_code")),
        lossq_clean_text(profile_data.get("class_codes")),
        lossq_clean_text(profile_data.get("exposure_basis")),
        lossq_clean_text(profile_data.get("underwriter_notes")),
        lossq_clean_text(profile_data.get("business_name")),
    ]).lower()

    policies = profile_data.get("policies") or []
    if isinstance(policies, list):
        for item in policies:
            if isinstance(item, dict):
                line_text += " " + " ".join([
                    lossq_clean_text(item.get("line_of_business")),
                    lossq_clean_text(item.get("policy_type")),
                    lossq_clean_text(item.get("coverage")),
                ]).lower()

    current_premium = lossq_money_value(profile_data.get("current_premium") or profile_data.get("expiring_premium"))
    target_premium = lossq_money_value(profile_data.get("target_renewal_premium"))
    payroll = lossq_money_value(profile_data.get("payroll"))
    revenue = lossq_money_value(profile_data.get("revenue") or profile_data.get("sales") or profile_data.get("receipts"))
    property_tiv = lossq_money_value(profile_data.get("property_tiv") or profile_data.get("tiv"))
    coverage_limit = lossq_money_value(profile_data.get("coverage_limit") or profile_data.get("limits"))
    deductible = lossq_money_value(profile_data.get("deductible"))
    retention = lossq_money_value(profile_data.get("retention"))
    cargo_limit = lossq_money_value(profile_data.get("cargo_limit"))
    umbrella_limit = lossq_money_value(profile_data.get("umbrella_limit"))
    experience_mod = lossq_money_value(profile_data.get("experience_mod") or profile_data.get("mod"))

    vehicle_count = lossq_int_value(profile_data.get("vehicle_count"))
    driver_count = lossq_int_value(profile_data.get("driver_count"))
    employee_count = lossq_int_value(profile_data.get("employee_count"))
    location_count = lossq_int_value(profile_data.get("location_count"))
    unit_count = lossq_int_value(profile_data.get("unit_count"))

    is_transportation = any(word in line_text for word in ["auto", "truck", "transport", "fleet", "vehicle", "driver", "cargo"])
    is_workers_comp = any(word in line_text for word in ["workers", "worker", "comp", "payroll", "wc"])
    is_property = any(word in line_text for word in ["property", "building", "tiv", "location", "contents"])
    is_general_liability = any(word in line_text for word in ["general liability", "premises", "operations", "contractor", "maintenance", "janitor", "service"])
    is_professional = any(word in line_text for word in ["professional", "errors", "omissions", "e&o"])
    is_cyber = "cyber" in line_text

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
    if property_tiv:
        exposure_drivers.append(f"Property TIV considered: ${property_tiv:,.0f}.")
    if coverage_limit:
        exposure_drivers.append(f"Coverage limit considered: ${coverage_limit:,.0f}.")
    if deductible:
        exposure_drivers.append(f"Deductible considered: ${deductible:,.0f}.")
    if retention:
        exposure_drivers.append(f"Retention or SIR considered: ${retention:,.0f}.")
    if experience_mod:
        exposure_drivers.append(f"Experience mod considered: {experience_mod:.2f}.")

    primary_line = (
        lossq_clean_text(profile_data.get("line_of_business"))
        or lossq_clean_text(profile_data.get("exposure_basis"))
        or "Not specified"
    )

    return {
        "has_exposure_inputs": bool(exposure_drivers or primary_line != "Not specified"),
        "primary_line_of_business": primary_line,
        "line_text": line_text,
        "current_premium": current_premium,
        "target_renewal_premium": target_premium,
        "payroll": payroll,
        "revenue": revenue,
        "property_tiv": property_tiv,
        "coverage_limit": coverage_limit,
        "deductible": deductible,
        "retention": retention,
        "cargo_limit": cargo_limit,
        "umbrella_limit": umbrella_limit,
        "experience_mod": experience_mod,
        "vehicle_count": vehicle_count,
        "driver_count": driver_count,
        "employee_count": employee_count,
        "location_count": location_count,
        "unit_count": unit_count,
        "is_transportation": is_transportation,
        "is_workers_comp": is_workers_comp,
        "is_property": is_property,
        "is_general_liability": is_general_liability,
        "is_professional": is_professional,
        "is_cyber": is_cyber,
        "exposure_drivers": exposure_drivers,
    }

def lossq_exposure_markets(ctx):
    markets = []

    if ctx.get("is_transportation"):
        markets.extend([
            "Transportation and commercial auto markets",
            "Fleet auto liability markets",
            "Motor truck cargo markets",
        ])

    if ctx.get("is_workers_comp"):
        markets.extend([
            "Workers compensation markets",
            "Payroll-driven casualty markets",
        ])

    if ctx.get("is_property"):
        markets.extend([
            "Property and TIV-driven markets",
            "Package markets with property capacity",
        ])

    if ctx.get("is_general_liability"):
        markets.extend([
            "General liability markets",
            "Middle-market casualty carriers",
        ])

    if ctx.get("is_professional"):
        markets.append("Professional liability markets")

    if ctx.get("is_cyber"):
        markets.append("Cyber liability markets")

    if not markets:
        markets = [
            "Regional commercial markets",
            "Middle-market carriers",
            "Specialty markets if standard appetite is limited",
        ]

    seen = []
    for item in markets:
        if item not in seen:
            seen.append(item)
    return seen

def lossq_exposure_carrier_targets(ctx):
    carriers = []

    if ctx.get("is_transportation"):
        carriers.extend([
            "Berkley Transportation",
            "Great West Casualty",
            "Progressive Commercial",
            "National General",
        ])

    if ctx.get("is_workers_comp"):
        carriers.extend([
            "Travelers",
            "The Hartford",
            "AmTrust",
            "EMPLOYERS",
        ])

    if ctx.get("is_property"):
        carriers.extend([
            "Travelers",
            "The Hartford",
            "Zurich",
            "CNA",
        ])

    if ctx.get("is_general_liability"):
        carriers.extend([
            "Travelers",
            "The Hartford",
            "CNA",
            "Liberty Mutual",
        ])

    if ctx.get("is_professional"):
        carriers.extend(["CNA", "Travelers", "The Hartford"])

    if ctx.get("is_cyber"):
        carriers.extend(["Travelers", "The Hartford", "CNA"])

    seen = []
    for carrier in carriers:
        if carrier not in seen:
            seen.append(carrier)

    return seen

def lossq_apply_exposure_to_decision(result, profile_data, claims):
    result = dict(result or {})
    profile_data = lossq_normalize_profile_data(profile_data)
    ctx = lossq_exposure_context(profile_data)

    if not ctx.get("has_exposure_inputs"):
        result["exposure_inputs_used"] = False
        return result

    concerns = list(result.get("underwriting_concerns") or [])
    markets = list(result.get("best_market_types") or [])
    drivers = list(result.get("exposure_drivers") or [])

    drivers.extend(ctx["exposure_drivers"])

    score = result.get("marketability_score")
    try:
        score = int(score) if score is not None else None
    except Exception:
        score = None

    probability = result.get("renewal_probability")
    try:
        probability = int(probability) if probability is not None else None
    except Exception:
        probability = None

    total_incurred = sum(lossq_money_value(getattr(c, "total_incurred", 0) or getattr(c, "incurred", 0)) for c in claims or [])
    current_premium = ctx.get("current_premium") or 0

    if current_premium > 0 and total_incurred > 0:
        loss_ratio = total_incurred / current_premium
        result.setdefault("decision_metrics", {})
        result["decision_metrics"]["exposure_loss_ratio"] = round(loss_ratio, 4)

        if loss_ratio >= 0.75:
            concerns.append(f"Loss ratio is elevated at approximately {loss_ratio * 100:.1f}% based on saved current premium.")
            if score is not None:
                score -= 10
            if probability is not None:
                probability -= 8
        elif loss_ratio <= 0.35:
            drivers.append(f"Loss ratio is favorable at approximately {loss_ratio * 100:.1f}% based on saved current premium.")
            if score is not None:
                score += 5
            if probability is not None:
                probability += 5

    if ctx.get("experience_mod") >= 1.25:
        concerns.append(f"Experience mod of {ctx['experience_mod']:.2f} may create workers compensation underwriting pressure.")
        if score is not None:
            score -= 8
    elif 0 < ctx.get("experience_mod") <= 0.90:
        drivers.append(f"Experience mod of {ctx['experience_mod']:.2f} supports a stronger workers compensation position.")
        if score is not None:
            score += 4

    if ctx.get("vehicle_count") >= 25 or ctx.get("driver_count") >= 25:
        concerns.append("Fleet size creates elevated auto underwriting review requirements.")
        if score is not None:
            score -= 5

    if ctx.get("property_tiv") >= 10000000:
        concerns.append("Large property TIV requires carrier capacity and catastrophe/property underwriting review.")

    if ctx.get("retention") >= 25000 or ctx.get("deductible") >= 25000:
        drivers.append("Meaningful deductible or retention improves risk sharing and may support carrier appetite.")
        if score is not None:
            score += 3

    for market in lossq_exposure_markets(ctx):
        if market not in markets:
            markets.append(market)

    if score is not None:
        score = max(0, min(100, score))
        result["marketability_score"] = score

    if probability is not None:
        probability = max(0, min(100, probability))
        result["renewal_probability"] = probability

    result["best_market_types"] = markets
    result["underwriting_concerns"] = concerns or ["No major underwriting concerns detected."]
    result["exposure_inputs_used"] = True
    result["exposure_profile"] = {
        "primary_line_of_business": ctx["primary_line_of_business"],
        "current_premium": ctx["current_premium"],
        "target_renewal_premium": ctx["target_renewal_premium"],
        "payroll": ctx["payroll"],
        "revenue": ctx["revenue"],
        "vehicle_count": ctx["vehicle_count"],
        "driver_count": ctx["driver_count"],
        "employee_count": ctx["employee_count"],
        "property_tiv": ctx["property_tiv"],
        "coverage_limit": ctx["coverage_limit"],
        "deductible": ctx["deductible"],
        "retention": ctx["retention"],
        "experience_mod": ctx["experience_mod"],
    }
    result["exposure_drivers"] = drivers
    result["underwriter_decision_summary"] = (
        str(result.get("underwriter_decision_summary") or "").rstrip()
        + f" Saved Exposure Inputs were also considered for {ctx['primary_line_of_business']}."
    ).strip()

    return result

def lossq_apply_exposure_to_appetite(result, profile_data, claims):
    result = dict(result or {})
    profile_data = lossq_normalize_profile_data(profile_data)
    ctx = lossq_exposure_context(profile_data)

    if not ctx.get("has_exposure_inputs"):
        result["exposure_inputs_used"] = False
        return result

    score = result.get("carrier_appetite_score")
    try:
        score = int(score) if score is not None else 0
    except Exception:
        score = 0

    if ctx.get("retention") >= 25000 or ctx.get("deductible") >= 25000:
        score += 4
    if ctx.get("experience_mod") >= 1.25:
        score -= 6
    if ctx.get("vehicle_count") >= 25 or ctx.get("driver_count") >= 25:
        score -= 4
    if ctx.get("current_premium") >= 50000:
        score += 2

    score = max(0, min(100, score))
    level = "Strong" if score >= 75 else "Moderate" if score >= 50 else "Limited"

    reasons = list(result.get("carrier_match_reasons") or [])
    reasons.extend(ctx["exposure_drivers"])

    markets = lossq_exposure_markets(ctx)

    if score < 25:
        level = "Distressed"
    elif score < 50:
        level = "Restricted"
    elif score < 75:
        level = "Limited"
    else:
        level = "Strong"

    best_fit_markets = []
    for market in markets:
        best_fit_markets.append({
            "carrier": market,
            "name": market,
            "market": market,
            "score": score,
            "match_score": score,
            "fit": level,
            "reason": (
                f"{market}: Appetite reviewed using saved Exposure Inputs for "
                f"{ctx['primary_line_of_business']}. Current premium ${ctx.get('current_premium', 0):,.0f}, "
                f"revenue ${ctx.get('revenue', 0):,.0f}, property TIV ${ctx.get('property_tiv', 0):,.0f}, "
                f"{ctx.get('employee_count', 0)} employees, {ctx.get('vehicle_count', 0)} vehicles, "
                f"and {ctx.get('driver_count', 0)} drivers were considered."
            )
        })

    result["carrier_appetite_score"] = score
    result["carrier_appetite_level"] = level
    result["best_market"] = markets[0] if markets else "Selective commercial markets"
    result["carrier_match_reasons"] = reasons
    result["best_fit_carriers"] = best_fit_markets
    result["best_fit_markets"] = best_fit_markets
    result["exposure_inputs_used"] = True
    result["exposure_profile"] = ctx
    result["lossq_appetite_reason_version"] = "LOSSQ_APPETITE_BEST_FIT_MARKET_OBJECTS_V1"
    result["market_strategy"] = (
        f"Market this as a {ctx['primary_line_of_business']} account using both account-specific claims and saved Exposure Inputs. "
        f"Best target markets: {', '.join(markets[:3]) if markets else 'Selective commercial markets'}."
    )
    result["placement_summary"] = (
        f"Carrier appetite is {score}/100, rated {level}, after considering claims plus saved Exposure Inputs for "
        f"{ctx['primary_line_of_business']}."
    )

    return result


# LOSSQ_EXPOSURE_ALIGNED_CARRIER_MATCH_RERANK_V1
def lossq_apply_exposure_to_carrier_match(result, profile_data, claims):
    result = dict(result or {})
    profile_data = lossq_normalize_profile_data(profile_data)
    ctx = lossq_exposure_context(profile_data)

    if not ctx.get("has_exposure_inputs"):
        result["exposure_inputs_used"] = False
        return result

    primary_line = str(ctx.get("primary_line_of_business") or "").strip()
    primary_lower = primary_line.lower()

    primary_is_transportation = any(
        word in primary_lower
        for word in ["auto", "transport", "truck", "fleet", "vehicle", "driver", "cargo"]
    )

    primary_is_bop_property_gl = any(
        word in primary_lower
        for word in ["businessowners", "bop", "property", "general liability", "liability", "package"]
    )

    target_carriers = lossq_exposure_carrier_targets(ctx)

    # For BOP/package/property/GL accounts, keep the target market focused on broad commercial carriers.
    if primary_is_bop_property_gl and not primary_is_transportation:
        target_carriers = ["Travelers", "The Hartford", "CNA", "Liberty Mutual"]

    if not target_carriers:
        target_carriers = ["Travelers", "The Hartford", "CNA", "Liberty Mutual"]

    metrics = result.get("carrier_match_metrics") or result.get("appetite_metrics") or {}
    total_claims = lossq_int_value(metrics.get("total_claims"))
    open_claims = lossq_int_value(metrics.get("open_claims"))
    total_incurred = lossq_money_value(metrics.get("total_incurred"))
    total_reserve = lossq_money_value(metrics.get("total_reserve"))
    large_claims = lossq_int_value(metrics.get("large_claims"))

    current_premium = ctx.get("current_premium") or 0
    loss_ratio = (total_incurred / current_premium) if current_premium and total_incurred else 0

    top_carriers = list(result.get("top_carriers") or [])
    adjusted = []

    for item in top_carriers:
        row = dict(item or {})
        carrier_name = str(row.get("carrier") or row.get("name") or "").strip()
        carrier_lower = carrier_name.lower()
        score = lossq_int_value(row.get("match_score") or row.get("score"))

        reasons = list(row.get("reasons") or [])
        target_match = any(
            target.lower() in carrier_lower or carrier_lower in target.lower()
            for target in target_carriers
        )

        if target_match:
            score += 18
            reasons.append(
                f"Exposure-aligned for {primary_line}: broad commercial/BOP, property, and casualty appetite."
            )
            reasons.append(
                f"Saved exposure inputs considered: ${ctx.get('current_premium', 0):,.0f} current premium, "
                f"${ctx.get('revenue', 0):,.0f} revenue, ${ctx.get('property_tiv', 0):,.0f} property TIV, "
                f"{ctx.get('employee_count', 0)} employees."
            )

            if loss_ratio >= 0.75 or open_claims > 0:
                score = min(score, 72)
                reasons.append(
                    f"Conditional due to loss pressure: {total_claims} claim(s), {open_claims} open, "
                    f"${total_incurred:,.0f} incurred, ${total_reserve:,.0f} reserves."
                )

        else:
            score -= 8
            reasons.append(
                f"Not a primary exposure target for {primary_line}; treated as secondary/backup market."
            )

            if "transport" in carrier_lower and not primary_is_transportation:
                score -= 20
                reasons.append(
                    "Demoted because the account's primary exposure is Businessowners/Property/GL, not transportation."
                )

        score = max(0, min(100, score))

        if score >= 70:
            fit = "Conditional exposure-aligned fit"
        elif score >= 50:
            fit = "Conditional backup fit"
        else:
            fit = "Poor fit / backup only"

        exposure_reason = (
            f"{carrier_name}: Exposure-aligned review for {primary_line}. "
            f"This is a Businessowners/Property/GL account, supported by saved Exposure Inputs: "
            f"${ctx.get('current_premium', 0):,.0f} current premium, "
            f"${ctx.get('revenue', 0):,.0f} revenue, "
            f"${ctx.get('property_tiv', 0):,.0f} property TIV, "
            f"{ctx.get('employee_count', 0)} employees, "
            f"{ctx.get('vehicle_count', 0)} vehicles, and "
            f"{ctx.get('driver_count', 0)} drivers. "
            f"Underwriting is conditional due to {total_claims} claim(s), "
            f"{open_claims} open claim(s), ${total_incurred:,.0f} incurred, "
            f"and ${total_reserve:,.0f} reserves."
        )

        if "transport" in carrier_lower and not primary_is_transportation:
            exposure_reason = (
                f"{carrier_name}: Backup only. This carrier was demoted because the account's primary exposure "
                f"is {primary_line}/property and general liability, not transportation. "
                f"The account still has {total_claims} claim(s), {open_claims} open claim(s), "
                f"${total_incurred:,.0f} incurred, and ${total_reserve:,.0f} reserves."
            )

        row["carrier"] = carrier_name
        row["match_score"] = score
        row["score"] = score
        row["fit"] = fit
        row["reason"] = exposure_reason
        row["match_reason"] = exposure_reason
        row["reasons"] = [exposure_reason]
        adjusted.append(row)

    # Add missing target carriers if the carrier database did not return them.
    existing_names = " | ".join(str(row.get("carrier") or "").lower() for row in adjusted)

    for target in target_carriers:
        if target.lower() not in existing_names:
            score = 66
            if loss_ratio >= 0.75 or open_claims > 0:
                score = 62

            adjusted.append({
                "carrier": target,
                "match_score": score,
                "score": score,
                "fit": "Conditional exposure-aligned fit",
                "reasons": [
                    f"Added as an exposure-aligned market for {primary_line}.",
                    f"Saved exposure inputs considered: ${ctx.get('current_premium', 0):,.0f} current premium, "
                    f"${ctx.get('revenue', 0):,.0f} revenue, ${ctx.get('property_tiv', 0):,.0f} property TIV.",
                    f"Requires underwriting review due to {open_claims} open claim(s) and ${total_incurred:,.0f} incurred."
                ],
            })

    adjusted = sorted(adjusted, key=lambda item: int(item.get("match_score") or item.get("score") or 0), reverse=True)

    recommended = adjusted[0] if adjusted else {}

    result["top_carriers"] = adjusted
    result["carrier_match_reasons"] = [
        str(row.get("reason") or row.get("match_reason") or "")
        for row in adjusted
        if str(row.get("reason") or row.get("match_reason") or "").strip()
    ]
    result["recommended_carrier"] = recommended.get("carrier") or result.get("recommended_carrier")
    result["recommended_score"] = recommended.get("match_score") or recommended.get("score") or result.get("recommended_score")
    result["recommended_market_category"] = (
        "Businessowners / Property / General Liability"
        if primary_is_bop_property_gl and not primary_is_transportation
        else result.get("recommended_market_category", "Commercial Insurance")
    )

    result["exposure_target_carriers"] = target_carriers
    result["exposure_inputs_used"] = True
    result["exposure_profile"] = ctx
    result["lossq_carrier_match_reason_version"] = "LOSSQ_EXPOSURE_ALIGNED_CARRIER_MATCH_RERANK_V1"

    result["carrier_match_summary"] = (
        f"LossQ recommends {result['recommended_carrier']} with a {result['recommended_score']}/100 "
        f"exposure-aligned match for {primary_line}. The ranking used saved Exposure Inputs "
        f"(${ctx.get('current_premium', 0):,.0f} current premium, ${ctx.get('revenue', 0):,.0f} revenue, "
        f"${ctx.get('property_tiv', 0):,.0f} property TIV, {ctx.get('employee_count', 0)} employees) "
        f"plus claim activity ({total_claims} claim(s), {open_claims} open, ${total_incurred:,.0f} incurred, "
        f"${total_reserve:,.0f} reserves). Transportation-specific markets are treated as secondary unless "
        f"auto/transportation is the primary account exposure."
    )

    return result


    target_carriers = lossq_exposure_carrier_targets(ctx)
    top_carriers = list(result.get("top_carriers") or [])

    adjusted = []
    for item in top_carriers:
        row = dict(item or {})
        carrier_name = str(row.get("carrier") or "")
        score = lossq_int_value(row.get("match_score"))

        boost = 0
        for target in target_carriers:
            if target.lower() in carrier_name.lower() or carrier_name.lower() in target.lower():
                boost = 12
                break

        if boost:
            score = min(100, score + boost)
            reasons = list(row.get("reasons") or [])
            reasons.append(f"Boosted because saved Exposure Inputs match {ctx['primary_line_of_business']} appetite.")
            row["reasons"] = reasons
            row["fit"] = row.get("fit") or "Exposure-aligned fit"

        row["match_score"] = score
        adjusted.append(row)

    adjusted = sorted(adjusted, key=lambda item: int(item.get("match_score") or 0), reverse=True)

    result["top_carriers"] = adjusted
    result["recommended_carrier"] = adjusted[0].get("carrier") if adjusted else (target_carriers[0] if target_carriers else result.get("recommended_carrier"))
    result["recommended_market_category"] = (
        "Transportation / Commercial Auto" if ctx.get("is_transportation")
        else "Workers Compensation" if ctx.get("is_workers_comp")
        else "Property / Package" if ctx.get("is_property")
        else "General Liability / Casualty" if ctx.get("is_general_liability")
        else result.get("recommended_market_category", "Commercial Insurance")
    )
    result["exposure_target_carriers"] = target_carriers
    result["exposure_inputs_used"] = True
    result["exposure_profile"] = ctx
    result["carrier_match_summary"] = (
        f"Carrier match used claim activity plus saved Exposure Inputs for {ctx['primary_line_of_business']}. "
        f"Recommended target markets: {', '.join(target_carriers[:4]) if target_carriers else 'regional commercial markets'}."
    )

    return result




# LOSSQ_DIRECT_FULL_ACCOUNT_PROFILE_EXPOSURE_LOOKUP_V1
def lossq_full_profile_for_exposure(db, current_user, policy_number, result=None, profile_data=None):
    organization_id = current_user.get("organization_id") if isinstance(current_user, dict) else None

    result_profile = {}
    try:
        result_profile = dict((result or {}).get("account_profile") or {})
    except Exception:
        result_profile = {}

    base_profile = profile_data if profile_data else result_profile

    if not organization_id:
        return lossq_normalize_profile_data(base_profile)

    profile_id = (
        lossq_profile_get(base_profile, "id")
        or result_profile.get("id")
    )

    try:
        if profile_id:
            profile = (
                db.query(AccountProfile)
                .filter(AccountProfile.organization_id == organization_id)
                .filter(AccountProfile.id == int(profile_id))
                .first()
            )
            if profile:
                return lossq_normalize_profile_data(profile)
    except Exception:
        pass

    selected_policy = str(policy_number or "").strip().upper()

    candidate_values = set()
    for source in [base_profile, result_profile]:
        for key in ["policy_number", "account_number", "customer_number"]:
            value = str(lossq_profile_get(source, key) or "").strip().upper()
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

            policies = _safe_policy_json(getattr(profile, "policies", None))
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
                return lossq_normalize_profile_data(profile)

    except Exception:
        pass

    return lossq_normalize_profile_data(base_profile)


# LOSSQ_FORCE_RESULT_ACCOUNT_PROFILE_EXPOSURE_SOURCE_V1
def lossq_profile_has_exposure_values(profile_data):
    if not profile_data:
        return False

    try:
        data = profile_data if isinstance(profile_data, dict) else lossq_normalize_profile_data(profile_data)
    except Exception:
        data = profile_data if isinstance(profile_data, dict) else {}

    exposure_keys = [
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

    for key in exposure_keys:
        value = data.get(key) if isinstance(data, dict) else None
        if value not in (None, "", "0", "$0", 0):
            return True

    return False


def lossq_best_exposure_profile(result, profile_data):
    result_profile = {}
    try:
        result_profile = dict((result or {}).get("account_profile") or {})
    except Exception:
        result_profile = {}

    if lossq_profile_has_exposure_values(profile_data):
        return profile_data

    if lossq_profile_has_exposure_values(result_profile):
        return result_profile

    return profile_data or result_profile or {}



# LOSSQ_ENDPOINT_FORCE_EXPOSURE_RETURN_V1
def lossq_force_exposure_from_result_profile(result):
    result = dict(result or {})
    profile = result.get("account_profile") or {}

    if not isinstance(profile, dict):
        try:
            profile = lossq_normalize_profile_data(profile)
        except Exception:
            profile = {}

    ctx = lossq_exposure_context(profile)

    if ctx.get("has_exposure_inputs"):
        result["exposure_inputs_used"] = True
        result["exposure_profile"] = {
            "primary_line_of_business": ctx.get("primary_line_of_business"),
            "current_premium": ctx.get("current_premium"),
            "target_renewal_premium": ctx.get("target_renewal_premium"),
            "payroll": ctx.get("payroll"),
            "revenue": ctx.get("revenue"),
            "vehicle_count": ctx.get("vehicle_count"),
            "driver_count": ctx.get("driver_count"),
            "employee_count": ctx.get("employee_count"),
            "property_tiv": ctx.get("property_tiv"),
            "coverage_limit": ctx.get("coverage_limit"),
            "deductible": ctx.get("deductible"),
            "retention": ctx.get("retention"),
            "experience_mod": ctx.get("experience_mod"),
        }
        result["exposure_drivers"] = ctx.get("exposure_drivers") or []
        result["lossq_exposure_patch_version"] = "LOSSQ_ENDPOINT_FORCE_EXPOSURE_RETURN_V1"
    else:
        result["lossq_exposure_patch_version"] = "LOSSQ_ENDPOINT_FORCE_EXPOSURE_RETURN_V1_NO_EXPOSURE_FOUND"

    return result


@router.get("/decision")
def renewal_decision(policy_number: str | None = Query(default=None), db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    result = engine_response(build_underwriter_decision_engine, db, current_user, policy_number)
    claims, policy_numbers_used, profile_data = get_claims_for_account(db, current_user, policy_number)
    profile_data = lossq_best_exposure_profile(result, profile_data)
    profile_data = lossq_full_profile_for_exposure(db, current_user, policy_number, result, profile_data)
    result["account_profile"] = profile_data
    result = lossq_apply_exposure_to_decision(result, profile_data, claims)
    result["policy_numbers_used"] = policy_numbers_used
    result = lossq_force_exposure_from_result_profile(result)
    return result



# LOSSQ_MARKETABLE_CARRIER_APPETITE_V1
def lossq_claim_text_for_appetite(claim):
    parts = [
        getattr(claim, "line_of_business", ""),
        getattr(claim, "coverage", ""),
        getattr(claim, "claim_type", ""),
        getattr(claim, "description", ""),
        getattr(claim, "cause_of_loss", ""),
        getattr(claim, "policy_number", ""),
    ]
    return " ".join(str(x or "") for x in parts).lower()


def lossq_detect_market_lines_for_appetite(claims, profile_data=None):
    profile_data = profile_data or {}
    text_parts = [
        profile_data.get("line_of_business"),
        profile_data.get("business_name"),
        profile_data.get("exposure_basis"),
        profile_data.get("class_code"),
        profile_data.get("class_codes"),
    ]

    policies = profile_data.get("policies") if isinstance(profile_data.get("policies"), list) else []
    for policy in policies:
        if isinstance(policy, dict):
            text_parts.extend([
                policy.get("line_of_business"),
                policy.get("policy_type"),
                policy.get("coverage"),
                policy.get("policy_number"),
            ])

    for claim in claims or []:
        text_parts.append(lossq_claim_text_for_appetite(claim))

    raw = " ".join(str(x or "") for x in text_parts).lower()
    lines = []

    if any(word in raw for word in ["auto", "vehicle", "fleet", "truck", "driver", "transport"]):
        lines.append("commercial_auto")

    if any(word in raw for word in ["general liability", "gl", "premises", "slip", "fall", "property damage", "liability"]):
        lines.append("general_liability")

    if any(word in raw for word in ["workers", "worker", "comp", "wc", "employee injury", "strain"]):
        lines.append("workers_comp")

    if any(word in raw for word in ["property", "building", "water", "fire", "theft", "wind", "equipment"]):
        lines.append("property")

    return list(dict.fromkeys(lines))


def lossq_marketable_carrier_appetite(result, profile_data, claims, policy_numbers_used=None, policy_number=None):
    result = dict(result or {})
    profile_data = profile_data or {}
    claims = claims or []
    policy_numbers_used = policy_numbers_used or []

    metrics = dict(result.get("appetite_metrics") or result.get("decision_metrics") or {})

    total_claims = int(metrics.get("total_claims") or len(claims) or 0)
    open_claims = int(metrics.get("open_claims") or len([c for c in claims if is_open(c)]) or 0)
    litigation_claims = int(metrics.get("litigation_claims") or len([c for c in claims if is_litigated(c)]) or 0)

    total_incurred = float(metrics.get("total_incurred") or sum(money(getattr(c, "total_incurred", 0)) for c in claims) or 0)
    total_reserve = float(metrics.get("total_reserve") or sum(money(getattr(c, "reserve_amount", 0)) for c in claims) or 0)
    largest_loss = float(metrics.get("largest_loss") or max([money(getattr(c, "total_incurred", 0)) for c in claims] or [0]) or 0)
    large_claims = int(metrics.get("large_claims") or len([c for c in claims if money(getattr(c, "total_incurred", 0)) >= 50000]) or 0)

    lines = lossq_detect_market_lines_for_appetite(claims, profile_data)

    # Market appetite score means carrier marketability, not claim severity.
    # A real account with claims should rarely display 0/100 unless data is unusable.
    score = 84
    score -= min(total_claims * 2, 16)
    score -= min(open_claims * 4, 22)
    score -= min(litigation_claims * 12, 24)
    score -= min(large_claims * 6, 18)

    if total_incurred >= 1000000:
        score -= 22
    elif total_incurred >= 500000:
        score -= 14
    elif total_incurred >= 250000:
        score -= 8
    elif total_incurred >= 100000:
        score -= 4

    if total_reserve >= 250000:
        score -= 14
    elif total_reserve >= 100000:
        score -= 9
    elif total_reserve >= 50000:
        score -= 5

    if total_claims > 0:
        # Floor prevents valid accounts from showing as impossible to market.
        if litigation_claims == 0 and total_incurred < 500000:
            score = max(score, 48)
        else:
            score = max(score, 35)

    score = max(0, min(100, int(round(score))))

    if score >= 80:
        level = "Preferred"
    elif score >= 70:
        level = "Strong"
    elif score >= 55:
        level = "Moderate"
    elif score >= 40:
        level = "Limited"
    else:
        level = "Distressed"

    best_fit = []

    if "commercial_auto" in lines:
        best_fit.append({
            "carrier_type": "Commercial Auto / Fleet Market",
            "market_category": "Transportation and commercial auto",
            "match_score": max(40, min(88, score + 4)),
            "fit": "Conditional fit" if open_claims else "Strong fit",
            "reason": "Commercial auto or fleet exposure is present. Include driver controls, open-claim status, and corrective actions."
        })

    if "general_liability" in lines:
        best_fit.append({
            "carrier_type": "Regional Casualty / General Liability Market",
            "market_category": "General liability and casualty",
            "match_score": max(40, min(86, score + 2)),
            "fit": "Moderate fit",
            "reason": "General liability activity can be marketed with claim narratives and loss-control explanation."
        })

    if "workers_comp" in lines:
        best_fit.append({
            "carrier_type": "Workers Compensation Market",
            "market_category": "Workers compensation",
            "match_score": max(40, min(84, score)),
            "fit": "Conditional fit" if open_claims else "Standard fit",
            "reason": "Workers compensation exposure should be supported by payroll, mod, return-to-work, and claim status."
        })

    if "property" in lines:
        best_fit.append({
            "carrier_type": "Commercial Property / Package Market",
            "market_category": "Property and package",
            "match_score": max(40, min(86, score + 1)),
            "fit": "Standard fit" if large_claims == 0 else "Selective fit",
            "reason": "Property exposure can be reviewed through package markets with valuation and deductible details."
        })

    if not best_fit:
        best_fit.append({
            "carrier_type": "Regional Commercial Package Market",
            "market_category": "Middle market commercial",
            "match_score": max(40, score),
            "fit": "Needs coverage classification",
            "reason": "LossQ found claims but needs clearer coverage line classification for more specific market targeting."
        })

    best_fit = sorted(best_fit, key=lambda x: int(x.get("match_score") or 0), reverse=True)

    reserve_reason = (
        f"Reserve exposure reviewed: ${total_reserve:,.0f}."
        if total_reserve > 0
        else "Reserve exposure is not clearly populated in the claim rows; verify open-claim reserves before marketing."
    )

    result.update({
        "policy_number": policy_number,
        "is_credible": total_claims > 0,
        "claims_used": total_claims,
        "policy_numbers_used": policy_numbers_used,
        "carrier_appetite_score": score,
        "carrier_appetite_level": level,
        "best_fit_carriers": best_fit,
        "poor_fit_carriers": result.get("poor_fit_carriers") or [],
        "carrier_match_reasons": [
            f"Total claims reviewed: {total_claims}",
            f"Open claims reviewed: {open_claims}",
            f"Litigation claims reviewed: {litigation_claims}",
            f"Total incurred reviewed: ${total_incurred:,.0f}",
            reserve_reason,
            f"Coverage lines detected: {', '.join(lines) if lines else 'Needs classification'}",
        ],
        "market_strategy": (
            "Market this account as a conditional but marketable submission. Lead with the strongest matching market category, "
            "attach claim narratives for open and large losses, confirm reserve adequacy, and explain corrective actions before approaching carriers."
        ),
        "placement_summary": (
            f"Carrier appetite is {score}/100, rated {level}, based on {total_claims} account-specific claims, "
            f"{open_claims} open claims, ${total_incurred:,.0f} incurred, and {litigation_claims} litigation-related claims. "
            "This is a marketability score, not a guarantee of carrier acceptance."
        ),
        "appetite_metrics": {
            **metrics,
            "total_claims": total_claims,
            "open_claims": open_claims,
            "litigation_claims": litigation_claims,
            "total_incurred": total_incurred,
            "total_reserve": total_reserve,
            "largest_loss": largest_loss,
            "large_claims": large_claims,
            "coverage_lines_detected": lines,
        },
        "lossq_appetite_patch_version": "LOSSQ_MARKETABLE_CARRIER_APPETITE_V1",
    })

    return result


@router.get("/carrier-appetite")
def carrier_appetite(policy_number: str | None = Query(default=None), db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    result = engine_response(build_carrier_appetite_engine, db, current_user, policy_number)
    claims, policy_numbers_used, profile_data = get_claims_for_account(db, current_user, policy_number)

    try:
        profile_data = lossq_best_exposure_profile(result, profile_data)
    except Exception:
        pass

    try:
        profile_data = lossq_full_profile_for_exposure(db, current_user, policy_number, result, profile_data)
    except Exception:
        pass

    result["account_profile"] = profile_data
    result = lossq_marketable_carrier_appetite(result, profile_data, claims, policy_numbers_used, policy_number)
    return result


@router.get("/submission-readiness")
def submission_readiness(policy_number: str | None = Query(default=None), db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    claims, policy_numbers_used, profile_data = get_claims_for_account(db, current_user, policy_number)
    quality = data_quality(claims, policy_numbers_used, profile_data)
    if not quality["is_credible"]:
        return {**insufficient_response(policy_number, "submission-readiness"), "submission_readiness_score": None, "submission_readiness_level": "Insufficient Data", "missing_items": quality["issues"], "required_documents": ["Validated policy schedule", "Parsed claim rows", "Currently valued loss runs"], "recommended_actions": ["Correct/upload loss data before marketing."], "claims_used": len(claims), "policy_numbers_used": policy_numbers_used}
    decision = build_underwriter_decision_engine(claims, policy_number)
    score = max(0, min(100, int(decision.get("marketability_score") or 0)))
    level = "Excellent" if score >= 85 else "Good" if score >= 70 else "Needs Work" if score >= 50 else "Not Ready"
    return {"policy_number": policy_number, "is_credible": True, "claims_used": len(claims), "policy_numbers_used": policy_numbers_used, "submission_readiness_score": score, "submission_readiness_level": level, "missing_items": decision.get("underwriting_concerns", []), "required_documents": ["Currently valued loss runs", "Claim narratives", "Reserve status", "Loss-control plan"], "recommended_actions": decision.get("underwriting_concerns", []), "carrier_confidence": "High" if score >= 75 else "Moderate" if score >= 50 else "Low", "submission_quality": level, "readiness_summary": f"Submission readiness is {score}/100 based on validated account-specific claims."}


# LOSSQ_EXPOSURE_AWARE_PREMIUM_FORECAST_V1
def lossq_apply_exposure_to_premium_forecast(result, profile_data, claims):
    result = dict(result or {})
    profile_data = lossq_normalize_profile_data(profile_data)
    ctx = lossq_exposure_context(profile_data)

    if not ctx.get("has_exposure_inputs"):
        result["exposure_inputs_used"] = False
        return result

    current_premium = ctx.get("current_premium") or 0
    target_premium = ctx.get("target_renewal_premium") or 0

    if current_premium > 0:
        result["current_premium"] = int(round(current_premium))

    if current_premium > 0 and target_premium > 0:
        expected_increase = int(round(((target_premium - current_premium) / current_premium) * 100))
        result["expected_renewal_premium"] = int(round(target_premium))
        result["expected_increase_percent"] = expected_increase
        result["best_case_percent"] = max(-10, expected_increase - 5)
        result["likely_range_percent"] = f"{max(-10, expected_increase - 5)}% to {expected_increase + 10}%"
        result["worst_case_percent"] = expected_increase + 10
        result["confidence_score"] = 92
        result["forecast_summary"] = (
            f"LossQ projects ${target_premium:,.0f}, an estimated {expected_increase}% change "
            f"from saved current premium of ${current_premium:,.0f}. This uses saved Exposure Inputs "
            f"plus account-specific claim activity, not a generic modeled premium."
        )

    result["exposure_inputs_used"] = True
    result["exposure_profile"] = {
        "primary_line_of_business": ctx.get("primary_line_of_business"),
        "current_premium": ctx.get("current_premium"),
        "target_renewal_premium": ctx.get("target_renewal_premium"),
        "payroll": ctx.get("payroll"),
        "revenue": ctx.get("revenue"),
        "vehicle_count": ctx.get("vehicle_count"),
        "driver_count": ctx.get("driver_count"),
        "employee_count": ctx.get("employee_count"),
        "property_tiv": ctx.get("property_tiv"),
        "coverage_limit": ctx.get("coverage_limit"),
        "deductible": ctx.get("deductible"),
        "retention": ctx.get("retention"),
        "experience_mod": ctx.get("experience_mod"),
    }
    result["exposure_drivers"] = ctx.get("exposure_drivers") or []
    result["lossq_exposure_patch_version"] = "LOSSQ_EXPOSURE_AWARE_PREMIUM_FORECAST_V1"

    return result


@router.get("/premium-forecast")
def premium_forecast(policy_number: str | None = Query(default=None), db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    result = engine_response(build_premium_forecast_engine, db, current_user, policy_number)
    claims, policy_numbers_used, profile_data = get_claims_for_account(db, current_user, policy_number)
    profile_data = lossq_best_exposure_profile(result, profile_data)
    profile_data = lossq_full_profile_for_exposure(db, current_user, policy_number, result, profile_data)
    result["account_profile"] = profile_data
    result = lossq_apply_exposure_to_premium_forecast(result, profile_data, claims)
    result["policy_numbers_used"] = policy_numbers_used
    return result

@router.get("/carrier-match")
def carrier_match(policy_number: str | None = Query(default=None), db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    result = engine_response(build_carrier_match_engine, db, current_user, policy_number)
    claims, policy_numbers_used, profile_data = get_claims_for_account(db, current_user, policy_number)
    profile_data = lossq_best_exposure_profile(result, profile_data)
    profile_data = lossq_full_profile_for_exposure(db, current_user, policy_number, result, profile_data)
    result["account_profile"] = profile_data
    result = lossq_apply_exposure_to_carrier_match(result, profile_data, claims)
    result["policy_numbers_used"] = policy_numbers_used
    result = lossq_force_exposure_from_result_profile(result)
    return result



# LOSSQ_FULL_ACCOUNT_RENEWAL_MEMO_V1
def lossq_memo_clean(value, fallback="-"):
    text = str(value or "").strip()
    if text.lower() in {"", "none", "null", "nan", "not set", "needs review"}:
        return fallback
    return text


def lossq_memo_money(value):
    try:
        cleaned = str(value or "").replace("$", "").replace(",", "").replace("%", "").strip()
        if cleaned.lower() in {"", "-", "none", "null", "nan"}:
            return 0.0
        return float(cleaned)
    except Exception:
        return 0.0


def lossq_memo_dollar(value):
    amount = lossq_memo_money(value)
    return f"${amount:,.0f}" if amount else "-"


def lossq_memo_int(value):
    try:
        cleaned = str(value or "").replace(",", "").strip()
        if cleaned.lower() in {"", "-", "none", "null", "nan"}:
            return 0
        return int(float(cleaned))
    except Exception:
        return 0


def lossq_memo_profile_value(profile_data, *keys, fallback="-"):
    profile_data = profile_data or {}
    for key in keys:
        value = profile_data.get(key)
        if value not in (None, "", [], {}):
            return lossq_memo_clean(value, fallback)
    return fallback


def lossq_memo_policy_schedule_text(profile_data, policy_numbers_used):
    profile_data = profile_data or {}
    policies = profile_data.get("policies") if isinstance(profile_data.get("policies"), list) else []

    lines = []

    for item in policies:
        if not isinstance(item, dict):
            continue

        policy_number = lossq_memo_clean(
            item.get("policy_number") or item.get("policyNumber") or item.get("policy") or item.get("number"),
            ""
        )

        if not policy_number:
            continue

        line = lossq_memo_clean(
            item.get("line_of_business") or item.get("policy_type") or item.get("coverage") or item.get("lob"),
            "Coverage not classified"
        )

        claim_count = item.get("claim_count")
        total_incurred = item.get("total_incurred")

        detail = f"- {policy_number}: {line}"

        if claim_count not in (None, ""):
            detail += f" | Claims: {claim_count}"

        if total_incurred not in (None, ""):
            detail += f" | Incurred: {lossq_memo_dollar(total_incurred)}"

        lines.append(detail)

    if not lines:
        for policy in policy_numbers_used or []:
            lines.append(f"- {policy}: Coverage classification should be confirmed.")

    return "\\n".join(lines) if lines else "- No policy schedule was available."


def lossq_memo_top_claims_text(claims, limit=6):
    rows = []

    sorted_claims = sorted(
        claims or [],
        key=lambda claim: lossq_memo_money(getattr(claim, "total_incurred", 0)),
        reverse=True,
    )

    for claim in sorted_claims[:limit]:
        claim_number = lossq_memo_clean(getattr(claim, "claim_number", None), "Unknown Claim")
        policy_number = lossq_memo_clean(getattr(claim, "policy_number", None), "Unknown Policy")
        status = lossq_memo_clean(getattr(claim, "status", None), "Unknown Status")
        date_of_loss = lossq_memo_clean(getattr(claim, "date_of_loss", None), "Unknown Date")
        cause = lossq_memo_clean(
            getattr(claim, "cause_of_loss", None) or getattr(claim, "description", None),
            "Cause not classified",
        )
        incurred = lossq_memo_dollar(getattr(claim, "total_incurred", 0))
        reserve = lossq_memo_dollar(getattr(claim, "reserve_amount", 0))

        rows.append(
            f"- {claim_number} | {policy_number} | {status} | DOL: {date_of_loss} | "
            f"Incurred: {incurred} | Reserve: {reserve} | {cause}"
        )

    return "\\n".join(rows) if rows else "- No individual claim rows were available."


def lossq_memo_list(items, fallback):
    if isinstance(items, list) and items:
        return "\\n".join(f"- {lossq_memo_clean(item, fallback)}" for item in items)
    return f"- {fallback}"


def lossq_build_full_account_renewal_memo(
    *,
    policy_number,
    claims,
    policy_numbers_used,
    profile_data,
    intelligence,
    decision,
    appetite,
    forecast,
):
    profile_data = profile_data or {}
    intelligence = intelligence or {}
    decision = decision or {}
    appetite = appetite or {}
    forecast = forecast or {}

    metrics = (
        intelligence.get("metrics")
        or intelligence.get("renewal_metrics")
        or decision.get("decision_metrics")
        or appetite.get("appetite_metrics")
        or {}
    )

    total_claims = int(metrics.get("total_claims") or len(claims or []) or 0)
    open_claims = int(metrics.get("open_claims") or len([claim for claim in claims or [] if is_open(claim)]) or 0)
    litigation_claims = int(metrics.get("litigation_claims") or len([claim for claim in claims or [] if is_litigated(claim)]) or 0)
    total_incurred = lossq_memo_money(metrics.get("total_incurred") or sum(lossq_memo_money(getattr(claim, "total_incurred", 0)) for claim in claims or []))
    total_reserve = lossq_memo_money(metrics.get("total_reserve") or sum(lossq_memo_money(getattr(claim, "reserve_amount", 0)) for claim in claims or []))

    business_name = lossq_memo_profile_value(profile_data, "business_name", "insured", fallback="Selected Account")
    carrier_name = lossq_memo_profile_value(profile_data, "writing_carrier", "carrier_name", fallback="-")
    agency_name = lossq_memo_profile_value(profile_data, "agency_name", fallback="-")
    account_number = lossq_memo_profile_value(profile_data, "account_number", "customer_number", fallback="-")
    main_policy = lossq_memo_profile_value(profile_data, "policy_number", fallback=policy_number or "-")
    effective_date = lossq_memo_profile_value(profile_data, "effective_date", fallback="-")
    expiration_date = lossq_memo_profile_value(profile_data, "expiration_date", fallback="-")
    line_of_business = lossq_memo_profile_value(profile_data, "line_of_business", "exposure_basis", fallback="-")

    current_premium = lossq_memo_dollar(profile_data.get("current_premium") or profile_data.get("expiring_premium"))
    target_premium = lossq_memo_dollar(profile_data.get("target_renewal_premium"))
    payroll = lossq_memo_dollar(profile_data.get("payroll"))
    revenue = lossq_memo_dollar(profile_data.get("revenue") or profile_data.get("sales") or profile_data.get("receipts"))
    property_tiv = lossq_memo_dollar(profile_data.get("property_tiv") or profile_data.get("tiv"))
    deductible = lossq_memo_dollar(profile_data.get("deductible"))
    experience_mod = lossq_memo_profile_value(profile_data, "experience_mod", "mod", fallback="-")
    vehicle_count = lossq_memo_int(profile_data.get("vehicle_count"))
    driver_count = lossq_memo_int(profile_data.get("driver_count"))
    employee_count = lossq_memo_int(profile_data.get("employee_count"))

    renewal_score = intelligence.get("renewal_score", "-")
    renewal_level = intelligence.get("renewal_risk_level") or intelligence.get("risk_level") or "-"
    renewal_probability = decision.get("renewal_probability", "-")
    appetite_score = appetite.get("carrier_appetite_score", "-")
    appetite_level = appetite.get("carrier_appetite_level", "-")
    premium_change = forecast.get("expected_increase_percent", "-")
    expected_premium = forecast.get("expected_renewal_premium")

    executive_summary = (
        intelligence.get("renewal_summary")
        or intelligence.get("summary")
        or f"LossQ reviewed {total_claims} account-specific claims for {business_name}. The account reflects {open_claims} open claims, ${total_incurred:,.0f} total incurred, and ${total_reserve:,.0f} outstanding reserves."
    )

    broker_recommendation = (
        intelligence.get("broker_recommendation")
        or intelligence.get("recommendation")
        or decision.get("recommended_action")
        or "Prepare updated loss runs, claim narratives, reserve status, and corrective-action documentation before renewal marketing."
    )

    memo = f"""LOSSQ AI RENEWAL MEMO

ACCOUNT DETAIL
Account / Insured: {business_name}
Writing Carrier: {carrier_name}
Producing Agency: {agency_name}
Account Number: {account_number}
Main Policy: {main_policy}
Selected Policy / Account Key: {policy_number or main_policy}
Policy Period: {effective_date} to {expiration_date}
Primary Line of Business: {line_of_business}

POLICY SCHEDULE
{lossq_memo_policy_schedule_text(profile_data, policy_numbers_used)}

EXPOSURE INPUTS
Current / Expiring Premium: {current_premium}
Target Renewal Premium: {target_premium}
Payroll: {payroll}
Revenue / Sales: {revenue}
Vehicle Count: {vehicle_count or "-"}
Driver Count: {driver_count or "-"}
Employee Count: {employee_count or "-"}
Property TIV: {property_tiv}
Deductible / Retention: {deductible}
Experience Mod: {experience_mod}

RENEWAL INTELLIGENCE
Renewal Score: {renewal_score}/100
Renewal Risk Level: {renewal_level}
Renewal Probability: {renewal_probability}%
Carrier Appetite: {appetite_score}/100 - {appetite_level}
Premium Forecast: {premium_change}% expected change
Expected Renewal Premium: {lossq_memo_dollar(expected_premium)}

CLAIM SUMMARY
Claims Reviewed: {total_claims}
Open Claims: {open_claims}
Litigation Claims: {litigation_claims}
Total Incurred: ${total_incurred:,.0f}
Outstanding Reserve: ${total_reserve:,.0f}

EXECUTIVE SUMMARY
{executive_summary}

RENEWAL DRIVERS
{lossq_memo_list(intelligence.get("renewal_drivers"), "Claims and exposure information reviewed for renewal positioning.")}

CARRIER CONCERNS
{lossq_memo_list(intelligence.get("carrier_concerns") or decision.get("underwriting_concerns"), "Confirm open claim status, reserves, valuation date, and corrective actions.")}

TOP CLAIMS / CLAIM NARRATIVE ITEMS
{lossq_memo_top_claims_text(claims)}

BROKER RECOMMENDATION
{broker_recommendation}

MARKET STRATEGY
{appetite.get("market_strategy") or appetite.get("placement_summary") or "Approach target markets with claim narratives, reserve explanations, loss-control documentation, and a clear renewal strategy."}

DOCUMENTATION CHECKLIST
- Currently valued loss runs
- Claim narratives for open and large losses
- Reserve status confirmation
- Corrective-action or loss-control summary
- Updated exposure basis and premium target
- Policy schedule confirmation across all lines

LossQ Note: This memo is generated from saved account profile data, policy schedule, claim activity, renewal engines, and exposure inputs available inside LossQ.
"""

    return memo


@router.get("/memo")
def renewal_memo(policy_number: str | None = Query(default=None), db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    claims, policy_numbers_used, profile_data = get_claims_for_account(db, current_user, policy_number)

    # Recover full saved account profile/exposure data before building memo.
    try:
        base_result = {"account_profile": profile_data or {}}
        profile_data = lossq_full_profile_for_exposure(db, current_user, policy_number, base_result, profile_data)
    except Exception:
        profile_data = profile_data or {}

    quality = data_quality(claims, policy_numbers_used, profile_data)

    intelligence = build_underwriting_intelligence(claims)
    intelligence = lossq_apply_exposure_to_underwriting_decision(intelligence, profile_data, claims) if "lossq_apply_exposure_to_underwriting_decision" in globals() else intelligence

    decision = build_underwriter_decision_engine(claims, policy_number)
    appetite = build_carrier_appetite_engine(claims, policy_number)
    forecast = build_premium_forecast_engine(claims, policy_number)

    try:
        appetite = lossq_marketable_carrier_appetite(appetite, profile_data, claims, policy_numbers_used, policy_number)
    except Exception:
        pass

    try:
        forecast = lossq_apply_exposure_to_premium_forecast(forecast, profile_data, claims)
    except Exception:
        pass

    memo = lossq_build_full_account_renewal_memo(
        policy_number=policy_number,
        claims=claims,
        policy_numbers_used=policy_numbers_used,
        profile_data=profile_data,
        intelligence=intelligence,
        decision=decision,
        appetite=appetite,
        forecast=forecast,
    )

    return {
        "memo": memo,
        "renewal_memo": memo,
        "policy_number": policy_number,
        "claims_used": len(claims),
        "policy_numbers_used": policy_numbers_used,
        "account_profile": profile_data,
        "data_quality": quality,
        "memo_quality": "full_account_detail",
        "backend_memo_version": "LOSSQ_FULL_ACCOUNT_RENEWAL_MEMO_V1",
    }

