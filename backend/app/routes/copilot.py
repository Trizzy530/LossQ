import os
from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import SessionLocal
from app.models.claim import Claim
from app.models.account_profile import AccountProfile
from app.auth_utils import get_current_user
from app.routes.summary import build_underwriting_intelligence

load_dotenv()

router = APIRouter(prefix="/copilot", tags=["Copilot"])


class CopilotRequest(BaseModel):
    question: str
    policy_number: str | None = None
    account_number: str | None = None
    profile_id: int | None = None
    policy_numbers: list[str] | None = None
    visible_claims: list[dict] | None = None
    profile: dict | None = None


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def build_claim_context(claims):
    lines = []

    for claim in claims[:75]:
        lines.append(
            f"Claim {claim.claim_number}: "
            f"Policy={claim.policy_number}, "
            f"LOB={claim.line_of_business}, "
            f"Status={claim.status}, "
            f"Paid=${float(claim.paid_amount or 0):,.2f}, "
            f"Reserve=${float(claim.reserve_amount or 0):,.2f}, "
            f"Total=${float(claim.total_incurred or 0):,.2f}, "
            f"Litigation={claim.litigation}, "
            f"Flag={claim.flag}, "
            f"Description={claim.description}"
        )

    return "\n".join(lines)


def fallback_answer(question, claims, intelligence, policy_number):
    question_lower = question.lower()

    total_claims = len(claims)
    open_claims = len([c for c in claims if c.status == "Open"])
    litigation_claims = len([c for c in claims if c.litigation])

    top_claims = sorted(
        claims,
        key=lambda c: float(c.total_incurred or 0),
        reverse=True,
    )[:3]

    top_claim_text = ", ".join(
        [
            f"{c.claim_number} (${float(c.total_incurred or 0):,.2f})"
            for c in top_claims
        ]
    )

    policy_text = f" for policy {policy_number}" if policy_number else ""

    if total_claims == 0:
        return (
            f"I do not see any claims loaded{policy_text}. "
            f"Upload a loss run under the selected policy first, then I can analyze renewal concerns, severity drivers, litigation exposure, and broker strategy."
        )

    if "renewal" in question_lower or "concern" in question_lower:
        return (
            f"For this selected account{policy_text}, the biggest renewal concerns are "
            f"{open_claims} open claim(s), {litigation_claims} litigation-related claim(s), "
            f"and total incurred exposure of ${intelligence['metrics']['total_incurred']:,.2f}. "
            f"The account is currently rated {intelligence['renewal_risk']} for renewal risk."
        )

    if "severity" in question_lower or "driving" in question_lower:
        return (
            f"For this selected account{policy_text}, the claims driving severity are: "
            f"{top_claim_text or 'none identified'}. "
            f"These should be reviewed first because they represent the largest incurred exposure."
        )

    if "litigation" in question_lower:
        return (
            f"For this selected account{policy_text}, there are {litigation_claims} litigation-related claim(s). "
            f"The broker should provide claim narratives, defense counsel updates, current reserves, "
            f"and expected resolution timing."
        )

    if "carrier" in question_lower or "explain" in question_lower or "submission" in question_lower:
        return intelligence["carrier_narrative"]

    return (
        f"For this selected account{policy_text}, there are {total_claims} claim(s), "
        f"{open_claims} open claim(s), and a {intelligence['risk_level']} risk level. "
        f"Recommended action: {intelligence['recommendation']}"
    )




# LOSSQ_COPILOT_ACCOUNT_POLICY_SET_V1
def lossq_copilot_norm(value):
    return str(value or "").strip().upper()


def lossq_copilot_profile_policy_numbers(profile):
    numbers = []

    if isinstance(profile, dict):
        for key in ["policy_number", "account_number", "customer_number"]:
            value = lossq_copilot_norm(profile.get(key))
            if value:
                numbers.append(value)

        for row in profile.get("policies") or profile.get("policy_schedule") or []:
            if isinstance(row, dict):
                value = lossq_copilot_norm(row.get("policy_number") or row.get("policy"))
                if value:
                    numbers.append(value)

    return list(dict.fromkeys([n for n in numbers if n]))


