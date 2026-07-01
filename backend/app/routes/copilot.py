import re
import traceback
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
  language_output: str | None = None
  language_output_label: str | None = None


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
        "reported_date": norm(attr(claim, "reported_date", "report_date", default="")),
        "claimant": norm(attr(claim, "claimant", "claimant_name", default="")),
        "cause": norm(attr(claim, "cause_of_loss", "cause", "loss_cause", default="")),
        "description": norm(attr(claim, "description", "loss_description", "cause_of_loss", default="")),
        "adjuster": norm(attr(claim, "adjuster", "examiner", "adjuster_name", default="")),
        "attorney": norm(attr(claim, "attorney_involved", "attorney", "litigation", "suit_status", default="")),
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
  policy_text = ", ".join(policy_numbers[:8]) if policy_numbers else selected_policy or "selected account"

  if not rows:
    return (
      f"I do not see claim rows tied to {selected_policy or 'the selected account'} yet. "
      "Upload or select the loss run first, then ask me about causes, reserves, policy lines, renewal risk, carrier strategy, or package generation."
    )

  def header(title):
    return (
      f"{title}\n"
      f"Account: {insured}\n"
      f"Policy context: {selected_policy or policy_text}\n"
      f"Claims used: {total_claims}\n\n"
    )

  def claim_line(row, include_cause=True):
    parts = [
      row.get("claim_number") or "-",
      row.get("status") or "-",
      row.get("line") or "-",
      f"Policy {row.get('policy_number') or '-'}",
      f"Paid {dollars(row['paid'])}",
      f"Reserve {dollars(row['reserve'])}",
      f"Total {dollars(row['total'])}",
    ]
    if include_cause and (row.get("cause") or row.get("description")):
      parts.append(f"Cause: {row.get('cause') or row.get('description')}")
    if row.get("claimant"):
      parts.append(f"Claimant: {row['claimant']}")
    if row.get("adjuster"):
      parts.append(f"Adjuster: {row['adjuster']}")
    return "- " + " | ".join(parts)

  def totals():
    return (
      f"- Total claims: {total_claims}\n"
      f"- Open claims: {len(open_rows)}\n"
      f"- Closed claims: {len(closed_rows)}\n"
      f"- Paid: {dollars(total_paid)}\n"
      f"- Reserve: {dollars(total_reserve)}\n"
      f"- Total incurred: {dollars(total_incurred)}\n"
      f"- Largest loss: {(largest or {}).get('claim_number', '-')} at {dollars((largest or {}).get('total', 0))}"
    )

  def legal_signal(row):
    text = " ".join(
      str(row.get(key) or "")
      for key in ("attorney", "flag", "description", "cause")
    ).lower()
    if any(term in text for term in ("none", "no attorney", "not involved", "no suit", "no litigation")):
      return False
    return any(term in text for term in ("attorney", "litigation", "suit", "counsel", "represented"))

  if any(term in q for term in ("cause", "caused", "why", "what happened", "loss driver", "driver")):
    cause_rows = [r for r in rows if r.get("cause") or r.get("description")]
    if not cause_rows:
      return header("Loss Cause Review") + (
        "I do not see a labeled cause-of-loss field in these claim rows. I can still use policy line, status, paid, reserve, and incurred values, but the file does not give me a clean cause label to quote."
      )
    return header("Loss Cause Review") + "Readable causes:\n" + "\n".join(
      claim_line(r) for r in cause_rows[:12]
    )

  if any(term in q for term in ("open", "reserve", "reserves", "outstanding")):
    if not open_rows:
      return header("Open Claim Review") + "There are no open claims in the selected claim set.\n\n" + totals()
    reserve_rows = sorted(open_rows, key=lambda r: r["reserve"], reverse=True)
    return header("Open Claim Review") + (
      f"There are {len(open_rows)} open claim(s) with {dollars(sum(r['reserve'] for r in open_rows))} in open reserves. "
      "These are the claims carriers will want explained first:\n"
      + "\n".join(claim_line(r) for r in reserve_rows[:12])
      + "\n\nNext action: get adjuster status, expected closure timing, reserve rationale, and corrective action for each open claim."
    )

  if any(term in q for term in ("litigation", "attorney", "suit", "legal", "counsel")):
    legal_rows = [r for r in rows if legal_signal(r)]
    if not legal_rows:
      return header("Litigation Review") + (
        "I do not see attorney, suit, counsel, or litigation involvement marked on the selected claim rows. If the source file has legal status in a separate note field, upload the full file and I can read it into the claim detail view."
      )
    return header("Litigation Review") + "Claims with legal signals:\n" + "\n".join(
      claim_line(r, include_cause=True) for r in legal_rows[:12]
    )

  if any(term in q for term in ("policy", "coverage", "line", "lines")):
    by_policy = {}
    for r in rows:
      key = r.get("policy_number") or "-"
      by_policy.setdefault(key, {"claims": 0, "total": 0, "reserve": 0, "lines": set()})
      by_policy[key]["claims"] += 1
      by_policy[key]["total"] += r["total"]
      by_policy[key]["reserve"] += r["reserve"]
      if r.get("line"):
        by_policy[key]["lines"].add(r["line"])
    lines = []
    for policy, data in sorted(by_policy.items(), key=lambda item: item[1]["total"], reverse=True):
      lob = ", ".join(sorted(data["lines"])) or "-"
      lines.append(f"- {policy}: {data['claims']} claim(s), {dollars(data['total'])} incurred, {dollars(data['reserve'])} reserve, lines: {lob}")
    return header("Policy And Coverage Review") + "\n".join(lines[:15])

  if any(term in q for term in ("count", "how many", "total", "summary")):
    return header("Claim Count And Totals") + totals()

  if any(term in q for term in ("premium", "renewal", "price", "rate", "increase")):
    return header("Renewal Pressure Review") + (
      f"Renewal pressure is tied to {total_claims} claim(s), {len(open_rows)} open claim(s), "
      f"{dollars(total_reserve)} in reserves, and {dollars(total_incurred)} total incurred. "
      "Open reserves are the most sensitive part because they can still develop before the carrier finalizes terms.\n\n"
      "Largest drivers:\n" + "\n".join(claim_line(r) for r in rows[:8])
    )

  if any(term in q for term in ("carrier", "concern", "underwriter", "market")):
    concerns = []
    if open_rows:
      concerns.append(f"Open claims: {len(open_rows)} open claim(s) with {dollars(total_reserve)} in reserve.")
    if largest:
      concerns.append(f"Severity: largest loss is {largest['claim_number']} at {dollars(largest['total'])}.")
    if total_claims >= 5:
      concerns.append(f"Frequency: {total_claims} claim(s) in the selected loss run.")
    if not concerns:
      concerns.append("The selected loss run does not show a major frequency or reserve problem from the claim rows available.")
    return header("Carrier Concern Review") + "\n".join(f"- {item}" for item in concerns)

  if any(term in q for term in ("broker", "explain", "talking point", "narrative")):
    return header("Broker Narrative") + (
      "Use this carrier-facing explanation:\n"
      f"- Account has {total_claims} claim(s), {len(open_rows)} open and {len(closed_rows)} closed.\n"
      f"- Total incurred is {dollars(total_incurred)}, with {dollars(total_reserve)} still reserved.\n"
      "- Address each open claim with current status, expected closure date, and reserve rationale.\n"
      "- Tie corrective actions directly to the loss causes shown in the file.\n"
      "- Include updated loss runs, policy schedule, exposure inputs, and renewal narrative in the submission packet."
    )

  if any(term in q for term in ("package", "submission", "packet", "generate")):
    return header("Submission Package Request") + (
      "I can build the submission package from this account context. The package should include account profile, policy schedule, exposure inputs, claim summary, open-claim explanations, loss-control narrative, renewal risk, carrier appetite, premium forecast, and submission readiness notes.\n\n"
      "Recommended package focus:\n"
      + totals()
      + "\n- Add a short note for every open claim before sending to markets."
    )

  return header("File Review") + (
    "Here is the direct read from the selected file context:\n"
    + totals()
    + "\n\nTop claim rows:\n"
    + "\n".join(claim_line(r) for r in rows[:8])
    + "\n\nAsk me about causes, open reserves, litigation, policy lines, renewal pressure, carrier concerns, or package generation for a narrower answer."
  )


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
