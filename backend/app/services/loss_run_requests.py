from __future__ import annotations

from datetime import datetime, timezone


REQUEST_STATUSES = {
    "draft",
    "authorization_needed",
    "requested",
    "follow_up_due",
    "received",
    "processing",
    "completed",
    "cancelled",
}

ALLOWED_TRANSITIONS = {
    "draft": {"authorization_needed", "requested", "cancelled"},
    "authorization_needed": {"requested", "cancelled"},
    "requested": {"follow_up_due", "received", "cancelled"},
    "follow_up_due": {"requested", "received", "cancelled"},
    "received": {"processing", "completed"},
    "processing": {"completed", "follow_up_due"},
    "completed": set(),
    "cancelled": {"draft"},
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def validate_transition(current: str, target: str) -> None:
    if current not in REQUEST_STATUSES or target not in REQUEST_STATUSES:
        raise ValueError("Unknown loss-run request status.")
    if current == target:
        return
    if target not in ALLOWED_TRANSITIONS[current]:
        raise ValueError(f"Cannot move a loss-run request from {current} to {target}.")


def needs_attention(status: str, next_follow_up_at: datetime | None, now: datetime | None = None) -> bool:
    if status == "authorization_needed":
        return True
    if status not in {"requested", "follow_up_due", "processing"} or next_follow_up_at is None:
        return status == "follow_up_due"
    current = now or utc_now()
    follow_up = next_follow_up_at
    if follow_up.tzinfo is None:
        follow_up = follow_up.replace(tzinfo=timezone.utc)
    return follow_up <= current
