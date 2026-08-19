from collections.abc import Iterable
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Query, Session

from app.db.session import get_db
from app.deps import CurrentUser, get_current_user
from app.models.orchestration import ResearchRun


GLOBAL_ROLES = frozenset({"admin", "analyst"})
RUN_WRITE_ROLES = frozenset({"admin", "analyst", "client"})


class RoleChecker:
    """Reusable FastAPI dependency for coarse-grained role requirements."""

    def __init__(self, allowed_roles: Iterable[str]):
        self.allowed_roles = frozenset(allowed_roles)

    def __call__(
        self,
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if current_user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user


def can_read_run(run: ResearchRun, current_user: CurrentUser) -> bool:
    if current_user.role in GLOBAL_ROLES:
        return True
    if current_user.brand_id is not None:
        return run.target_brand_id == current_user.brand_id
    return current_user.role == "viewer" and bool(run.is_public_demo)


def get_authorized_run(
    run_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResearchRun:
    """Load a run and enforce tenant read access without leaking its existence."""
    run = db.query(ResearchRun).filter(ResearchRun.run_id == run_id).first()
    if run is None or not can_read_run(run, current_user):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run not found",
        )
    return run


def scope_runs_query(query: Query, current_user: CurrentUser) -> Query:
    """Apply the caller's tenant visibility to a ResearchRun query."""
    if current_user.role in GLOBAL_ROLES:
        return query
    if current_user.brand_id is not None:
        return query.filter(ResearchRun.target_brand_id == current_user.brand_id)
    return query.filter(ResearchRun.is_public_demo.is_(True))


def require_run_write_permission(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    if current_user.role not in RUN_WRITE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers cannot trigger research runs",
        )
    if current_user.role == "client" and current_user.brand_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client account is not assigned to a brand",
        )
    return current_user


def resolve_run_target_brand(
    requested_brand_id: UUID | None,
    current_user: CurrentUser,
) -> UUID:
    """Resolve a trusted tenant for run creation without accepting spoofed input."""
    require_run_write_permission(current_user)

    if current_user.role == "client":
        if requested_brand_id is not None and requested_brand_id != current_user.brand_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Clients can only create runs for their assigned brand",
            )
        # The write guard guarantees this is non-null for clients.
        return current_user.brand_id  # type: ignore[return-value]

    if requested_brand_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="target_brand_id is required for admin and analyst users",
        )
    return requested_brand_id
