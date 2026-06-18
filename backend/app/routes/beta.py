from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import json
import os
import urllib.request
import urllib.error

router = APIRouter(prefix="/beta", tags=["Beta Notifications"])


class BetaNotifyRequest(BaseModel):
    email: str
    source: Optional[str] = "landing_page"
    page_url: Optional[str] = ""
    user_agent: Optional[str] = ""
    note: Optional[str] = ""


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
    error = ""

    try:
        sent = send_beta_notification(payload)
    except Exception as exc:
        error = str(exc)[:300]
        print("LOSSQ_BETA_NOTIFY_EMAIL_ERROR:", error)

    return {
        "ok": True,
        "sent": sent,
        "message": "Beta request received.",
        "email": payload.email,
        "error": error if os.getenv("LOSSQ_DEBUG_EMAIL_ERRORS", "").lower() == "true" else "",
    }
