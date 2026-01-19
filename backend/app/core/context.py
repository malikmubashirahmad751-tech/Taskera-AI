from contextvars import ContextVar
from typing import Optional
from app.core.logger import logger

user_id_context: ContextVar[Optional[str]] = ContextVar('user_id', default=None)

def get_current_user_id() -> Optional[str]:
    """
    Get the current user_id from context.
    Returns None if not set.
    """
    try:
        user_id = user_id_context.get()
        return user_id
    except LookupError:
        logger.warning("[Context] user_id not set in context")
        return None

def set_current_user_id(user_id: str):
    """
    Set the current user_id in context.
    Returns a token that must be used to reset the context.
    """
    if user_id:
        return user_id_context.set(user_id)
    else:
        logger.warning("[Context] Attempted to set empty user_id")
        return None

def reset_current_user_id(token):
    """
    Reset the user_id context using the token returned by set_current_user_id.
    """
    if token:
        user_id_context.reset(token)