def lossq_copilot_find_profile(db, current_user, request):
    org_id = current_user.get("organization_id")
    if not org_id:
        return None

    if getattr(request, "profile_id", None):
        try:
            profile = (
                db.query(AccountProfile)
                .filter(AccountProfile.organization_id == org_id)
                .filter(AccountProfile.id == int(request.profile_id))
                .first()
            )
            if profile:
                return profile
        except Exception:
            pass

    selected_keys = [
        lossq_copilot_norm(getattr(request, "policy_number", None)),
        lossq_copilot_norm(getattr(request, "account_number", None)),
    ]

    selected_keys = [item for item in selected_keys if item]

    if not selected_keys:
        return None

    profiles = (
        db.query(AccountProfile)
        .filter(AccountProfile.organization_id == org_id)
        .order_by(AccountProfile.id.desc())
        .all()
    )

    for profile in profiles:
        profile_dict = {
            "policy_number": getattr(profile, "policy_number", None),
            "account_number": getattr(profile, "account_number", None),
            "customer_number": getattr(profile, "customer_number", None),
            "policies": getattr(profile, "policies", None) or [],
        }

        profile_numbers = lossq_copilot_profile_policy_numbers(profile_dict)

        if any(key in profile_numbers for key in selected_keys):
            return profile

    return None


def lossq_copilot_resolve_policy_numbers(db, current_user, request):
    numbers = []

    for value in getattr(request, "policy_numbers", None) or []:
        normalized = lossq_copilot_norm(value)
        if normalized:
            numbers.append(normalized)

    for value in [
        getattr(request, "policy_number", None),
        getattr(request, "account_number", None),
    ]:
        normalized = lossq_copilot_norm(value)
        if normalized:
            numbers.append(normalized)

    if isinstance(getattr(request, "profile", None), dict):
        numbers.extend(lossq_copilot_profile_policy_numbers(request.profile))

    saved_profile = lossq_copilot_find_profile(db, current_user, request)
    if saved_profile:
        saved_profile_dict = {
            "policy_number": getattr(saved_profile, "policy_number", None),
            "account_number": getattr(saved_profile, "account_number", None),
            "customer_number": getattr(saved_profile, "customer_number", None),
            "policies": getattr(saved_profile, "policies", None) or [],
        }
        numbers.extend(lossq_copilot_profile_policy_numbers(saved_profile_dict))

    # Only use real policy numbers for claim filtering. Account numbers are kept for display only.
    real_policy_numbers = [
        item for item in list(dict.fromkeys(numbers))
        if item and item not in {"-", "NOT SET", "POLICY NOT SET"} and ("-" in item)
    ]

    return real_policy_numbers


def lossq_copilot_visible_claim_objects(request):
    rows = getattr(request, "visible_claims", None) or []
    claim_objs = []

    class VisibleClaim:
        pass

    for row in rows:
        if not isinstance(row, dict):
            continue

        obj = VisibleClaim()
        for key, value in row.items():
            setattr(obj, key, value)

        # normalize common frontend keys
        if not hasattr(obj, "paid_amount"):
            setattr(obj, "paid_amount", row.get("paid") or row.get("paid_amount") or 0)
        if not hasattr(obj, "reserve_amount"):
            setattr(obj, "reserve_amount", row.get("reserve") or row.get("reserve_amount") or 0)
        if not hasattr(obj, "total_incurred"):
            setattr(obj, "total_incurred", row.get("total") or row.get("incurred") or row.get("total_incurred") or 0)

        claim_objs.append(obj)

    return claim_objs



@router.post("/ask")
def ask_copilot(
    request: CopilotRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # LOSSQ_COPILOT_ACCOUNT_AWARE_CLAIM_QUERY_V1
    policy_numbers = lossq_copilot_resolve_policy_numbers(db, current_user, request)

    query = db.query(Claim).filter(
        Claim.organization_id == current_user["organization_id"]
    )

    if policy_numbers:
        query = query.filter(func.upper(func.trim(Claim.policy_number)).in_(policy_numbers))
        claims = query.all()
    else:
        claims = []

    # If dashboard already has the correct visible claims, use them as safe fallback.
    if not claims:
        claims = lossq_copilot_visible_claim_objects(request)

    intelligence = build_underwriting_intelligence(claims)

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        return {
            "answer": fallback_answer(
                request.question,
                claims,
                intelligence,
                request.policy_number,
            ),
            "mode": "rule_based",
            "policy_number": request.policy_number,
            "claims_used": len(claims),
            "policy_numbers_used": policy_numbers,
        }

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)

        selected_policy = request.policy_number or request.account_number or "Selected account"

        prompt = f"""
You are LossQ, an AI underwriting copilot for commercial insurance brokers.

IMPORTANT:
Only analyze the claim data provided below.
The broker is currently viewing this selected policy/account:
{selected_policy}

Do not reference claims outside this selected account.
If no claims are provided, tell the broker to upload a loss run under the selected policy.

Answer the broker's question using only the provided claim data.
Return the response in this exact structure:

SUMMARY:
Short underwriting overview.

RENEWAL_RISK:
GREEN, YELLOW, or RED with explanation.

SEVERITY_DRIVERS:
Bullet list of largest severity concerns.

LITIGATION_EXPOSURE:
Explain litigation concerns.

RESERVE_ADEQUACY:
Discuss reserve concerns.

BROKER_ACTIONS:
Bullet list of broker recommendations.

UNDERWRITER_CONCERNS:
Bullet list of likely carrier concerns.

SUBMISSION_STRATEGY:
Explain how the broker should position the account.

Current selected account intelligence:
Risk Level: {intelligence["risk_level"]}
Renewal Risk: {intelligence["renewal_risk"]}
Risk Score: {intelligence["risk_score"]}
Submission Strength: {intelligence["submission_strength"]}
Summary: {intelligence["summary"]}
Recommendation: {intelligence["recommendation"]}

Selected policy claim data:
{build_claim_context(claims)}

Broker question:
{request.question}
"""

        response = client.responses.create(
            model="gpt-5.5-mini",
            input=prompt,
        )

        return {
            "answer": response.output_text,
            "mode": "openai",
            "policy_number": request.policy_number,
            "claims_used": len(claims),
            "policy_numbers_used": policy_numbers,
        }

    except Exception:
        return {
            "answer": fallback_answer(
                request.question,
                claims,
                intelligence,
                request.policy_number,
            ),
            "mode": "rule_based_fallback",
            "policy_number": request.policy_number,
            "claims_used": len(claims),
        }

