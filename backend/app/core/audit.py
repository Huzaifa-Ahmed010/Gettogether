from sqlalchemy.orm import Session

from app.models import AuditEvent, User


def record_audit_event(
    db: Session,
    actor: User | None,
    action: str,
    resource_type: str,
    resource_id: int | None,
) -> None:
    db.add(
        AuditEvent(
            actor_user_id=actor.id if actor else None,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
        )
    )
