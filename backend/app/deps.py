from uuid import UUID

from pydantic import BaseModel


class CurrentUser(BaseModel):
    user_id: UUID


def get_current_user() -> CurrentUser:
    """
    Stub dependency for Supabase JWT verification.
    Will be replaced with real JWT parsing in a later sprint.
    Never trust user ID from request body!
    """
    return CurrentUser(user_id="00000000-0000-0000-0000-000000000000")
