import re
from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.claim import Claim
from app.models.account_profile import AccountProfile
from app.auth_utils import get_current_user

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


# LOSSQ_DETAILED_ACCOUNT_AWARE_COPILOT_V1
def norm(value):
    return str(value or "").strip()


def norm_upper(value):
    return norm(value).upper()


def money(value):
    try:
        clean = re.sub(r"[^0-9.\-]", "", str(value or "0"))
        if clean in {"", "-", ".", "-."}:
            return 0.0
        return float(clean)
    except Exception:
        return 0.0


def dollars(value):
    return f"${money(value):,.0f}"


def attr(obj, *keys, default=""):
    for key in keys:
        try:
            if isinstance(obj, dict):
                value = obj.get(key)
            else:
                value = getattr(obj, key, None)
            if value not in [None, ""]:
                return value
        except Exception:
            pass
    return default


def current_org_id(current_user):
    if isinstance(current_user, dict):
        return current_user.get("organization_id")
    return getattr(current_user, "organization_id", None)


def profile_to_dict(profile):
    if not profile:
        return {}

    if isinstance(profile, dict):
        return profile

    data = {}
    for key in [
        "id",
        "business_name",
        "insured",
        "named_insured",
        "carrier_name",
        "writing_carrier",
        "account_number",
        "customer_number",
        "policy_number",
        "effective_date",
        "expiration_date",
        "evaluation_date",
        "policies",
        "policy_schedule",
    ]:
        try:
            data[key] = getattr(profile, key, None)
        except Exception:
            pass
    return data


def profile_policy_numbers(profile_like):
    profile_like = profile_to_dict(profile_like)
    numbers = []

    for key in ["policy_number", "account_number", "customer_number"]:
        value = norm_upper(profile_like.get(key))
        if value:
            numbers.append(value)

    for row in profile_like.get("policies") or profile_like.get("policy_schedule") or []:
        if isinstance(row, dict):
            value = norm_upper(row.get("policy_number") or row.get("policy"))
            if value:
                numbers.append(value)

    return list(dict.fromkeys([item for item in numbers if item]))


def find_saved_profile(db: Session, current_user, request: CopilotRequest):
    org_id = current_org_id(current_user)
    if not org_id:
        return None

    if request.profile_id:
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

    selected = [
        norm_upper(request.policy_number),
        norm_upper(request.account_number),
    ]
    selected = [item for item in selected if item]

    if not selected:
        return None

    profiles = (
        db.query(AccountProfile)
        .filter(AccountProfile.organization_id == org_id)
        .order_by(AccountProfile.id.desc())
        .all()
    )

    for profile in profiles:
        numbers = profile_policy_numbers(profile)
        if any(item in numbers for item in selected):
            return profile

    return None


def resolve_policy_numbers(db: Session, current_user, request: CopilotRequest):
    numbers = []

    for item in request.policy_numbers or []:
        value = norm_upper(item)
        if value:
            numbers.append(value)

    if isinstance(request.profile, dict):
        numbers.extend(profile_policy_numbers(request.profile))

    saved_profile = find_saved_profile(db, current_user, request)
    if saved_profile:
        numbers.extend(profile_policy_numbers(saved_profile))

    for item in [request.policy_number, request.account_number]:
        value = norm_upper(item)
        if value:
            numbers.append(value)

    numbers = list(dict.fromkeys([item for item in numbers if item]))

    # Keep real policy/account-like keys. This supports account selection plus policy schedule selection.
    return [
        item
        for item in numbers
        if item not in {"-", "NOT SET", "POLICY NOT SET", "N/A"}
    ]


def visible_claim_objects(request: CopilotRequest):
    rows = request.visible_claims or []
    output = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        output.append(row)

    return output


