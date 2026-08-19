from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.deps import CurrentUser
from app.models.access_control import AuditLog


def record_audit_event(
    *,
    db: Session,
    actor: CurrentUser,
    action_type: str,
    resource_type: str,
    resource_id: str | None = None,
    old_state: dict[str, Any] | None = None,
    new_state: dict[str, Any] | None = None,
    request: Request | None = None,
) -> AuditLog:
    """Stage an audit event in the caller's transaction without committing it."""
    entry = AuditLog(
        actor_id=actor.user_id,
        actor_email=actor.email or "unknown",
        actor_role=actor.role,
        action_type=action_type,
        resource_type=resource_type,
        resource_id=resource_id,
        old_state=old_state,
        new_state=new_state,
        ip_address=(request.client.host if request and request.client else None),
        user_agent=(request.headers.get("user-agent") if request else None),
    )
    db.add(entry)
    return entry
