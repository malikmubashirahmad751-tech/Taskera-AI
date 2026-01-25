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

def set_current_user_id(user_id: str) -> None:
    """
    Set the current user_id in context.
    
    Args:
        user_id: The user identifier to set
    """
    if user_id:
        user_id_context.set(user_id)
    else:
        logger.warning("[Context] Attempted to set empty user_id")