def claim_context_rows(claims):
    rows = []
    for claim in claims or []:
        paid = money(attr(claim, "paid_amount", "paid", "total_paid", default=0))
        reserve = money(attr(claim, "reserve_amount", "reserve", "outstanding_reserve", default=0))
        total = money(attr(claim, "total_incurred", "incurred", "total", default=0))

        rows.append(
            {
                "claim_number": norm(attr(claim, "claim_number", "claimNumber", "claim_no", default="-")),
                "policy_number": norm(attr(claim, "policy_number", "policyNumber", "policy", default="-")),
                "line": norm(attr(claim, "line_of_business", "claim_type", "line", default="-")),
                "status": norm(attr(claim, "status", "claim_status", default="-")),
                "paid": paid,
                "reserve": reserve,
                "total": total,
                "date_of_loss": norm(attr(claim, "date_of_loss", "loss_date", default="")),
                "description": norm(attr(claim, "description", "loss_description", "cause_of_loss", default="")),
                "flag": norm(attr(claim, "flag", "risk_flag", default="")),
            }
        )

    return rows


def is_open(row):
    return "open" in row.get("status", "").lower() or "reopen" in row.get("status", "").lower()


def is_closed(row):
    status = row.get("status", "").lower()
    return "closed" in status or "settled" in status


def build_detailed_answer(question: str, claims, profile, selected_policy, policy_numbers):
    rows = claim_context_rows(claims)
    rows = sorted(rows, key=lambda r: (0 if is_open(r) else 1 if not is_closed(r) else 2, -r["total"]))

    total_claims = len(rows)
    open_rows = [r for r in rows if is_open(r)]
    closed_rows = [r for r in rows if is_closed(r)]
    total_paid = sum(r["paid"] for r in rows)
    total_reserve = sum(r["reserve"] for r in rows)
    total_incurred = sum(r["total"] for r in rows)
    largest = max(rows, key=lambda r: r["total"], default=None)

    profile = profile_to_dict(profile)
    insured = (
        profile.get("business_name")
        or profile.get("insured")
        or profile.get("named_insured")
        or "the selected account"
    )

    q = (question or "").lower()

    if not rows:
        return (
            f"Policy analyzed: {selected_policy or 'Selected account'}\n"
            f"Claims used: 0\n\n"
            "I do not see claim rows tied to the selected account yet. Upload or select the account loss run first, then Copilot can analyze renewal concerns, severity drivers, open reserves, claim mix, and broker strategy."
        )

    open_detail = "\n".join(
        [
            f"- {r['claim_number']} | {r['line']} | {dollars(r['total'])} total | {dollars(r['reserve'])} reserve | Policy {r['policy_number']}"
            for r in open_rows[:8]
        ]
    ) or "- No open claims."

    top_detail = "\n".join(
        [
            f"- {r['claim_number']} | {r['status']} | {r['line']} | {dollars(r['total'])} total | {dollars(r['reserve'])} reserve"
            for r in rows[:8]
        ]
    )

    policy_text = ", ".join(policy_numbers[:8]) if policy_numbers else selected_policy or "selected account"

    severity_comment = "low"
    if total_incurred >= 250000 or total_reserve >= 100000 or len(open_rows) >= 4:
        severity_comment = "critical"
    elif total_incurred >= 100000 or total_reserve >= 50000 or len(open_rows) >= 2:
        severity_comment = "high"
    elif total_incurred >= 50000:
        severity_comment = "moderate"

    premium_reason = (
        f"The premium pressure is driven by {total_claims} validated claim(s), "
        f"{len(open_rows)} open claim(s), {dollars(total_incurred)} total incurred, "
        f"and {dollars(total_reserve)} still sitting in reserves. "
        "Open reserves matter because underwriters treat unresolved claim cost as uncertainty."
    )

    if "premium" in q or "high" in q or "renewal" in q:
        focus = premium_reason
    elif "litigation" in q:
        focus = (
            "I do not see litigation count shown as active in the selected claim set, but carriers will still ask for open-claim status, reserve rationale, and whether any attorney involvement exists on the largest open losses."
        )
    elif "broker" in q or "explain" in q or "submission" in q:
        focus = (
            "The broker should explain the open claim reserve position, what caused the largest losses, what corrective actions were taken, and whether reserves are expected to close, reduce, or develop further."
        )
    elif "concern" in q or "carrier" in q:
        focus = (
            "The biggest carrier concerns are open reserves, claim frequency across multiple policy lines, and whether the current loss controls are strong enough to prevent recurrence."
        )
    else:
        focus = (
            "The account needs underwriting attention because claim frequency, open claim reserves, and total incurred losses create renewal pressure."
        )

    answer = f"""Policy analyzed: {selected_policy or policy_text}
Claims used: {total_claims}

Account reviewed: {insured}
Policies considered: {policy_text}

Direct answer:
{focus}

Claim summary:
- Total claims: {total_claims}
- Open claims: {len(open_rows)}
- Closed claims: {len(closed_rows)}
- Paid losses: {dollars(total_paid)}
- Open reserves: {dollars(total_reserve)}
- Total incurred: {dollars(total_incurred)}
- Largest loss: {largest['claim_number'] if largest else '-'} at {dollars(largest['total']) if largest else '$0'}
- Renewal concern level: {severity_comment.upper()}

Open claims that need carrier explanation:
{open_detail}

Top claim drivers:
{top_detail}

Underwriter concerns:
- Open reserves may still develop before renewal.
- Claim frequency indicates the carrier may question operational controls.
- Multiple policy lines with losses can make placement harder than a single isolated loss.
- The account should not be marketed without updated loss runs and open-claim status notes.

Broker talking points:
- Explain what caused each open claim.
- Provide reserve comments from the carrier or adjuster.
- State whether any claim is expected to close before renewal.
- Document corrective actions, safety changes, training, maintenance, or operational controls.
- Prepare a clean carrier submission packet with current loss runs, policy schedule, exposure inputs, and renewal narrative.

Recommended next step:
Request an updated loss run and add short claim notes for each open claim before sending this account to markets."""

    return answer


