from contextvars import ContextVar

user_id_context: ContextVar[str] = ContextVar("user_id", default=None)

def get_current_user_id():
    """Retrieves the user_id for the current request context."""
    return user_id_context.get()