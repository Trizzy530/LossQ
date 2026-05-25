import os
from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.claim import Claim
from app.auth_utils import get_current_user
from app.routes.summary import build_underwriting_intelligence

load_dotenv()

router = APIRouter(prefix="/copilot", tags=["Copilot"])


class CopilotRequest(BaseModel):
    question: str
    policy_number: str | None = None


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


@router.post("/ask")
def ask_copilot(
    request: CopilotRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    query = db.query(Claim).filter(
        Claim.organization_id == current_user["organization_id"]
    )

    if request.policy_number:
        query = query.filter(Claim.policy_number == request.policy_number)

    claims = query.all()

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
        }

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)

        selected_policy = request.policy_number or "All organization claims"

        prompt = f"""
You are LossQ, an AI underwriting copilot for commercial insurance brokers.

IMPORTANT:
Only analyze the claim data provided below.
The broker is currently viewing this selected policy/account:
{selected_policy}

Do not reference claims outside this selected account.
If no claims are provided, tell the broker to upload a loss run under the selected policy.

Answer the broker's question using only the provided claim data.
Be concise, practical, and underwriting-focused.
Give clear broker actions where appropriate.

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