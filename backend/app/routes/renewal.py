from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime

from app.database import SessionLocal
from app.auth_utils import get_current_user
from app.routes.summary import build_underwriting_intelligence, get_claims_for_account, data_quality, money, is_open_claim, has_litigation, is_flagged_claim

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
    if len(claims) == 0:
        return {**insufficient_response(policy_number, "carrier-match"), "top_carriers": [], "recommended_carrier": "Insufficient Data", "recommended_score": None, "carrier_match_summary": "No carrier match generated because claims were not parsed or validated."}
    appetite = build_carrier_appetite_engine(claims, policy_number)
    appetite_score = appetite.get("carrier_appetite_score") or 0
    metrics = get_loss_metrics(claims)
    carriers = [
        ("Travelers", 85), ("Liberty Mutual", 82), ("Nationwide", 80), ("CNA", 78),
        ("The Hartford", 79), ("Progressive Commercial", 76), ("State Auto", 74),
        ("Zurich", 73), ("Chubb", 72), ("AmTrust", 70), ("E&S / Specialty Market", 65)
    ]
    matches = []
    for carrier, base in carriers:
        score = base + (appetite_score - 70) * 0.35
        if metrics["litigation_claims"] and carrier in ["Chubb", "Travelers"]: score -= 8
        if metrics["open_claims"] >= 3 and carrier not in ["E&S / Specialty Market", "AmTrust"]: score -= 5
        if appetite_score < 50 and carrier == "E&S / Specialty Market": score += 18
        score = int(max(0, min(100, score)))
        fit = "Excellent" if score >= 85 else "Strong" if score >= 75 else "Moderate" if score >= 65 else "Limited"
        matches.append({"carrier": carrier, "match_score": score, "fit": fit, "reason": "Fit adjusted by claim frequency, severity, open reserves, and litigation."})
    matches.sort(key=lambda x: x["match_score"], reverse=True)
    return {"policy_number": policy_number, "is_credible": True, "top_carriers": matches[:5], "recommended_carrier": matches[0]["carrier"], "recommended_score": matches[0]["match_score"], "carrier_match_summary": f"LossQ recommends {matches[0]['carrier']} with a {matches[0]['match_score']}/100 match based on validated account-specific claims."}


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


def engine_response(builder, db, current_user, policy_number):
    claims, policy_numbers_used, profile_data = get_claims_for_account(db, current_user, policy_number)
    quality = data_quality(claims, policy_numbers_used, profile_data)
    result = builder(claims, policy_number)
    return {**result, "data_quality": quality, "is_credible": quality["is_credible"], "claims_used": len(claims), "policy_numbers_used": policy_numbers_used, "account_profile": profile_data}


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