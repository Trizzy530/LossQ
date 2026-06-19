from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from typing import Optional
from datetime import datetime
import json
import os
import urllib.request
import urllib.error
from app.database import SessionLocal
from app.auth_utils import get_current_user

router = APIRouter(prefix="/beta", tags=["Beta Notifications"])


class BetaNotifyRequest(BaseModel):
    email: str
    source: Optional[str] = "landing_page"
    page_url: Optional[str] = ""
    user_agent: Optional[str] = ""


# LOSSQ_BETA_REQUEST_STORAGE_V1
def ensure_beta_requests_table(db):
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS beta_requests (
                id SERIAL PRIMARY KEY,
                email VARCHAR(320) UNIQUE NOT NULL,
                source VARCHAR(120),
                page_url TEXT,
                user_agent TEXT,
                status VARCHAR(50) DEFAULT 'new',
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                approved_at TIMESTAMP NULL,
                rejected_at TIMESTAMP NULL,
                activated_at TIMESTAMP NULL
            )
            """
        )
    )

    for column_sql in [
        "ALTER TABLE beta_requests ADD COLUMN IF NOT EXISTS source VARCHAR(120)",
        "ALTER TABLE beta_requests ADD COLUMN IF NOT EXISTS page_url TEXT",
        "ALTER TABLE beta_requests ADD COLUMN IF NOT EXISTS user_agent TEXT",
        "ALTER TABLE beta_requests ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'new'",
        "ALTER TABLE beta_requests ADD COLUMN IF NOT EXISTS notes TEXT",
        "ALTER TABLE beta_requests ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE beta_requests ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE beta_requests ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP NULL",
        "ALTER TABLE beta_requests ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMP NULL",
        "ALTER TABLE beta_requests ADD COLUMN IF NOT EXISTS activated_at TIMESTAMP NULL",
    ]:
        try:
            db.execute(text(column_sql))
        except Exception:
            pass

    db.commit()


def save_beta_request(payload: BetaNotifyRequest):
    db = SessionLocal()
    try:
        ensure_beta_requests_table(db)

        existing = db.execute(
            text("SELECT id, status FROM beta_requests WHERE lower(email) = :email LIMIT 1"),
            {"email": payload.email},
        ).fetchone()

        if existing:
            current_status = str(dict(existing._mapping).get("status") or "new").lower()
            next_status = "new" if current_status in {"rejected"} else current_status

            db.execute(
                text(
                    """
                    UPDATE beta_requests
                    SET source = :source,
                        page_url = :page_url,
                        user_agent = :user_agent,
                        status = :status,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE lower(email) = :email
                    """
                ),
                {
                    "email": payload.email,
                    "source": payload.source or "landing_page",
                    "page_url": payload.page_url or "",
                    "user_agent": payload.user_agent or "",
                    "status": next_status,
                },
            )
        else:
            db.execute(
                text(
                    """
                    INSERT INTO beta_requests (email, source, page_url, user_agent, status)
                    VALUES (:email, :source, :page_url, :user_agent, 'new')
                    """
                ),
                {
                    "email": payload.email,
                    "source": payload.source or "landing_page",
                    "page_url": payload.page_url or "",
                    "user_agent": payload.user_agent or "",
                },
            )

        db.commit()
        return True
    finally:
        db.close()
    note: Optional[str] = ""








# LOSSQ_BETA_EXIT_SURVEY_V1
class BetaExitSurveyRequest(BaseModel):
    overall_score: int
    would_pay: Optional[str] = ""
    likely_plan: Optional[str] = ""
    most_valuable_feature: Optional[str] = ""
    most_confusing_part: Optional[str] = ""
    missing_feature: Optional[str] = ""
    would_recommend: Optional[str] = ""
    launch_blocker: Optional[str] = ""
    additional_feedback: Optional[str] = ""
    page_url: Optional[str] = ""


def ensure_beta_exit_surveys_table(db):
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS beta_exit_surveys (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NULL,
                organization_id INTEGER NULL,
                email VARCHAR(320),
                overall_score INTEGER,
                would_pay VARCHAR(80),
                likely_plan VARCHAR(120),
                most_valuable_feature TEXT,
                most_confusing_part TEXT,
                missing_feature TEXT,
                would_recommend VARCHAR(80),
                launch_blocker TEXT,
                additional_feedback TEXT,
                page_url TEXT,
                status VARCHAR(50) DEFAULT 'new',
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )

    for column_sql in [
        "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS user_id INTEGER NULL",
        "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS organization_id INTEGER NULL",
        "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS email VARCHAR(320)",
        "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS overall_score INTEGER",
        "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS would_pay VARCHAR(80)",
        "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS likely_plan VARCHAR(120)",
        "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS most_valuable_feature TEXT",
        "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS most_confusing_part TEXT",
        "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS missing_feature TEXT",
        "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS would_recommend VARCHAR(80)",
        "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS launch_blocker TEXT",
        "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS additional_feedback TEXT",
        "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS page_url TEXT",
        "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'new'",
        "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS notes TEXT",
        "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE beta_exit_surveys ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    ]:
        try:
            db.execute(text(column_sql))
        except Exception:
            pass

    db.commit()

# LOSSQ_BETA_FEEDBACK_TRACKER_V1
class BetaFeedbackRequest(BaseModel):
    message: str
    feature: Optional[str] = "General"
    page_url: Optional[str] = ""
    severity: Optional[str] = "normal"


def ensure_beta_feedback_table(db):
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS beta_feedback (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NULL,
                organization_id INTEGER NULL,
                email VARCHAR(320),
                feature VARCHAR(160),
                severity VARCHAR(50),
                message TEXT NOT NULL,
                page_url TEXT,
                status VARCHAR(50) DEFAULT 'new',
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )

    for column_sql in [
        "ALTER TABLE beta_feedback ADD COLUMN IF NOT EXISTS user_id INTEGER NULL",
        "ALTER TABLE beta_feedback ADD COLUMN IF NOT EXISTS organization_id INTEGER NULL",
        "ALTER TABLE beta_feedback ADD COLUMN IF NOT EXISTS email VARCHAR(320)",
        "ALTER TABLE beta_feedback ADD COLUMN IF NOT EXISTS feature VARCHAR(160)",
        "ALTER TABLE beta_feedback ADD COLUMN IF NOT EXISTS severity VARCHAR(50)",
        "ALTER TABLE beta_feedback ADD COLUMN IF NOT EXISTS message TEXT",
        "ALTER TABLE beta_feedback ADD COLUMN IF NOT EXISTS page_url TEXT",
        "ALTER TABLE beta_feedback ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'new'",
        "ALTER TABLE beta_feedback ADD COLUMN IF NOT EXISTS notes TEXT",
        "ALTER TABLE beta_feedback ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE beta_feedback ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    ]:
        try:
            db.execute(text(column_sql))
        except Exception:
            pass

    db.commit()

# LOSSQ_BETA_AUTO_REPLY_V1
def send_beta_auto_reply(payload: BetaNotifyRequest):
    enabled = os.getenv("BETA_AUTO_REPLY_ENABLED", "true").strip().lower()
    if enabled in {"false", "0", "no", "off"}:
        print("LOSSQ_BETA_AUTO_REPLY_SKIPPED_DISABLED:", {"email": payload.email})
        return False

    resend_api_key = os.getenv("RESEND_API_KEY", "").strip()
    from_email = os.getenv("SMTP_FROM_EMAIL", "hello@lossq.com").strip()

    if not resend_api_key or not from_email:
        print(
            "LOSSQ_BETA_AUTO_REPLY_NOT_CONFIGURED:",
            {
                "email": payload.email,
                "from_email": from_email,
                "has_resend_key": bool(resend_api_key),
            },
        )
        return False

    subject = "Your LossQ beta request was received"

    body = f"""
