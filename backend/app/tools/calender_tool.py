from typing import Literal, Optional
from langchain.tools import tool
from app.services.scheduler_service import create_event, list_events, update_event, delete_event

Action = Literal["create", "list", "update", "delete"]

@tool
def manage_calendar_events(
    action: Action,
    event_id: Optional[int] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
    run_date_iso: Optional[str] = None
) -> str:
    """
    Manages calendar events. Use this tool to create, list, update, or delete events.
    
    To use this tool, you MUST provide the 'action' parameter.
    
    Actions:
    - 'create': Creates a new event. Requires 'name', 'description', and 'run_date_iso'.
    - 'list': Lists all scheduled events. Does not require other parameters.
    - 'update': Updates an existing event. Requires 'event_id' and at least one of name, description or run_date_iso.
    - 'delete': Deletes an event. Requires 'event_id'.
    """
    if action == "list":
        return list_events()
    
    elif action == "create":
        if not all([name, description, run_date_iso]):
            return "Error: To create an event, you must provide 'name', 'description', and 'run_date_iso'."
        return create_event(name, description, run_date_iso)
        
    elif action == "update":
        if not event_id:
            return "Error: To update an event, you must provide the 'event_id'."
        return update_event(event_id, name, description, run_date_iso)
        
    elif action == "delete":
        if not event_id:
            return "Error: To delete an event, you must provide the 'event_id'."
        return delete_event(event_id)
        
    else:
        return f"Error: Invalid action '{action}'. Please use one of 'create', 'list', 'update', 'delete'."