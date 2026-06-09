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
    probability = max(0, min(100, probability))
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

    metrics = claim_metrics(claims)

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

                profile_data = {
                    "id": getattr(profile, "id", None),
                    "business_name": getattr(profile, "business_name", None),
                    "insured": getattr(profile, "business_name", None),
                    "carrier_name": getattr(profile, "carrier_name", None),
                    "writing_carrier": getattr(profile, "writing_carrier", None),
                    "policy_number": getattr(profile, "policy_number", None),
                    "account_number": getattr(profile, "account_number", None),
                    "customer_number": getattr(profile, "customer_number", None),
                    "effective_date": getattr(profile, "effective_date", None),
                    "expiration_date": getattr(profile, "expiration_date", None),
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


@router.get("/decision")
def renewal_decision(policy_number: str | None = Query(default=None), db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return engine_response(build_underwriter_decision_engine, db, current_user, policy_number)

@router.get("/carrier-appetite")
def carrier_appetite(policy_number: str | None = Query(default=None), db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return engine_response(build_carrier_appetite_engine, db, current_user, policy_number)

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

@router.get("/premium-forecast")
def premium_forecast(policy_number: str | None = Query(default=None), db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return engine_response(build_premium_forecast_engine, db, current_user, policy_number)

@router.get("/carrier-match")
def carrier_match(policy_number: str | None = Query(default=None), db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return engine_response(build_carrier_match_engine, db, current_user, policy_number)

@router.get("/memo")
def renewal_memo(policy_number: str | None = Query(default=None), db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    claims, policy_numbers_used, profile_data = get_claims_for_account(db, current_user, policy_number)
    quality = data_quality(claims, policy_numbers_used, profile_data)
    if not quality["is_credible"]:
        return {"memo": "INSUFFICIENT DATA: LossQ cannot generate a credible renewal memo until policy schedule and claims are parsed and saved.", "policy_number": policy_number, "claims_used": len(claims), "policy_numbers_used": policy_numbers_used, "data_quality": quality}
    intelligence = build_underwriting_intelligence(claims)
    decision = build_underwriter_decision_engine(claims, policy_number)
    appetite = build_carrier_appetite_engine(claims, policy_number)
    forecast = build_premium_forecast_engine(claims, policy_number)
    metrics = intelligence.get("metrics", {})
    memo = f"""LOSSQ AI RENEWAL MEMO\nSelected Account / Policy: {policy_number or 'Selected Account'}\nPolicy Numbers Used: {', '.join(policy_numbers_used)}\nClaims Used: {len(claims)}\n\nRenewal Score: {intelligence.get('renewal_score')}/100\nRenewal Risk Level: {intelligence.get('renewal_risk_level')}\nRenewal Probability: {decision.get('renewal_probability')}%\nCarrier Appetite: {appetite.get('carrier_appetite_level')}\nPremium Forecast: {forecast.get('expected_increase_percent')}% expected change\n\nClaim Summary:\nTotal Claims: {metrics.get('total_claims',0)}\nOpen Claims: {metrics.get('open_claims',0)}\nLitigation Claims: {metrics.get('litigation_claims',0)}\nTotal Incurred: ${metrics.get('total_incurred',0):,.2f}\nTotal Reserve: ${metrics.get('total_reserve',0):,.2f}\n\nBroker Recommendation:\n{intelligence.get('recommendation')}\n"""