Hi,

Thank you for requesting beta access to LossQ.

We received your request and will review it shortly. LossQ beta access is being opened in stages for agencies, brokers, and insurance professionals who want to test loss run uploads, claims analysis, renewal insights, exposure inputs, and submission tools.

Next step:

Please create your LossQ account using the same email address you used for the beta request:

https://www.lossq.com/register

Once your account is created, our team can activate limited beta dashboard access if approved.

Best,
LossQ Team
hello@lossq.com
""".strip()

    data = {
        "from": f"LossQ <{from_email}>",
        "to": [payload.email],
        "subject": subject,
        "text": body,
    }

    request = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(data).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {resend_api_key}",
            "Content-Type": "application/json",
            "User-Agent": "LossQ/1.0 (https://www.lossq.com; hello@lossq.com)",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            print(
                "LOSSQ_BETA_AUTO_REPLY_SENT:",
                {
                    "email": payload.email,
                    "status": response.status,
                    "response": response_body[:500],
                },
            )
            return 200 <= response.status < 300
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        print(
            "LOSSQ_BETA_AUTO_REPLY_HTTP_ERROR:",
            {
                "status": exc.code,
                "body": error_body[:1000],
            },
        )
        raise Exception(f"Auto-reply Resend HTTP {exc.code}: {error_body[:300]}")
    except Exception as exc:
        print("LOSSQ_BETA_AUTO_REPLY_ERROR:", str(exc)[:500])
        raise

def send_beta_notification(payload: BetaNotifyRequest):
    resend_api_key = os.getenv("RESEND_API_KEY", "").strip()
    from_email = os.getenv("SMTP_FROM_EMAIL", "hello@lossq.com").strip()
    notify_to = os.getenv("BETA_NOTIFY_EMAIL", "hello@lossq.com").strip()

    if not resend_api_key or not from_email or not notify_to:
        print(
            "LOSSQ_BETA_NOTIFY_RESEND_NOT_CONFIGURED:",
            {
                "email": payload.email,
                "source": payload.source,
                "from_email": from_email,
                "notify_to": notify_to,
                "has_resend_key": bool(resend_api_key),
            },
        )
        return False

    subject = f"New LossQ Beta Signup: {payload.email}"

    body = f"""
