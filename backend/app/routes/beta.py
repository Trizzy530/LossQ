from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import os
import smtplib
from email.message import EmailMessage

router = APIRouter(prefix="/beta", tags=["Beta Notifications"])


class BetaNotifyRequest(BaseModel):
    email: str
    source: Optional[str] = "landing_page"
    page_url: Optional[str] = ""
    user_agent: Optional[str] = ""
    note: Optional[str] = ""


def send_beta_notification(payload: BetaNotifyRequest):
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587") or "587")
    smtp_username = os.getenv("SMTP_USERNAME", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_from = os.getenv("SMTP_FROM_EMAIL", smtp_username or "support@lossq.com").strip()
    notify_to = os.getenv("BETA_NOTIFY_EMAIL", "support@lossq.com").strip()

    if not smtp_host or not smtp_username or not smtp_password or not notify_to:
        print(
            "LOSSQ_BETA_NOTIFY_SMTP_NOT_CONFIGURED:",
            {
                "email": payload.email,
                "source": payload.source,
                "page_url": payload.page_url,
                "notify_to": notify_to,
            },
        )
        return False

    msg = EmailMessage()
    msg["Subject"] = f"New LossQ Beta Signup: {payload.email}"
    msg["From"] = smtp_from
    msg["To"] = notify_to

    body = f"""
New LossQ beta signup received.

Email: {payload.email}
Source: {payload.source or ""}
Page URL: {payload.page_url or ""}
User Agent: {payload.user_agent or ""}
Note: {payload.note or ""}
Received At: {datetime.utcnow().isoformat()} UTC
""".strip()

    msg.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.send_message(msg)

    print("LOSSQ_BETA_NOTIFY_EMAIL_SENT:", {"email": payload.email, "notify_to": notify_to})
    return True


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
    error = ""

    try:
        sent = send_beta_notification(payload)
    except Exception as exc:
        error = str(exc)[:300]
        print("LOSSQ_BETA_NOTIFY_EMAIL_ERROR:", error)

    # Always return success to the website visitor so the beta form does not expose email config details.
    return {
        "ok": True,
        "sent": sent,
        "message": "Beta request received.",
        "email": payload.email,
        "error": error if os.getenv("LOSSQ_DEBUG_EMAIL_ERRORS", "").lower() == "true" else "",
    }