@router.post("/renewal-analysis")
def renewal_analysis(
    request: CopilotRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    query = db.query(Claim).filter(
        Claim.organization_id == current_user["organization_id"]
    )

    if request.policy_number:
        query = query.filter(
            Claim.policy_number == request.policy_number
        )

    claims = query.all()

    intelligence = build_underwriting_intelligence(claims)

    return {
        "policy_number": request.policy_number,
        "claims_used": len(claims),
        "renewal_risk": intelligence["renewal_risk"],
        "risk_score": intelligence["risk_score"],
        "summary": intelligence["summary"],
        "recommendation": intelligence["recommendation"],
        "submission_strength": intelligence["submission_strength"],
    }


@router.post("/litigation-analysis")
def litigation_analysis(
    request: CopilotRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    query = db.query(Claim).filter(
        Claim.organization_id == current_user["organization_id"]
    )

    if request.policy_number:
        query = query.filter(
            Claim.policy_number == request.policy_number
        )

    claims = query.all()

    litigation_claims = [
        c for c in claims if c.litigation
    ]

    return {
        "policy_number": request.policy_number,
        "litigation_claims": len(litigation_claims),
        "claims": [
            {
                "claim_number": c.claim_number,
                "status": c.status,
                "total_incurred": c.total_incurred,
                "description": c.description,
            }
            for c in litigation_claims
        ],
    }


@router.post("/reserve-analysis")
def reserve_analysis(
    request: CopilotRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    query = db.query(Claim).filter(
        Claim.organization_id == current_user["organization_id"]
    )

    if request.policy_number:
        query = query.filter(
            Claim.policy_number == request.policy_number
        )

    claims = query.all()

    reserve_total = sum(
        float(c.reserve_amount or 0)
        for c in claims
    )

    incurred_total = sum(
        float(c.total_incurred or 0)
        for c in claims
    )

    reserve_ratio = (
        reserve_total / incurred_total
        if incurred_total > 0
        else 0
    )

    adequacy = "Adequate"

    if reserve_ratio < 0.15:
        adequacy = "Potentially Deficient"

    elif reserve_ratio > 0.5:
        adequacy = "Conservative"

    return {
        "policy_number": request.policy_number,
        "reserve_total": reserve_total,
        "incurred_total": incurred_total,
        "reserve_ratio": reserve_ratio,
        "reserve_adequacy": adequacy,
    }


@router.post("/carrier-strategy")
def carrier_strategy(
    request: CopilotRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    query = db.query(Claim).filter(
        Claim.organization_id == current_user["organization_id"]
    )

    if request.policy_number:
        query = query.filter(
            Claim.policy_number == request.policy_number
        )

    claims = query.all()

    intelligence = build_underwriting_intelligence(claims)

    return {
        "policy_number": request.policy_number,
        "carrier_strategy": intelligence["carrier_narrative"],
        "risk_level": intelligence["risk_level"],
        "renewal_risk": intelligence["renewal_risk"],
        "submission_strength": intelligence["submission_strength"],
    }


@router.post("/broker-summary")
def broker_summary(
    request: CopilotRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    query = db.query(Claim).filter(
        Claim.organization_id == current_user["organization_id"]
    )

    if request.policy_number:
        query = query.filter(
            Claim.policy_number == request.policy_number
        )

    claims = query.all()

    intelligence = build_underwriting_intelligence(claims)

    return {
        "policy_number": request.policy_number,
        "summary": intelligence["summary"],
        "recommendation": intelligence["recommendation"],
        "risk_level": intelligence["risk_level"],
        "renewal_risk": intelligence["renewal_risk"],
    }