@router.post("/ask")
def ask_copilot(
    request: CopilotRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # LOSSQ_COPILOT_NO_500_GUARD_V1
    try:
        org_id = current_org_id(current_user)

        if not org_id:
            return {
                "answer": "I could not verify the organization context for this user.",
                "policy_number": request.policy_number,
                "claims_used": 0,
                "policy_numbers_used": [],
            }

        policy_numbers = resolve_policy_numbers(db, current_user, request)

        claims = []
        if policy_numbers:
            claims = (
                db.query(Claim)
                .filter(Claim.organization_id == org_id)
                .filter(func.upper(func.trim(Claim.policy_number)).in_(policy_numbers))
                .all()
            )

        if not claims:
            claims = visible_claim_objects(request)

        saved_profile = find_saved_profile(db, current_user, request)
        profile = profile_to_dict(saved_profile)

        if not profile and isinstance(request.profile, dict):
            profile = request.profile

        if not isinstance(profile, dict):
            profile = {}

        selected_policy = (
            request.policy_number
            or request.account_number
            or profile.get("policy_number")
            or "Selected account"
        )

        answer = build_detailed_answer(
            request.question,
            claims,
            profile,
            selected_policy,
            policy_numbers,
        )

        return {
            "answer": answer,
            "policy_number": selected_policy,
            "policy_numbers_used": policy_numbers,
            "claims_used": len(claims or []),
        }

    except Exception as exc:
        print("LOSSQ_COPILOT_ERROR_START")
        print(traceback.format_exc())
        print("LOSSQ_COPILOT_ERROR_END")

        return {
            "answer": (
                "Copilot hit a backend issue while reviewing this account, but the backend stayed online. "
                "Please retry after refreshing the account. The error has been logged for repair."
            ),
            "policy_number": request.policy_number or request.account_number or "Selected account",
            "policy_numbers_used": request.policy_numbers or [],
            "claims_used": 0,
            "error": str(exc),
        }
