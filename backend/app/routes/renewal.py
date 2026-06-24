from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime

from app.database import SessionLocal
from app.auth_utils import get_current_user
from app.plan_limits import require_package_access
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


# LOSSQ_REALISTIC_RENEWAL_MODEL_HELPERS_V1
def lossq_model_money(value):
  try:
    return money(value)
  except Exception:
    try:
      return float(str(value or "0").replace("$", "").replace(",", "").strip() or 0)
    except Exception:
      return 0.0


def lossq_model_claim_line(claim):
  line_text = str(
    getattr(claim, "line_of_business", "")
    or getattr(claim, "claim_type", "")
    or getattr(claim, "coverage", "")
    or getattr(claim, "policy_type", "")
    or ""
  ).lower()

  policy_text = str(getattr(claim, "policy_number", "") or "").upper()

  if "worker" in line_text or "comp" in line_text or "-WC-" in policy_text:
    return "workers_comp"
  if "liquor" in line_text:
    return "liquor_liability"
  if "auto" in line_text or "-AL-" in policy_text or "-AUTO-" in policy_text:
    return "commercial_auto"
  if "cargo" in line_text or "-CG-" in policy_text or "-CARGO-" in policy_text:
    return "cargo"
  if "property" in line_text or "-CP-" in policy_text or "-PROP-" in policy_text:
    return "property"
  if "bop" in line_text or "businessowner" in line_text or "-BOP-" in policy_text:
    return "bop"
  if "cyber" in line_text or "-CY-" in policy_text or "-CYBER-" in policy_text:
    return "cyber"
  if "employment" in line_text or "epli" in line_text or "-EPLI-" in policy_text:
    return "epli"
  if "director" in line_text or "officer" in line_text or "d&o" in line_text or "-DO-" in policy_text:
    return "d_and_o"
  if "professional" in line_text or "errors" in line_text or "omissions" in line_text or "-PL-" in policy_text or "-EO-" in policy_text:
    return "professional_liability"
  if "inland" in line_text or "marine" in line_text or "-IM-" in policy_text:
    return "inland_marine"
  if "crime" in line_text or "-CRIME-" in policy_text:
    return "crime"
  if "umbrella" in line_text or "excess" in line_text or "-UMB-" in policy_text or "-XS-" in policy_text:
    return "umbrella_excess"
  if "general" in line_text or "liability" in line_text or "-GL-" in policy_text:
    return "general_liability"

  return "other_commercial"


def lossq_model_line_label(code):
  labels = {
    "general_liability": "General Liability",
    "workers_comp": "Workers Compensation",
    "commercial_auto": "Commercial Auto",
    "cargo": "Cargo",
    "property": "Commercial Property",
    "bop": "BOP",
    "cyber": "Cyber",
    "epli": "EPLI",
    "d_and_o": "D&O",
    "professional_liability": "Professional Liability",
    "inland_marine": "Inland Marine",
    "crime": "Crime",
    "liquor_liability": "Liquor Liability",
    "umbrella_excess": "Umbrella / Excess",
    "other_commercial": "Other Commercial Line",
  }
  return labels.get(code, "Other Commercial Line")


