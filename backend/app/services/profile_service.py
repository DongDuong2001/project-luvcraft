import logging
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.access_control import BrandDomain, UserProfile


logger = logging.getLogger(__name__)


def normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    local_part, separator, domain = normalized.rpartition("@")
    if not separator or not local_part or not domain:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated identity is missing a valid email address",
        )
    return f"{local_part}@{domain}"


def email_domain(email: str) -> str:
    return normalize_email(email).rsplit("@", 1)[1]


def resolve_initial_access(email: str, db: Session) -> tuple[str, UUID | None]:
    """Resolve a safe first-login role and optional brand tenant."""
    normalized_email = normalize_email(email)
    if normalized_email in settings.rbac_admin_emails:
        return "admin", None

    domain = email_domain(normalized_email)
    if domain in settings.internal_email_domains:
        return "analyst", None

    brand_domain = (
        db.query(BrandDomain)
        .filter(BrandDomain.domain_name == domain)
        .first()
    )
    if brand_domain is not None:
        return "client", brand_domain.brand_id
    return "viewer", None


def get_or_create_user_profile(
    *,
    user_id: UUID,
    email: str | None,
    db: Session,
) -> UserProfile:
    """Load an authorization profile, provisioning it on first login."""
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if profile is not None:
        # The admin allowlist is a bootstrap floor, not a one-shot default: an
        # operator adding an email to RBAC_ADMIN_EMAILS after that user's first
        # login must still result in an admin, otherwise a deployment with zero
        # admins can never promote anyone.
        if (
            profile.role != "admin"
            and normalize_email(profile.email) in settings.rbac_admin_emails
        ):
            previous_role = profile.role
            profile.role = "admin"
            db.commit()
            logger.info(
                "Promoted user_id=%s from role=%s to admin via RBAC_ADMIN_EMAILS",
                user_id,
                previous_role,
            )
        return profile

    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated identity is missing an email address",
        )

    normalized_email = normalize_email(email)
    role, brand_id = resolve_initial_access(normalized_email, db)
    profile = UserProfile(
        user_id=user_id,
        email=normalized_email,
        role=role,
        brand_id=brand_id,
        is_active=True,
    )

    try:
        # A savepoint keeps the surrounding request transaction usable if two
        # first-login requests race to create the same profile.
        with db.begin_nested():
            db.add(profile)
            db.flush()
    except IntegrityError:
        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        if profile is None:
            logger.warning("Profile provisioning conflict for user_id=%s", user_id)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user profile already exists for this identity",
            )
    else:
        # Provisioning is an authentication-side effect and must survive read-only
        # endpoints such as /auth/me, whose request handlers do not commit.
        db.commit()

    return profile
