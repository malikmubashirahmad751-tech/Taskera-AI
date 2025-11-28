from contextvars import ContextVar
from typing import Optional, Any

user_id_context: ContextVar[Optional[str]] = ContextVar("user_id", default=None)

def get_current_user_id() -> Optional[str]:
    """
    Get the current user ID from context.
    Returns None if not set.
    """
    return user_id_context.get()

def set_current_user_id(user_id: str) -> Any:
    """
    Set the current user ID in context.
    Returns a token that can be used to reset the context.
    """
    return user_id_context.set(user_id)

def reset_user_context(token: Any):
    """
    Reset the context to its previous state using a token.
    """
    user_id_context.reset(token)