New LossQ beta signup received.

Email: {payload.email}
Source: {payload.source or ""}
Page URL: {payload.page_url or ""}
User Agent: {payload.user_agent or ""}
Note: {payload.note or ""}
Received At: {datetime.utcnow().isoformat()} UTC
""".strip()

    data = {
        "from": f"LossQ <{from_email}>",
        "to": [notify_to],
        "subject": subject,
        "text": body,
        "reply_to": payload.email,
    }

    request = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(data).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {resend_api_key}",
            "Content-Type": "application/json",
            "User-Agent": "LossQ/1.0 (https://www.lossq.com; hello@lossq.com)",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            print(
                "LOSSQ_BETA_NOTIFY_RESEND_SENT:",
                {
                    "email": payload.email,
                    "notify_to": notify_to,
                    "status": response.status,
                    "response": response_body[:500],
                },
            )
            return 200 <= response.status < 300
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        print(
            "LOSSQ_BETA_NOTIFY_RESEND_HTTP_ERROR:",
            {
                "status": exc.code,
                "body": error_body[:1000],
            },
        )
        raise Exception(f"Resend HTTP {exc.code}: {error_body[:300]}")
    except Exception as exc:
        print("LOSSQ_BETA_NOTIFY_RESEND_ERROR:", str(exc)[:500])
        raise


@router.post("/notify")
async def beta_notify(payload: BetaNotifyRequest):
    payload.email = str(payload.email or "").strip().lower()
    if "@" not in payload.email or "." not in payload.email:
        return {
            "ok": False,
            "sent": False,
            "message": "Enter a valid email address.",
            "email": payload.email,
            "error": "",
        }

    sent = False
    auto_reply_sent = False
    request_saved = False
    error = ""

    # LOSSQ_BETA_REQUEST_SAVE_ON_NOTIFY_V1
    try:
        request_saved = save_beta_request(payload)
    except Exception as exc:
        print("LOSSQ_BETA_REQUEST_SAVE_ERROR:", str(exc)[:500])

    try:
        sent = send_beta_notification(payload)
    except Exception as exc:
        error = str(exc)[:300]
        print("LOSSQ_BETA_NOTIFY_EMAIL_ERROR:", error)

    try:
        auto_reply_sent = send_beta_auto_reply(payload)
    except Exception as exc:
        auto_error = str(exc)[:300]
        print("LOSSQ_BETA_AUTO_REPLY_SEND_ERROR:", auto_error)
        if not error:
            error = auto_error

    return {
        "ok": True,
        "sent": sent,
        "auto_reply_sent": auto_reply_sent,
        "request_saved": request_saved,
        "message": "Beta request received.",
        "email": payload.email,
        "error": error if os.getenv("LOSSQ_DEBUG_EMAIL_ERRORS", "").lower() == "true" else "",
    }


@router.post("/feedback")
async def submit_beta_feedback(
    payload: BetaFeedbackRequest,
    current_user: dict = Depends(get_current_user),
):
    db = SessionLocal()
    try:
        ensure_beta_feedback_table(db)

        message = str(payload.message or "").strip()
        if len(message) < 5:
            return {
                "ok": False,
                "message": "Please enter more detail before submitting feedback.",
            }

        email = str(current_user.get("email") or "").strip().lower()
        user_id = current_user.get("user_id")
        organization_id = current_user.get("organization_id")

        db.execute(
            text(
                """
                INSERT INTO beta_feedback
                    (user_id, organization_id, email, feature, severity, message, page_url, status)
                VALUES
                    (:user_id, :organization_id, :email, :feature, :severity, :message, :page_url, 'new')
                """
            ),
            {
                "user_id": user_id,
                "organization_id": organization_id,
                "email": email,
                "feature": str(payload.feature or "General").strip()[:160],
                "severity": str(payload.severity or "normal").strip().lower()[:50],
                "message": message,
                "page_url": str(payload.page_url or "").strip(),
            },
        )

        db.commit()

        return {
            "ok": True,
            "message": "Feedback submitted. Thank you for helping improve LossQ.",
        }
    finally:
        db.close()


@router.post("/exit-survey")
async def submit_beta_exit_survey(
    payload: BetaExitSurveyRequest,
    current_user: dict = Depends(get_current_user),
):
    db = SessionLocal()
    try:
        ensure_beta_exit_surveys_table(db)

        score = int(payload.overall_score or 0)
        if score < 1 or score > 10:
            return {
                "ok": False,
                "message": "Overall score must be between 1 and 10.",
            }

        email = str(current_user.get("email") or "").strip().lower()
        user_id = current_user.get("user_id")
        organization_id = current_user.get("organization_id")

        db.execute(
            text(
                """
                INSERT INTO beta_exit_surveys
                    (
                        user_id, organization_id, email, overall_score, would_pay,
                        likely_plan, most_valuable_feature, most_confusing_part,
                        missing_feature, would_recommend, launch_blocker,
                        additional_feedback, page_url, status
                    )
                VALUES
                    (
                        :user_id, :organization_id, :email, :overall_score, :would_pay,
                        :likely_plan, :most_valuable_feature, :most_confusing_part,
                        :missing_feature, :would_recommend, :launch_blocker,
                        :additional_feedback, :page_url, 'new'
                    )
                """
            ),
            {
                "user_id": user_id,
                "organization_id": organization_id,
                "email": email,
                "overall_score": score,
                "would_pay": str(payload.would_pay or "").strip()[:80],
                "likely_plan": str(payload.likely_plan or "").strip()[:120],
                "most_valuable_feature": str(payload.most_valuable_feature or "").strip(),
                "most_confusing_part": str(payload.most_confusing_part or "").strip(),
                "missing_feature": str(payload.missing_feature or "").strip(),
                "would_recommend": str(payload.would_recommend or "").strip()[:80],
                "launch_blocker": str(payload.launch_blocker or "").strip(),
                "additional_feedback": str(payload.additional_feedback or "").strip(),
                "page_url": str(payload.page_url or "").strip(),
            },
        )

        db.commit()

        return {
            "ok": True,
            "message": "Exit survey submitted. Thank you for helping shape LossQ.",
        }
    finally:
        db.close()