def lossq_model_metrics(claims):
  claims = claims or []

  total_claims = len(claims)
  open_claims = len([claim for claim in claims if is_open(claim)])
  closed_claims = max(total_claims - open_claims, 0)
  litigation_claims = len([claim for claim in claims if is_litigated(claim)])

  total_paid = 0.0
  total_reserve = 0.0
  total_incurred = 0.0
  largest_loss = 0.0
  line_summary = {}

  for claim in claims:
    paid = lossq_model_money(getattr(claim, "paid_amount", 0))
    reserve = lossq_model_money(getattr(claim, "reserve_amount", 0))
    total = lossq_model_money(getattr(claim, "total_incurred", 0))
    if total <= 0 and (paid > 0 or reserve > 0):
      total = paid + reserve

    total_paid += paid
    total_reserve += reserve
    total_incurred += total
    largest_loss = max(largest_loss, total)

    line = lossq_model_claim_line(claim)
    if line not in line_summary:
      line_summary[line] = {
        "line_code": line,
        "line_of_business": lossq_model_line_label(line),
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

    if is_open(claim):
      line_summary[line]["open_claims"] += 1
    if is_litigated(claim):
      line_summary[line]["litigation_claims"] += 1

  average_severity = total_incurred / total_claims if total_claims else 0
  reserve_ratio = total_reserve / total_incurred if total_incurred else 0
  closure_rate = closed_claims / total_claims if total_claims else 0
  largest_loss_ratio = largest_loss / total_incurred if total_incurred else 0

  large_claims_50k = 0
  large_claims_100k = 0
  severe_claims_250k = 0

  for claim in claims:
    paid = lossq_model_money(getattr(claim, "paid_amount", 0))
    reserve = lossq_model_money(getattr(claim, "reserve_amount", 0))
    total = lossq_model_money(getattr(claim, "total_incurred", 0))
    if total <= 0 and (paid > 0 or reserve > 0):
      total = paid + reserve

    if total >= 50000:
      large_claims_50k += 1
    if total >= 100000:
      large_claims_100k += 1
    if total >= 250000:
      severe_claims_250k += 1

  line_output = list(line_summary.values())
  line_output.sort(key=lambda item: item["total_incurred"], reverse=True)

  return {
    "total_claims": total_claims,
    "open_claims": open_claims,
    "closed_claims": closed_claims,
    "litigation_claims": litigation_claims,
    "total_paid": total_paid,
    "total_reserve": total_reserve,
    "total_incurred": total_incurred,
    "largest_loss": largest_loss,
    "average_severity": average_severity,
    "reserve_ratio": reserve_ratio,
    "closure_rate": closure_rate,
    "largest_loss_ratio": largest_loss_ratio,
    "large_claims_50k": large_claims_50k,
    "large_claims_100k": large_claims_100k,
    "severe_claims_250k": severe_claims_250k,
    "line_summary": line_output,
    "line_codes": list(line_summary.keys()),
  }


def lossq_model_market_band(score):
  if score >= 85:
    return "Preferred"
  if score >= 72:
    return "Standard"
  if score >= 58:
    return "Cautious"
  if score >= 42:
    return "Restricted"
  return "Distressed"


def lossq_model_premium_band(increase):
  if increase <= 5:
    return "Flat to +5%"
  if increase <= 10:
    return "+5% to +10%"
  if increase <= 20:
    return "+10% to +20%"
  if increase <= 35:
    return "+20% to +35%"
  if increase <= 55:
    return "+35% to +55%"
  return "+55% or higher / non-renewal watch"


# LOSSQ_REALISTIC_UNDERWRITER_DECISION_ENGINE_V1
def build_underwriter_decision_engine(claims, policy_number=None):
  if len(claims) == 0:
    return {
      **insufficient_response(policy_number, "decision"),
      "renewal_probability": None,
      "quote_probability": None,
      "expected_premium_impact": "Insufficient Data",
      "carrier_appetite": "Insufficient Data",
      "marketability_score": None,
      "submission_readiness": "Needs validated claims before marketing",
      "underwriting_concerns": ["No claims available for underwriting decision."],
      "best_market_types": [],
      "required_followups": ["Validate parsed claims and policy schedule."],
      "broker_action_plan": ["Correct parser/upload data before releasing to markets."],
      "underwriter_decision_summary": "Insufficient claim data. Do not rely on this decision.",
    }

  intelligence = build_underwriting_intelligence(claims)
  base_metrics = get_loss_metrics(claims)
  metrics = lossq_model_metrics(claims)

  renewal_score = int(intelligence.get("renewal_score") or 0)

  probability = 96

  probability -= max(0, metrics["total_claims"] - 2) * 3
  probability -= min(metrics["open_claims"] * 6, 24)
  probability -= min(metrics["litigation_claims"] * 10, 30)
  probability -= min(metrics["large_claims_100k"] * 8, 24)
  probability -= min(metrics["severe_claims_250k"] * 12, 24)

  if metrics["total_incurred"] >= 1500000:
    probability -= 24
  elif metrics["total_incurred"] >= 1000000:
    probability -= 18
  elif metrics["total_incurred"] >= 500000:
    probability -= 12
  elif metrics["total_incurred"] >= 250000:
    probability -= 7

  if metrics["reserve_ratio"] >= 0.60:
    probability -= 14
  elif metrics["reserve_ratio"] >= 0.40:
    probability -= 9
  elif metrics["reserve_ratio"] >= 0.25:
    probability -= 5

  if metrics["closure_rate"] >= 0.80 and metrics["total_reserve"] <= 0:
    probability += 5
  elif metrics["closure_rate"] >= 0.65 and metrics["open_claims"] <= 1:
    probability += 3

  if renewal_score:
    probability = int((probability * 0.65) + (renewal_score * 0.35))

  probability = max(12, min(100, round(probability)))

  marketability = probability
  marketability -= min(metrics["open_claims"] * 3, 12)
  marketability -= min(metrics["litigation_claims"] * 4, 16)
  if metrics["reserve_ratio"] >= 0.40:
    marketability -= 7
  if metrics["large_claims_100k"] >= 2:
    marketability -= 6
  marketability = max(0, min(100, round(marketability)))

  appetite = lossq_model_market_band(marketability)

  if probability >= 85:
    impact = "Flat to +5%"
    ready = "Ready for standard renewal marketing with current valued loss runs."
  elif probability >= 72:
    impact = "+5% to +10%"
    ready = "Marketable with broker narrative and updated loss valuation."
  elif probability >= 58:
    impact = "+10% to +20%"
    ready = "Marketable with claim narratives, reserve support, and corrective-action detail."
  elif probability >= 42:
    impact = "+20% to +35%"
    ready = "Needs underwriting cleanup before broad marketing; target specialty or incumbent markets first."
  else:
    impact = "+35% or higher / possible non-renewal concern"
    ready = "Not ready for broad market release without updated loss runs, open-claim status, litigation updates, and corrective-action documentation."

  concerns = []
  if metrics["open_claims"]:
    concerns.append(f"{metrics['open_claims']} open claim(s) may continue developing before renewal.")
  if metrics["litigation_claims"]:
    concerns.append(f"{metrics['litigation_claims']} litigated claim(s) create uncertainty around defense cost, venue, and ultimate severity.")
  if metrics["total_reserve"]:
    concerns.append(f"${metrics['total_reserve']:,.0f} in outstanding reserves may pressure terms and quote authority.")
  if metrics["large_claims_100k"]:
    concerns.append(f"{metrics['large_claims_100k']} large claim(s) exceed $100,000 and require carrier-ready narratives.")
  if metrics["total_claims"] >= 5:
    concerns.append("Claim frequency may raise questions about controls, maintenance, staffing, safety, or operational discipline.")
  if metrics["reserve_ratio"] >= 0.40:
    concerns.append(f"Reserve ratio is {metrics['reserve_ratio']:.0%}, indicating material unresolved loss development.")

  if not concerns:
    concerns.append("No major underwriting concerns detected from the validated claim set.")

  best_market_types = []
  line_codes = set(metrics.get("line_codes") or [])

  if marketability >= 80:
    best_market_types.append("Admitted standard commercial markets")
    best_market_types.append("Regional preferred markets")
  elif marketability >= 60:
    best_market_types.append("Regional commercial markets")
    best_market_types.append("Middle-market carriers")
    best_market_types.append("Incumbent renewal market")
  elif marketability >= 42:
    best_market_types.append("Specialty markets")
    best_market_types.append("Program markets where line appetite matches operations")
    best_market_types.append("Incumbent market with corrective-action narrative")
  else:
    best_market_types.append("E&S or specialty markets")
    best_market_types.append("Incumbent-only strategy until open claim/litigation issues are clarified")

  if "cyber" in line_codes:
    best_market_types.append("Cyber specialty markets requiring controls, MFA, EDR, backups, and incident response detail")
  if "umbrella_excess" in line_codes:
    best_market_types.append("Umbrella/excess markets requiring underlying loss explanations and limit structure")
  if "epli" in line_codes:
    best_market_types.append("EPLI markets requiring HR controls, handbook, training, and claim status")
  if "property" in line_codes:
    best_market_types.append("Property markets requiring COPE details, roof age, valuation, and loss mitigation")
  if "workers_comp" in line_codes:
    best_market_types.append("Workers compensation markets requiring safety controls and return-to-work detail")

  required_followups = [
    "Current valued loss runs with valuation date",
    "Large-loss narratives with corrective action",
    "Updated exposure basis and current/expiring premium by line",
  ]
  if metrics["open_claims"]:
    required_followups.append("Open-claim adjuster status, reserve basis, and expected closure timeline")
  if metrics["litigation_claims"]:
    required_followups.append("Litigation report with counsel, venue, settlement posture, and next milestone")

  broker_action_plan = [
    "Lead with a concise account narrative tying claim experience to corrective action.",
    "Separate one-time severity events from recurring frequency issues where the facts support it.",
    "Package open claims and litigated claims before approaching preferred markets.",
  ]

  if marketability < 60:
    broker_action_plan.append("Approach incumbent and specialty markets first; hold preferred markets until claim documentation is complete.")
  else:
    broker_action_plan.append("Market standard and regional carriers with a complete submission and current valuation.")

  return {
    "policy_number": policy_number,
    "is_credible": True,
    "renewal_probability": probability,
    "quote_probability": probability,
    "expected_premium_impact": impact,
    "carrier_appetite": appetite,
    "marketability_score": marketability,
    "submission_readiness": ready,
    "underwriting_concerns": concerns,
    "best_market_types": list(dict.fromkeys(best_market_types)),
    "required_followups": required_followups,
    "broker_action_plan": broker_action_plan,
    "decision_metrics": {**base_metrics, **metrics},
    "underwriter_decision_summary": (
      f"LossQ estimates a {probability}% renewal/quote probability and {marketability}/100 marketability score. "
      f"The model considered {metrics['total_claims']} claims, {metrics['open_claims']} open claims, "
      f"{metrics['litigation_claims']} litigated claims, ${metrics['total_incurred']:,.0f} total incurred, "
      f"${metrics['total_reserve']:,.0f} reserves, {metrics['reserve_ratio']:.0%} reserve ratio, "
      f"and {metrics['large_claims_100k']} large claim(s) over $100,000."
    ),
  }


# LOSSQ_REALISTIC_CARRIER_APPETITE_ENGINE_V1
def build_carrier_appetite_engine(claims, policy_number=None):
  if len(claims) == 0:
    return {
      **insufficient_response(policy_number, "carrier-appetite"),
      "carrier_appetite_score": None,
      "carrier_appetite_level": "Insufficient Data",
      "best_fit_carriers": [],
      "poor_fit_carriers": [],
      "carrier_match_reasons": ["No validated claims available."],
      "market_strategy": "Do not market until loss data is validated.",
      "placement_summary": "Insufficient claim data. Carrier appetite has not been rated.",
    }

  decision = build_underwriter_decision_engine(claims, policy_number)
  metrics = lossq_model_metrics(claims)

  score = int(decision.get("marketability_score") or 0)

  # Carrier appetite sensitivity.
  score -= min(metrics["open_claims"] * 3, 12)
  score -= min(metrics["litigation_claims"] * 5, 18)
  score -= min(metrics["large_claims_100k"] * 4, 14)

  if metrics["reserve_ratio"] >= 0.60:
    score -= 10
  elif metrics["reserve_ratio"] >= 0.40:
    score -= 6

  if metrics["total_claims"] >= 10:
    score -= 8
  elif metrics["total_claims"] >= 6:
    score -= 5

  if metrics["closure_rate"] >= 0.80 and metrics["total_reserve"] <= 0:
    score += 5

  score = max(0, min(100, round(score)))
  level = lossq_model_market_band(score)

  line_codes = set(metrics.get("line_codes") or [])

  best_fit = []
  poor_fit = []

  if level in {"Preferred", "Standard"}:
    best_fit.extend(["Admitted standard markets", "Regional commercial carriers", "Incumbent renewal market"])
  elif level == "Cautious":
    best_fit.extend(["Regional commercial carriers", "Middle-market carriers", "Incumbent market with narrative"])
    poor_fit.extend(["Preferred low-touch markets"])
  elif level == "Restricted":
    best_fit.extend(["Specialty markets", "Program markets", "Incumbent market with corrective-action plan"])
    poor_fit.extend(["Preferred standard markets", "Markets with low tolerance for open reserves or litigation"])
  else:
    best_fit.extend(["E&S markets", "Specialty distressed-account markets", "Incumbent-only strategy pending documentation"])
    poor_fit.extend(["Standard admitted markets", "Preferred regional markets"])

  if "property" in line_codes:
    best_fit.append("Property markets that can underwrite COPE, TIV, roof, CAT, and loss-control detail")
  if "cyber" in line_codes:
    best_fit.append("Cyber specialty markets that review MFA, EDR, backups, and incident response controls")
  if "epli" in line_codes:
    best_fit.append("EPLI markets that review HR controls, handbook, training, and prior complaint status")
  if "umbrella_excess" in line_codes:
    best_fit.append("Umbrella/excess markets requiring underlying claim narrative and limit adequacy")
  if "workers_comp" in line_codes:
    best_fit.append("Workers compensation markets requiring safety program and return-to-work details")
  if "commercial_auto" in line_codes:
    best_fit.append("Commercial auto markets requiring driver controls, MVR standards, telematics, and fleet safety")

  reasons = [
    f"Carrier appetite score: {score}/100 ({level}).",
    f"Total incurred reviewed: ${metrics['total_incurred']:,.0f}.",
    f"Open claims: {metrics['open_claims']}; litigated claims: {metrics['litigation_claims']}.",
    f"Outstanding reserves: ${metrics['total_reserve']:,.0f} ({metrics['reserve_ratio']:.0%} reserve ratio).",
    f"Large losses over $100,000: {metrics['large_claims_100k']}.",
  ]

  if level == "Preferred":
    strategy = "Release to standard and regional markets with a clean submission, current valuation, and concise loss narrative."
  elif level == "Standard":
    strategy = "Market standard and regional carriers, but include claim narrative and reserve support up front."
  elif level == "Cautious":
    strategy = "Prioritize markets comfortable with moderate loss activity. Include large-loss narratives, open-claim status, and corrective action."
  elif level == "Restricted":
    strategy = "Start with incumbent, specialty, and program markets. Hold preferred markets until open claims, litigation, and reserves are documented."
  else:
    strategy = "Treat as distressed placement. Build documentation first, then approach E&S/specialty markets and the incumbent carrier."

  return {
    "policy_number": policy_number,
    "is_credible": True,
    "carrier_appetite_score": score,
    "carrier_appetite_level": level,
    "best_fit_carriers": list(dict.fromkeys(best_fit)),
    "poor_fit_carriers": list(dict.fromkeys(poor_fit)),
    "carrier_match_reasons": reasons,
    "market_strategy": strategy,
    "placement_summary": (
      f"Carrier appetite is {score}/100, rated {level}. "
      f"LossQ expects {decision.get('expected_premium_impact')} pricing pressure based on "
      f"{metrics['total_claims']} claims, ${metrics['total_incurred']:,.0f} incurred, "
      f"{metrics['open_claims']} open claims, {metrics['litigation_claims']} litigated claims, "
      f"and ${metrics['total_reserve']:,.0f} reserves."
    ),
    "appetite_metrics": metrics,
  }


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


# LOSSQ_REALISTIC_PREMIUM_FORECAST_ENGINE_V1
def build_premium_forecast_engine(claims, policy_number=None):
  if len(claims) == 0:
    return {
      **insufficient_response(policy_number, "premium-forecast"),
      "current_premium": None,
      "expected_renewal_premium": None,
      "expected_increase_percent": None,
      "best_case_percent": None,
      "likely_range_percent": "Insufficient Data",
      "worst_case_percent": None,
      "confidence_score": 0,
      "forecast_drivers": ["No validated claims were available."],
      "forecast_summary": "Premium forecast not generated. LossQ needs parsed claims and preferably current premium/exposure data.",
    }

  intelligence = build_underwriting_intelligence(claims)
  decision = build_underwriter_decision_engine(claims, policy_number)
  metrics = lossq_model_metrics(claims)

  total_incurred = metrics["total_incurred"]

  # Modeled current premium is a fallback when real premium is not available.
  # It is not a quote; it gives the model a denominator for expected pricing pressure.
  modeled_current = max(25000, int((total_incurred * 0.55) + 45000))
  loss_ratio = total_incurred / modeled_current if modeled_current else 0

  increase = 0

  if loss_ratio >= 2.00:
    increase += 42
  elif loss_ratio >= 1.50:
    increase += 32
  elif loss_ratio >= 1.00:
    increase += 24
  elif loss_ratio >= 0.75:
    increase += 16
  elif loss_ratio >= 0.50:
    increase += 9
  elif loss_ratio <= 0.20:
    increase -= 3

  if metrics["total_claims"] >= 12:
    increase += 14
  elif metrics["total_claims"] >= 8:
    increase += 10
  elif metrics["total_claims"] >= 5:
    increase += 6
  elif metrics["total_claims"] <= 1:
    increase -= 2

  if metrics["largest_loss"] >= 500000:
    increase += 20
  elif metrics["largest_loss"] >= 250000:
    increase += 14
  elif metrics["largest_loss"] >= 100000:
    increase += 8
  elif metrics["largest_loss"] >= 50000:
    increase += 4

  if metrics["open_claims"]:
    increase += min(metrics["open_claims"] * 4, 18)

  if metrics["litigation_claims"]:
    increase += min(metrics["litigation_claims"] * 8, 24)

  if metrics["reserve_ratio"] >= 0.60:
    increase += 14
  elif metrics["reserve_ratio"] >= 0.40:
    increase += 9
  elif metrics["reserve_ratio"] >= 0.25:
    increase += 5

  renewal_score = int(intelligence.get("renewal_score") or 0)
  if renewal_score < 40:
    increase += 16
  elif renewal_score < 55:
    increase += 10
  elif renewal_score < 70:
    increase += 5
  elif renewal_score >= 85:
    increase -= 4

  if int(decision.get("marketability_score") or 0) < 45:
    increase += 12
  elif int(decision.get("marketability_score") or 0) < 60:
    increase += 7

  if metrics["closure_rate"] >= 0.80 and metrics["total_reserve"] <= 0:
    increase -= 4

  increase = int(max(-5, min(125, round(increase))))

  best_case = max(-5, increase - 10)
  worst_case = min(150, increase + 20)

  if metrics["open_claims"] or metrics["litigation_claims"] or metrics["reserve_ratio"] >= 0.35:
    worst_case = min(150, increase + 30)

  expected = int(modeled_current * (1 + increase / 100))

  confidence = 50
  if metrics["total_claims"] >= 3:
    confidence += 10
  if metrics["line_summary"]:
    confidence += 8
  if metrics["total_incurred"] > 0:
    confidence += 7
  if metrics["open_claims"] or metrics["litigation_claims"]:
    confidence -= 5
  if metrics["total_claims"] <= 1:
    confidence -= 8

  confidence = max(35, min(85, confidence))

  pricing_action = lossq_model_premium_band(increase)

  drivers = [
    f"Modeled loss ratio: {loss_ratio * 100:.1f}%.",
    f"{metrics['total_claims']} account-specific claim(s) reviewed.",
    f"Total incurred: ${metrics['total_incurred']:,.0f}.",
    f"Largest loss: ${metrics['largest_loss']:,.0f}.",
    f"Open claims: {metrics['open_claims']}.",
    f"Litigated claims: {metrics['litigation_claims']}.",
    f"Outstanding reserves: ${metrics['total_reserve']:,.0f} ({metrics['reserve_ratio']:.0%} reserve ratio).",
    f"Marketability score: {decision.get('marketability_score')}/100.",
  ]

  if metrics["line_summary"]:
    top_line = metrics["line_summary"][0]
    drivers.append(
      f"Primary loss driver: {top_line['line_of_business']} with ${top_line['total_incurred']:,.0f} incurred."
    )

  return {
    "policy_number": policy_number,
    "is_credible": True,
    "current_premium": modeled_current,
    "expected_renewal_premium": expected,
    "expected_increase_percent": increase,
    "best_case_percent": best_case,
    "likely_range_percent": f"{best_case}% to {worst_case}%",
    "worst_case_percent": worst_case,
    "pricing_action_band": pricing_action,
    "non_renewal_watch": bool(increase >= 45 or int(decision.get("marketability_score") or 0) < 42),
    "confidence_score": confidence,
    "forecast_drivers": drivers,
    "forecast_metrics": metrics,
    "forecast_summary": (
      f"LossQ projects a modeled renewal premium of ${expected:,.0f}, an estimated {increase}% change "
      f"from modeled current premium of ${modeled_current:,.0f}. Expected pricing action is {pricing_action}. "
      f"This is not a carrier quote; it is a rules-based forecast using loss ratio, frequency, severity, "
      f"open reserves, litigation, line mix, and marketability."
    ),
  }


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



# LOSSQ_CANADA_MARKET_INTELLIGENCE_V1
def lossq_canada_market_text_v1(value):
  try:
    return str(value or '').strip()
  except Exception:
    return ''

def lossq_canada_market_is_account_v1(profile_data=None, claims=None):
  parts = []
  if isinstance(profile_data, dict):
    parts.extend([lossq_canada_market_text_v1(v) for v in profile_data.values()])
    for row in profile_data.get('policies') or profile_data.get('policy_schedule') or []:
      if isinstance(row, dict):
        parts.extend([lossq_canada_market_text_v1(v) for v in row.values()])
  if isinstance(claims, list):
    for claim in claims[:50]:
      if isinstance(claim, dict):
        parts.extend([lossq_canada_market_text_v1(v) for v in claim.values()])
  text = ' '.join(parts).lower()
  tokens = ['canada', 'cad', 'ca$', 'c$', 'ontario', 'alberta', 'british columbia', 'quebec', 'québec', 'wsib', 'wcb', 'worksafebc', 'cnesst']
  return any(token in text for token in tokens)

def lossq_canada_market_line_key_v1(value):
  text = lossq_canada_market_text_v1(value).lower()
  if any(x in text for x in ['cgl', 'general liability']):
    return 'gl'
  if any(x in text for x in ['fleet', 'auto', 'automobile']):
    return 'auto'
  if any(x in text for x in ['wcb', 'wsib', 'workers', 'comp', 'worksafebc', 'cnesst']):
    return 'wc'
  if any(x in text for x in ['errors', 'omissions', 'e&o', 'professional']):
    return 'professional'
  if 'cyber' in text:
    return 'cyber'
  if any(x in text for x in ['umbrella', 'excess']):
    return 'umbrella'
  if 'property' in text:
    return 'property'
  if any(x in text for x in ['cargo', 'transit']):
    return 'cargo'
  return ''

def lossq_canada_market_lines_v1(profile_data=None, claims=None):
  lines = set()
  if isinstance(profile_data, dict):
    for row in profile_data.get('policies') or profile_data.get('policy_schedule') or []:
      if isinstance(row, dict):
        key = lossq_canada_market_line_key_v1(row.get('line_of_business') or row.get('coverage') or row.get('policy_type'))
        if key:
          lines.add(key)
  if isinstance(claims, list):
    for claim in claims:
      if isinstance(claim, dict):
        key = lossq_canada_market_line_key_v1(claim.get('line_of_business') or claim.get('claim_type'))
        if key:
          lines.add(key)
  return lines

def lossq_canada_market_metrics_v1(result=None, claims=None):
  metrics = {}
  if isinstance(result, dict):
    metrics.update(result.get('carrier_match_metrics') or {})
    metrics.update(result.get('appetite_metrics') or {})
  if isinstance(claims, list) and claims:
    total_claims = len(claims)
    open_claims = 0
    total_incurred = 0.0
    total_reserve = 0.0
    litigation_claims = 0
    for claim in claims:
      if not isinstance(claim, dict):
        continue
      status = lossq_canada_market_text_v1(claim.get('status') or claim.get('claim_status')).lower()
      if 'open' in status:
        open_claims += 1
      try:
        total_incurred += float(claim.get('total_incurred') or claim.get('incurred') or 0)
      except Exception:
        pass
      try:
        total_reserve += float(claim.get('reserve_amount') or claim.get('reserve') or 0)
      except Exception:
        pass
      if claim.get('litigation') is True or claim.get('attorney_assigned') is True or claim.get('suit_filed') is True:
        litigation_claims += 1
    metrics.update({
      'total_claims': total_claims,
      'open_claims': open_claims,
      'total_incurred': total_incurred,
      'total_reserve': total_reserve,
      'litigation_claims': litigation_claims,
    })
  return metrics

def lossq_canada_carrier_directory_v1():
  return [
    {'carrier': 'Intact Insurance', 'lines': {'gl', 'property', 'auto', 'umbrella'}, 'base': 82, 'category': 'Canadian standard commercial / middle market'},
    {'carrier': 'Aviva Canada', 'lines': {'gl', 'property', 'auto', 'umbrella'}, 'base': 79, 'category': 'Canadian commercial package'},
    {'carrier': 'Northbridge Insurance', 'lines': {'gl', 'auto', 'cargo', 'property'}, 'base': 78, 'category': 'Canadian commercial specialty'},
    {'carrier': 'Zurich Canada', 'lines': {'gl', 'property', 'professional', 'cyber', 'umbrella'}, 'base': 77, 'category': 'Canadian middle market / specialty'},
    {'carrier': 'CNA Canada', 'lines': {'gl', 'professional', 'cyber', 'property'}, 'base': 75, 'category': 'Canadian casualty / professional'},
    {'carrier': 'Chubb Canada', 'lines': {'property', 'professional', 'cyber', 'umbrella'}, 'base': 74, 'category': 'Canadian specialty / executive risk'},
    {'carrier': 'Lloyd’s Canada', 'lines': {'professional', 'cyber', 'umbrella', 'property'}, 'base': 73, 'category': 'Canadian specialty market'},
    {'carrier': 'Definity / Economical Insurance', 'lines': {'gl', 'auto', 'property'}, 'base': 72, 'category': 'Canadian regional commercial'},
    {'carrier': 'Wawanesa Commercial', 'lines': {'gl', 'auto', 'property'}, 'base': 70, 'category': 'Canadian regional commercial'},
  ]

def lossq_apply_canada_carrier_appetite_v1(result, profile_data=None, claims=None, policy_numbers_used=None, policy_number=None):
  result = dict(result or {})
  if not lossq_canada_market_is_account_v1(profile_data, claims):
    return result
  metrics = lossq_canada_market_metrics_v1(result, claims)
  lines = lossq_canada_market_lines_v1(profile_data, claims) or {'gl'}
  total_claims = int(metrics.get('total_claims') or 0)
  open_claims = int(metrics.get('open_claims') or 0)
  litigation_claims = int(metrics.get('litigation_claims') or 0)
  total_incurred = float(metrics.get('total_incurred') or 0)
  total_reserve = float(metrics.get('total_reserve') or 0)
  score = 82
  score -= min(open_claims * 5, 20)
  score -= min(litigation_claims * 8, 20)
  if total_incurred >= 250000:
    score -= 18
  elif total_incurred >= 100000:
    score -= 10
  elif total_incurred >= 50000:
    score -= 5
  if total_reserve >= 100000:
    score -= 10
  elif total_reserve >= 50000:
    score -= 6
  score = max(0, min(100, int(score)))
  level = 'Strong' if score >= 75 else 'Moderate' if score >= 55 else 'Restricted' if score >= 35 else 'Critical'
  target_carriers = [row['carrier'] for row in lossq_canada_carrier_directory_v1() if lines.intersection(row['lines'])][:5]
  result.update({
    'carrier_appetite_score': score,
    'carrier_appetite_level': level,
    'best_fit_carriers': target_carriers,
    'best_fit_markets': target_carriers,
    'carrier_match_reasons': [
      f'Canada account detected from uploaded country/currency/province signals.',
      f'Coverage lines detected: {', '.join(sorted(lines))}.',
      f'Reviewed {total_claims} claim(s), {open_claims} open claim(s), CAD ${total_incurred:,.0f} incurred, CAD ${total_reserve:,.0f} reserves.',
    ],
    'market_strategy': f'Market as a Canadian commercial account. Prioritize Canadian carriers comfortable with {', '.join(sorted(lines))} and attach current claim narratives/reserve status.',
    'placement_summary': f'Canadian carrier appetite is {score}/100, rated {level}, based on {total_claims} claim(s), {open_claims} open claim(s), CAD ${total_incurred:,.0f} incurred, and detected lines {', '.join(sorted(lines))}.',
    'appetite_metrics': {**metrics, 'coverage_lines_detected': sorted(lines), 'currency': 'CAD', 'country': 'Canada'},
    'carrier_country': 'Canada',
    'market_currency': 'CAD',
    'lossq_canada_appetite_version': 'LOSSQ_CANADA_CARRIER_APPETITE_V1',
  })
  return result

def lossq_apply_canada_carrier_match_v1(result, profile_data=None, claims=None):
  result = dict(result or {})
  if not lossq_canada_market_is_account_v1(profile_data, claims):
    return result
  metrics = lossq_canada_market_metrics_v1(result, claims)
  lines = lossq_canada_market_lines_v1(profile_data, claims) or {'gl'}
  total_claims = int(metrics.get('total_claims') or 0)
  open_claims = int(metrics.get('open_claims') or 0)
  total_incurred = float(metrics.get('total_incurred') or 0)
  total_reserve = float(metrics.get('total_reserve') or 0)
  matches = []
  for market in lossq_canada_carrier_directory_v1():
    overlap = lines.intersection(market['lines'])
    if not overlap:
      continue
    score = market['base'] + len(overlap) * 4
    score -= min(open_claims * 3, 12)
    if total_incurred >= 250000:
      score -= 15
    elif total_incurred >= 100000:
      score -= 8
    if total_reserve >= 50000:
      score -= 5
    score = max(0, min(100, int(score)))
    reason = f"{market['carrier']}: Canada-market fit for {', '.join(sorted(overlap))}. Reviewed {total_claims} claim(s), {open_claims} open claim(s), CAD ${total_incurred:,.0f} incurred, and CAD ${total_reserve:,.0f} reserves."
    matches.append({'carrier': market['carrier'], 'group': market['carrier'], 'match_score': score, 'score': score, 'market_category': market['category'], 'reason': reason, 'match_reason': reason, 'country': 'Canada', 'currency': 'CAD'})
  matches = sorted(matches, key=lambda row: row.get('match_score', 0), reverse=True)
  if not matches:
    return result
  recommended = matches[0]
  result.update({
    'top_carriers': matches[:5],
    'recommended_carrier': recommended.get('carrier'),
    'recommended_score': recommended.get('match_score'),
    'recommended_market_category': recommended.get('market_category'),
    'carrier_match_reasons': [row.get('reason') for row in matches[:5]],
    'carrier_match_summary': f"LossQ recommends {recommended.get('carrier')} with a {recommended.get('match_score')}/100 Canada-market match. Ranking used Canadian jurisdiction/currency signals, coverage lines {', '.join(sorted(lines))}, {total_claims} claim(s), {open_claims} open claim(s), CAD ${total_incurred:,.0f} incurred, and CAD ${total_reserve:,.0f} reserves.",
    'carrier_match_metrics': {**metrics, 'coverage_lines_detected': sorted(lines), 'currency': 'CAD', 'country': 'Canada'},
    'carrier_country': 'Canada',
    'market_currency': 'CAD',
    'lossq_canada_carrier_match_version': 'LOSSQ_CANADA_CARRIER_MATCH_V1',
  })
  return result



# LOSSQ_CANADA_CARRIER_MATCH_REAL_STATS_V2
def lossq_canada_get_value_v2(obj, keys):
  if obj is None:
    return None
  for key in keys:
    try:
      if isinstance(obj, dict) and obj.get(key) not in (None, ""):
        return obj.get(key)
      if hasattr(obj, key):
        value = getattr(obj, key)
        if value not in (None, ""):
          return value
    except Exception:
      continue
  return None

def lossq_canada_money_v2(value):
  try:
    if value is None:
      return 0.0
    if isinstance(value, (int, float)):
      return float(value)
    text_value = str(value or "")
    text_value = re.sub(r"(?i)\b(?:cad|cdn|cnd|usd)\b", "", text_value)
    text_value = text_value.replace("CA$", "").replace("C$", "").replace("$", "")
    text_value = text_value.replace(",", "").replace("(", "-").replace(")", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text_value)
    return float(match.group(0)) if match else 0.0
  except Exception:
    return 0.0

def lossq_canada_parse_policy_rows_v2(value):
  rows = []
  if isinstance(value, list):
    rows.extend(value)
  elif isinstance(value, str) and value.strip():
    try:
      import json
      parsed = json.loads(value)
      if isinstance(parsed, list):
        rows.extend(parsed)
    except Exception:
      pass
  return rows

def lossq_canada_line_key_v2(value):
  text_value = str(value or "").strip().lower()
  compact = re.sub(r"[^a-z0-9]+", "", text_value)

  if compact in {"cgl", "commercialgeneralliability", "generalliability"} or "general liability" in text_value:
    return "gl"
  if any(x in text_value for x in ["fleet", "auto", "automobile"]) or compact in {"auto", "commercialauto", "commercialautomobile"}:
    return "auto"
  if any(x in text_value for x in ["wcb", "wsib", "workers", "comp", "worksafebc", "cnesst"]):
    return "wc"
  if any(x in text_value for x in ["errors", "omissions", "e&o", "professional"]):
    return "professional"
  if "cyber" in text_value:
    return "cyber"
  if any(x in text_value for x in ["umbrella", "excess"]):
    return "umbrella"
  if "property" in text_value or "bop" in text_value:
    return "property"
  if "cargo" in text_value or "transit" in text_value:
    return "cargo"
  return ""

def lossq_canada_line_label_v2(line_key):
  labels = {
    "gl": "General Liability",
    "auto": "Commercial Auto",
    "wc": "Workers Compensation",
    "professional": "Professional Liability",
    "cyber": "Cyber",
    "umbrella": "Umbrella / Excess",
    "property": "Property / Package",
    "cargo": "Cargo / Inland Marine",
  }
  return labels.get(line_key, line_key)

def lossq_canada_collect_lines_v2(profile_data=None, claims=None, result=None):
  lines = set()

  if isinstance(profile_data, dict):
    for key in ["line_of_business", "primary_line_of_business", "coverage", "policy_type"]:
      line_key = lossq_canada_line_key_v2(profile_data.get(key))
      if line_key:
        lines.add(line_key)

    for schedule_key in ["policies", "policy_schedule", "policySchedule"]:
      for row in lossq_canada_parse_policy_rows_v2(profile_data.get(schedule_key)):
        if isinstance(row, dict):
          line_key = lossq_canada_line_key_v2(
            row.get("line_of_business")
            or row.get("coverage")
            or row.get("policy_type")
            or row.get("line")
            or row.get("lob")
          )
          if line_key:
            lines.add(line_key)

  if isinstance(result, dict):
    metrics = result.get("carrier_match_metrics") or result.get("appetite_metrics") or {}
    detected = metrics.get("coverage_lines_detected") or metrics.get("lines") or []
    if isinstance(detected, str):
      detected = [detected]
    if isinstance(detected, list):
      for value in detected:
        line_key = lossq_canada_line_key_v2(value)
        if line_key:
          lines.add(line_key)

  if isinstance(claims, list):
    for claim in claims:
      value = lossq_canada_get_value_v2(claim, [
        "line_of_business",
        "claim_type",
        "coverage",
        "policy_type",
        "lob",
        "line",
      ])
      line_key = lossq_canada_line_key_v2(value)
      if line_key:
        lines.add(line_key)

  return lines

def lossq_canada_collect_metrics_v2(result=None, claims=None):
  metrics = {}
  if isinstance(result, dict):
    metrics.update(result.get("carrier_match_metrics") or {})
    metrics.update(result.get("appetite_metrics") or {})

  total_claims = 0
  open_claims = 0
  total_incurred = 0.0
  total_reserve = 0.0
  litigation_claims = 0

  if isinstance(claims, list):
    for claim in claims:
      total_claims += 1

      status = str(lossq_canada_get_value_v2(claim, ["status", "claim_status", "claimStatus"]) or "").lower()
      reserve = lossq_canada_money_v2(lossq_canada_get_value_v2(claim, ["reserve_amount", "reserve", "reserves"]))
      paid = lossq_canada_money_v2(lossq_canada_get_value_v2(claim, ["paid_amount", "paid", "paid_loss"]))
      incurred = lossq_canada_money_v2(lossq_canada_get_value_v2(claim, ["total_incurred", "incurred", "total", "total_amount"]))

      if incurred <= 0 and (paid or reserve):
        incurred = paid + reserve

      if "open" in status or reserve > 0:
        open_claims += 1

      total_incurred += incurred
      total_reserve += reserve

      attorney_flag = lossq_canada_get_value_v2(claim, [
        "attorney_assigned",
        "attorney_involved",
        "litigation",
        "litigation_flag",
        "suit_filed",
      ])
      attorney_text = str(attorney_flag or "").lower()
      if attorney_flag is True or attorney_text in {"true", "yes", "y", "1"}:
        litigation_claims += 1

  if total_claims == 0:
    total_claims = int(metrics.get("total_claims") or 0)
  if open_claims == 0:
    open_claims = int(metrics.get("open_claims") or 0)
  if total_incurred == 0:
    total_incurred = lossq_canada_money_v2(metrics.get("total_incurred"))
  if total_reserve == 0:
    total_reserve = lossq_canada_money_v2(metrics.get("total_reserve"))
  if litigation_claims == 0:
    litigation_claims = int(metrics.get("litigation_claims") or 0)

  return {
    **metrics,
    "total_claims": total_claims,
    "open_claims": open_claims,
    "total_incurred": total_incurred,
    "total_reserve": total_reserve,
    "litigation_claims": litigation_claims,
  }

def lossq_apply_canada_carrier_match_real_stats_v2(result, profile_data=None, claims=None):
  result = dict(result or {})

  if not callable(globals().get("lossq_canada_market_is_account_v1")):
    return result

  if not lossq_canada_market_is_account_v1(profile_data, claims):
    return result

  metrics = lossq_canada_collect_metrics_v2(result, claims)
  lines = lossq_canada_collect_lines_v2(profile_data, claims, result) or {"gl"}

  total_claims = int(metrics.get("total_claims") or 0)
  open_claims = int(metrics.get("open_claims") or 0)
  litigation_claims = int(metrics.get("litigation_claims") or 0)
  total_incurred = float(metrics.get("total_incurred") or 0)
  total_reserve = float(metrics.get("total_reserve") or 0)

  directory = [
    {"carrier": "Intact Insurance", "lines": {"gl", "property", "auto", "umbrella"}, "base": 82, "category": "Canadian standard commercial / middle market"},
    {"carrier": "Aviva Canada", "lines": {"gl", "property", "auto", "umbrella"}, "base": 79, "category": "Canadian commercial package"},
    {"carrier": "Northbridge Insurance", "lines": {"gl", "auto", "cargo", "property"}, "base": 78, "category": "Canadian commercial specialty"},
    {"carrier": "Zurich Canada", "lines": {"gl", "property", "professional", "cyber", "umbrella"}, "base": 77, "category": "Canadian middle market / specialty"},
    {"carrier": "CNA Canada", "lines": {"gl", "professional", "cyber", "property"}, "base": 75, "category": "Canadian casualty / professional"},
    {"carrier": "Chubb Canada", "lines": {"property", "professional", "cyber", "umbrella"}, "base": 74, "category": "Canadian specialty / executive risk"},
    {"carrier": "Lloyd’s Canada", "lines": {"professional", "cyber", "umbrella", "property"}, "base": 73, "category": "Canadian specialty market"},
    {"carrier": "Definity / Economical Insurance", "lines": {"gl", "auto", "property"}, "base": 72, "category": "Canadian regional commercial"},
    {"carrier": "Wawanesa Commercial", "lines": {"gl", "auto", "property"}, "base": 70, "category": "Canadian regional commercial"},
  ]

  matches = []
  readable_lines = [lossq_canada_line_label_v2(line) for line in sorted(lines)]

  for market in directory:
    overlap = lines.intersection(market["lines"])
    if not overlap:
      continue

    score = market["base"] + len(overlap) * 4
    score -= min(open_claims * 3, 12)
    score -= min(litigation_claims * 4, 12)

    if total_incurred >= 250000:
      score -= 15
    elif total_incurred >= 100000:
      score -= 8
    elif total_incurred >= 50000:
      score -= 4

    if total_reserve >= 100000:
      score -= 8
    elif total_reserve >= 50000:
      score -= 5

    score = max(0, min(100, int(score)))

    overlap_labels = [lossq_canada_line_label_v2(line) for line in sorted(overlap)]
    reason = (
      f"{market['carrier']}: Canada-market fit for {', '.join(overlap_labels)}. "
      f"Account lines reviewed: {', '.join(readable_lines)}. "
      f"Reviewed {total_claims} claim(s), {open_claims} open claim(s), "
      f"{litigation_claims} attorney/litigation indicator(s), "
      f"CAD ${total_incurred:,.0f} incurred, and CAD ${total_reserve:,.0f} reserves."
    )

    matches.append({
      "carrier": market["carrier"],
      "group": market["carrier"],
      "match_score": score,
      "score": score,
      "market_category": market["category"],
      "reason": reason,
      "match_reason": reason,
      "country": "Canada",
      "currency": "CAD",
      "matched_lines": overlap_labels,
      "account_lines_reviewed": readable_lines,
    })

  matches = sorted(matches, key=lambda row: row.get("match_score", 0), reverse=True)

  if not matches:
    return result

  recommended = matches[0]

  result.update({
    "top_carriers": matches[:5],
    "recommended_carrier": recommended.get("carrier"),
    "recommended_score": recommended.get("match_score"),
    "recommended_market_category": recommended.get("market_category"),
    "carrier_match_reasons": [row.get("reason") for row in matches[:5]],
    "carrier_match_summary": (
      f"LossQ recommends {recommended.get('carrier')} with a {recommended.get('match_score')}/100 Canada-market match. "
      f"The ranking used Canadian jurisdiction/currency signals, account lines {', '.join(readable_lines)}, "
      f"{total_claims} claim(s), {open_claims} open claim(s), {litigation_claims} attorney/litigation indicator(s), "
      f"CAD ${total_incurred:,.0f} incurred, and CAD ${total_reserve:,.0f} reserves."
    ),
    "carrier_match_metrics": {
      **metrics,
      "coverage_lines_detected": readable_lines,
      "coverage_line_keys_detected": sorted(lines),
      "currency": "CAD",
      "country": "Canada",
    },
    "carrier_country": "Canada",
    "market_currency": "CAD",
    "lossq_canada_carrier_match_version": "LOSSQ_CANADA_CARRIER_MATCH_REAL_STATS_V2",
  })

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
def renewal_decision(policy_number: str | None = Query(default=None), db: Session = Depends(get_db), current_user: dict = Depends(require_package_access)):
  result = engine_response(build_underwriter_decision_engine, db, current_user, policy_number)
  claims, policy_numbers_used, profile_data = get_claims_for_account(db, current_user, policy_number)
  profile_data = lossq_best_exposure_profile(result, profile_data)
  profile_data = lossq_full_profile_for_exposure(db, current_user, policy_number, result, profile_data)
  result["account_profile"] = profile_data
  result = lossq_apply_exposure_to_decision(result, profile_data, claims)
  result["policy_numbers_used"] = policy_numbers_used
  result = lossq_force_exposure_from_result_profile(result)
  # LOSSQ_CANADA_CARRIER_MATCH_CALL_V1
  result = lossq_apply_canada_carrier_match_v1(result, profile_data, claims)
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
def carrier_appetite(policy_number: str | None = Query(default=None), db: Session = Depends(get_db), current_user: dict = Depends(require_package_access)):
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
  # LOSSQ_CANADA_CARRIER_APPETITE_CALL_V1
  result = lossq_apply_canada_carrier_appetite_v1(result, profile_data, claims, policy_numbers_used, policy_number)
  return result



# LOSSQ_UNDERWRITER_SUBMISSION_READINESS_V2
def lossq_submission_claim_value_v2(claim, *names):
  if isinstance(claim, dict):
    for name in names:
      if claim.get(name) not in (None, ""):
        return claim.get(name)
    return ""

  for name in names:
    value = getattr(claim, name, None)
    if value not in (None, ""):
      return value

  return ""


def lossq_submission_clean_v2(value):
  import re
  return re.sub(r"\s+", " ", str(value or "").replace("\ufeff", "").strip())


def lossq_submission_money_v2(value):
  import re

  raw = lossq_submission_clean_v2(value)
  if not raw:
    return 0.0

  if isinstance(value, (int, float)):
    return float(value)

  neg = raw.startswith("(") and raw.endswith(")")
  raw = raw.replace("$", "").replace(",", "").replace("(", "").replace(")", "")
  raw = re.sub(r"[^0-9.\-]+", "", raw)

  try:
    amount = float(raw or 0)
    return -amount if neg else amount
  except Exception:
    return 0.0


def lossq_submission_is_open_v2(claim):
  status = lossq_submission_clean_v2(lossq_submission_claim_value_v2(claim, "status", "claim_status")).lower()
  return status in {"open", "opened", "reopened", "pending", "reported"}


def lossq_submission_is_litigated_v2(claim):
  raw = lossq_submission_clean_v2(lossq_submission_claim_value_v2(claim, "litigation", "litigated", "attorney_involved", "suit")).lower()
  return raw in {"true", "yes", "y", "1", "litigated", "attorney", "suit", "counsel assigned"}


def lossq_submission_line_v2(claim):
  return lossq_submission_clean_v2(
    lossq_submission_claim_value_v2(
      claim,
      "line_of_business",
      "claim_type",
      "coverage",
      "policy_type",
      "lob",
    )
  ) or "Unspecified Line"


def lossq_submission_claim_number_v2(claim):
  return lossq_submission_clean_v2(
    lossq_submission_claim_value_v2(claim, "claim_number", "Claim Number", "claim_no", "claim_id")
  ) or "Unnumbered Claim"


def lossq_submission_policy_number_v2(claim):
  return lossq_submission_clean_v2(
    lossq_submission_claim_value_v2(claim, "policy_number", "Policy Number", "policy_no", "policy")
  )


def lossq_submission_description_v2(claim):
  return lossq_submission_clean_v2(
    lossq_submission_claim_value_v2(claim, "description", "claim_description", "cause_of_loss", "cause")
  )


def lossq_claim_specific_requirements_v2(claim):
  line = lossq_submission_line_v2(claim)
  line_key = line.lower()
  status = "Open" if lossq_submission_is_open_v2(claim) else "Closed"
  claim_number = lossq_submission_claim_number_v2(claim)
  paid = lossq_submission_money_v2(lossq_submission_claim_value_v2(claim, "paid_amount", "total_paid", "paid"))
  reserve = lossq_submission_money_v2(lossq_submission_claim_value_v2(claim, "reserve_amount", "total_reserve", "reserve"))
  incurred = lossq_submission_money_v2(lossq_submission_claim_value_v2(claim, "total_incurred", "gross_incurred", "net_incurred", "incurred"))
  if incurred <= 0 and (paid or reserve):
    incurred = paid + reserve

  needs = []
  why = []

  if status == "Open":
    needs.extend([
      "current adjuster status",
      "reserve rationale",
      "expected closure or next review date",
      "confirmation of litigation or counsel involvement",
    ])
    why.append("open reserves create uncertainty until the adjuster explains the current posture")

  if reserve > 0:
    needs.append("carrier or adjuster reserve comments")
    why.append("the remaining reserve may still develop before renewal")

  if incurred >= 50000 or reserve >= 25000:
    needs.extend([
      "large-loss narrative",
      "cause of loss",
      "corrective action taken",
      "why recurrence risk has been reduced",
    ])
    why.append("severity will drive underwriter questions even if the claim is not the most frequent loss type")

  if lossq_submission_is_litigated_v2(claim):
    needs.extend([
      "defense counsel status",
      "venue and litigation milestone",
      "settlement posture",
    ])
    why.append("litigation changes claim volatility and market appetite")

  if "workers" in line_key or line_key == "wc":
    needs.extend([
      "return-to-work status",
      "medical-only versus indemnity detail",
      "lost-time status",
      "safety training or job-duty correction",
    ])
  elif "liquor" in line_key:
    needs.extend([
      "incident report",
      "alcohol-service training records",
      "security or ID-check controls",
      "post-loss corrective action for alcohol service",
    ])
  elif "general" in line_key or line_key == "gl":
    needs.extend([
      "premises condition or negligence explanation",
      "photos or maintenance records if applicable",
      "corrective action for the hazard or operation involved",
    ])
  elif "auto" in line_key:
    needs.extend([
      "driver involved",
      "fault determination",
      "MVR or driver safety action",
      "telematics or retraining detail if applicable",
    ])
  elif "cargo" in line_key:
    needs.extend([
      "commodity involved",
      "route and custody detail",
      "packaging, loading, theft, or security controls",
    ])
  elif "property" in line_key or "bop" in line_key or "businessowner" in line_key:
    needs.extend([
      "repair status",
      "photos or invoices",
      "mitigation steps",
      "fire, water, theft, or equipment-control correction",
    ])
  elif "cyber" in line_key:
    needs.extend([
      "incident vector",
      "containment timeline",
      "MFA/back-up/security-control changes",
      "breach notification status if applicable",
    ])

  if not lossq_submission_description_v2(claim):
    needs.append("plain-English description of what happened")

  if status == "Closed":
    needs.extend([
      "final paid confirmation",
      "confirmation no reserve remains",
    ])
    if incurred >= 25000:
      needs.append("corrective action narrative despite closure")

  # De-duplicate while preserving order.
  needs = list(dict.fromkeys([item for item in needs if item]))
  why = list(dict.fromkeys([item for item in why if item]))

  if not needs:
    needs = ["standard claim documentation and confirmation no unusual development is expected"]

  if not why:
    why = ["underwriters need to know whether this is isolated, corrected, and unlikely to recur"]

  return {
    "claim_number": claim_number,
    "policy_number": lossq_submission_policy_number_v2(claim),
    "line_of_business": line,
    "status": status,
    "paid": paid,
    "reserve": reserve,
    "total_incurred": incurred,
    "needed": needs,
    "why_it_matters": why,
    "summary": (
      f"{claim_number} is a {status.lower()} {line} claim with ${incurred:,.0f} total incurred "
      f"and ${reserve:,.0f} in reserve. Before this submission is carrier-ready, provide "
      f"{', '.join(needs[:5])}."
    ),
  }


def lossq_underwriter_submission_readiness_v2(policy_number, claims, policy_numbers_used, profile_data, quality, decision):
  profile_data = profile_data if isinstance(profile_data, dict) else {}
  claims = claims if isinstance(claims, list) else []

  total_claims = len(claims)
  open_claims = sum(1 for claim in claims if lossq_submission_is_open_v2(claim))
  litigated_claims = sum(1 for claim in claims if lossq_submission_is_litigated_v2(claim))
  total_incurred = sum(
    lossq_submission_money_v2(lossq_submission_claim_value_v2(claim, "total_incurred", "gross_incurred", "net_incurred", "incurred"))
    for claim in claims
  )
  total_reserve = sum(
    lossq_submission_money_v2(lossq_submission_claim_value_v2(claim, "reserve_amount", "total_reserve", "reserve"))
    for claim in claims
  )

  score = 100
  score_deductions = []
  to_reach_100 = []

  def deduct(points, reason, fix):
    nonlocal score
    points = int(points or 0)
    if points <= 0:
      return
    score -= points
    score_deductions.append(f"-{points}: {reason} Fix: {fix}")
    to_reach_100.append(fix)

  if not profile_data.get("business_name"):
    deduct(8, "Named insured was not confirmed.", "Add or correct the named insured/account name.")

  if not (profile_data.get("carrier_name") or profile_data.get("writing_carrier") or profile_data.get("carrier")):
    deduct(6, "Writing carrier was not confirmed.", "Add the writing carrier or carrier shown on the loss run.")

  if not (profile_data.get("effective_date") or profile_data.get("policy_effective_date")):
    deduct(5, "Policy effective date is missing.", "Add the policy effective date.")
  if not (profile_data.get("expiration_date") or profile_data.get("policy_expiration_date")):
    deduct(5, "Policy expiration date is missing.", "Add the policy expiration date.")

  if not (profile_data.get("evaluation_date") or profile_data.get("valuation_date") or profile_data.get("loss_run_date")):
    deduct(8, "Loss run valuation/evaluation date is missing.", "Upload or enter currently valued loss runs with valuation date shown.")

  if not (profile_data.get("policies") or profile_data.get("policy_schedule") or policy_numbers_used):
    deduct(10, "Policy schedule was not confirmed.", "Add the policy schedule with policy numbers, lines of business, effective dates, expiration dates, and premiums.")

  exposure_fields = [
    ("revenue", "annual revenue"),
    ("payroll", "payroll"),
    ("employee_count", "employee count"),
    ("vehicle_count", "vehicle count"),
    ("current_premium", "current premium"),
  ]
  missing_exposures = [label for field, label in exposure_fields if not profile_data.get(field)]
  if missing_exposures:
    deduct(
      min(18, 4 * len(missing_exposures)),
      "Exposure inputs are incomplete: " + ", ".join(missing_exposures) + ".",
      "Complete exposure inputs so the underwriter can evaluate claim frequency against the correct exposure base.",
    )

  if open_claims:
    deduct(
      min(20, open_claims * 5),
      f"{open_claims} open claim(s) require current status and reserve support.",
      "Provide adjuster status, reserve basis, litigation/counsel status, and expected closure or next review date for each open claim.",
    )

  if litigated_claims:
    deduct(
      min(15, litigated_claims * 5),
      f"{litigated_claims} litigated claim(s) require legal posture.",
      "Attach litigation notes with counsel, venue, settlement posture, and next milestone.",
    )

  large_claims = []
  missing_descriptions = []
  for claim in claims:
    incurred = lossq_submission_money_v2(lossq_submission_claim_value_v2(claim, "total_incurred", "gross_incurred", "net_incurred", "incurred"))
    reserve = lossq_submission_money_v2(lossq_submission_claim_value_v2(claim, "reserve_amount", "total_reserve", "reserve"))
    if incurred >= 50000 or reserve >= 25000:
      large_claims.append(claim)
    if not lossq_submission_description_v2(claim):
      missing_descriptions.append(claim)

  if large_claims:
    deduct(
      min(15, len(large_claims) * 4),
      f"{len(large_claims)} severe or high-reserve claim(s) need large-loss explanation.",
      "Add a large-loss narrative explaining cause, severity, corrective action, and why recurrence risk is reduced.",
    )

  if missing_descriptions:
    deduct(
      min(10, len(missing_descriptions) * 2),
      f"{len(missing_descriptions)} claim(s) are missing plain-English descriptions.",
      "Add a short claim description or cause of loss for each claim without narrative detail.",
    )

  if not (profile_data.get("underwriter_notes") or profile_data.get("loss_control_plan") or profile_data.get("safety_plan")):
    deduct(
      6,
      "No underwriting notes or loss-control narrative is attached.",
      "Add a brief broker narrative explaining operations, claim controls, corrective actions, and why the account is ready for market.",
    )

  score = max(0, min(100, int(score)))
  level = "Excellent" if score >= 90 else "Market Ready" if score >= 80 else "Ready With Conditions" if score >= 70 else "Needs Broker Cleanup" if score >= 50 else "Not Ready"
  carrier_confidence = "High" if score >= 80 else "Moderate" if score >= 60 else "Low"

  claim_reviews = [lossq_claim_specific_requirements_v2(claim) for claim in claims]
  claim_reviews.sort(key=lambda item: (item.get("status") != "Open", -(item.get("total_incurred") or 0), -(item.get("reserve") or 0)))

  claim_readiness_items = [item["summary"] for item in claim_reviews[:12]]

  required_documents = [
    "Currently valued loss runs with valuation/evaluation date shown",
    "Policy schedule with policy numbers, lines of business, effective dates, expiration dates, and premiums",
    "Exposure basis detail: revenue, payroll, employees, vehicles, locations, limits, and current premium where applicable",
    "Open-claim status notes with reserve basis and expected closure or next review date",
    "Large-loss narratives with cause, corrective action, and recurrence-control explanation",
    "Line-specific supplementals or confirmation they are not applicable",
    "Producer/agency contact and final branded carrier packet",
  ]

  if not to_reach_100:
    to_reach_100 = [
      "Maintain current valuation date, complete exposure inputs, and keep claim notes updated before final carrier release."
    ]

  decision_concerns = decision.get("underwriting_concerns", []) if isinstance(decision, dict) else []
  missing_items = list(dict.fromkeys(
    [item.split(" Fix: ")[0] for item in score_deductions]
    + [str(item) for item in decision_concerns if item]
  ))

  account_name = (
    profile_data.get("business_name")
    or profile_data.get("named_insured")
    or profile_data.get("account_name")
    or "this account"
  )

  underwriter_readiness_narrative = (
    f"{account_name} is rated {level} at {score}/100. The file includes {total_claims} validated claim(s), "
    f"{open_claims} open claim(s), ${total_incurred:,.0f} total incurred, and ${total_reserve:,.0f} remaining reserves. "
    f"The submission will look stronger to an underwriter once the broker resolves the specific readiness gaps: "
    f"{' '.join(to_reach_100[:4])}"
  )

  if claim_readiness_items:
    underwriter_readiness_narrative += (
      " The claim review should lead with the open or highest-reserve claims first, because those are the items most likely to slow quoting."
    )

  return {
    "policy_number": policy_number,
    "is_credible": True,
    "claims_used": len(claims),
    "policy_numbers_used": policy_numbers_used,
    "submission_readiness_score": score,
    "readiness_score": score,
    "submission_readiness_level": level,
    "carrier_confidence": carrier_confidence,
    "submission_quality": level,
    "missing_items": missing_items or ["No material missing items identified."],
    "required_documents": required_documents,
    "recommended_actions": to_reach_100[:10],
    "to_reach_100": list(dict.fromkeys(to_reach_100)),
    "score_deductions": score_deductions or ["No score deductions. Maintain current loss runs, exposures, and claim narratives."],
    "claim_readiness_items": claim_readiness_items or ["No claim-level follow-up required beyond standard documentation."],
    "claim_underwriter_reviews": claim_reviews,
    "underwriter_readiness_narrative": underwriter_readiness_narrative,
    "readiness_summary": underwriter_readiness_narrative,
    "readiness_metrics": {
      "total_claims": total_claims,
      "open_claims": open_claims,
      "litigated_claims": litigated_claims,
      "total_incurred": total_incurred,
      "total_reserve": total_reserve,
    },
  }


@router.get("/submission-readiness")
def submission_readiness(policy_number: str | None = Query(default=None), db: Session = Depends(get_db), current_user: dict = Depends(require_package_access)):
  claims, policy_numbers_used, profile_data = get_claims_for_account(db, current_user, policy_number)
  quality = data_quality(claims, policy_numbers_used, profile_data)

  if not quality["is_credible"]:
    return {
      **insufficient_response(policy_number, "submission-readiness"),
      "submission_readiness_score": None,
      "readiness_score": None,
      "submission_readiness_level": "Insufficient Data",
      "missing_items": quality["issues"],
      "required_documents": ["Validated policy schedule", "Parsed claim rows", "Currently valued loss runs"],
      "recommended_actions": ["Correct or upload credible loss data before releasing to markets."],
      "to_reach_100": ["Upload validated claim rows, policy schedule, and currently valued loss runs before marketing."],
      "score_deductions": ["Insufficient data: LossQ cannot score readiness until claim and policy data are credible."],
      "claim_readiness_items": [],
      "claim_underwriter_reviews": [],
      "underwriter_readiness_narrative": "Submission readiness cannot be rated until validated loss data is available.",
      "readiness_summary": "Submission readiness cannot be rated until validated loss data is available.",
      "claims_used": len(claims),
      "policy_numbers_used": policy_numbers_used,
    }

  decision = build_underwriter_decision_engine(claims, policy_number)

  return lossq_underwriter_submission_readiness_v2(
    policy_number,
    claims,
    policy_numbers_used,
    profile_data,
    quality,
    decision,
  )


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
def premium_forecast(policy_number: str | None = Query(default=None), db: Session = Depends(get_db), current_user: dict = Depends(require_package_access)):
  result = engine_response(build_premium_forecast_engine, db, current_user, policy_number)
  claims, policy_numbers_used, profile_data = get_claims_for_account(db, current_user, policy_number)
  profile_data = lossq_best_exposure_profile(result, profile_data)
  profile_data = lossq_full_profile_for_exposure(db, current_user, policy_number, result, profile_data)
  result["account_profile"] = profile_data
  result = lossq_apply_exposure_to_premium_forecast(result, profile_data, claims)
  result["policy_numbers_used"] = policy_numbers_used
  return result

@router.get("/carrier-match")
def carrier_match(policy_number: str | None = Query(default=None), db: Session = Depends(get_db), current_user: dict = Depends(require_package_access)):
  result = engine_response(build_carrier_match_engine, db, current_user, policy_number)
  claims, policy_numbers_used, profile_data = get_claims_for_account(db, current_user, policy_number)
  profile_data = lossq_best_exposure_profile(result, profile_data)
  profile_data = lossq_full_profile_for_exposure(db, current_user, policy_number, result, profile_data)
  result["account_profile"] = profile_data
  result = lossq_apply_exposure_to_carrier_match(result, profile_data, claims)
  result["policy_numbers_used"] = policy_numbers_used
  result = lossq_force_exposure_from_result_profile(result)
  # LOSSQ_CANADA_CARRIER_MATCH_ENDPOINT_OVERRIDE_V2
  # Carrier Match must use Canada markets after exposure rerank/force logic.
  if callable(globals().get("lossq_apply_canada_carrier_match_v1")):
    result = lossq_apply_canada_carrier_match_v1(result, profile_data, claims)
    result["lossq_canada_carrier_match_endpoint_version"] = "LOSSQ_CANADA_CARRIER_MATCH_ENDPOINT_OVERRIDE_V2"
  elif callable(globals().get("lossq_canada_carrier_match_v1")):
    result = lossq_canada_carrier_match_v1(result, profile_data, claims)
    result["lossq_canada_carrier_match_endpoint_version"] = "LOSSQ_CANADA_CARRIER_MATCH_ENDPOINT_OVERRIDE_V2"
  # LOSSQ_CANADA_CARRIER_MATCH_REAL_STATS_CALL_V2
  result = lossq_apply_canada_carrier_match_real_stats_v2(result, profile_data, claims)
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
def renewal_memo(policy_number: str | None = Query(default=None), db: Session = Depends(get_db), current_user: dict = Depends(require_package_access)):
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
