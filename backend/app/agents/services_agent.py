import dateparser
from datetime import datetime
from typing import Literal, Optional
from langchain_core.tools import tool
from app.core.logger import logger
from app.services.scheduler import add_new_task, correct_run_date
from app.services import scheduler_service

def run_research_task_wrapper(query: str):
    """Wrapper to run research task - imports search dynamically to avoid circular imports"""
    try:
        from app.agents.tools_agent import search_tool
        result = search_tool.invoke(query)
        logger.info(f"[Research] Task completed for query: '{query}'")
        return result
    except Exception as e:
        logger.error(f"[Research] Task failed for query '{query}': {e}")
        return f"Error: {e}"

@tool
def schedule_research_task(query: str, run_date_iso: str):
    """Schedules a research task for a specific date and time in ISO format."""
    try:
        run_date = datetime.fromisoformat(run_date_iso)
        run_date = correct_run_date(run_date)
        return add_new_task(
            func=run_research_task_wrapper,
            trigger='date',
            run_date=run_date,
            args=[query]
        )
    except ValueError:
        return "Error: Invalid date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)."
    except Exception as e:
        logger.error(f"Error scheduling research task: {e}")
        return f"An unexpected error occurred: {e}"

Action = Literal["create", "list", "update", "delete"]

@tool
def manage_calendar_events(
    action: Action,
    name: Optional[str] = "Unnamed Event",
    date_expression: Optional[str] = None,
    description: Optional[str] = None,
    job_id: Optional[str] = None
):
    """
    Manage calendar events (create, delete, update, list).

    Args:
        action: 'create', 'delete', 'update', or 'list'.
        name: (Optional) Event name/title.
        date_expression: (Optional) Natural language date/time (e.g. 'tomorrow at 3pm').
        description: (Optional) Event description.
        job_id: (Optional) Required for update/delete.
    """

    try:
        if action == "create":
            if not date_expression:
                return {"error": "Missing 'date_expression' for event creation."}

            run_date = dateparser.parse(
                date_expression,
                settings={
                    "PREFER_DATES_FROM": "future",
                    "RELATIVE_BASE": datetime.now(),
                    "DATE_ORDER": "DMY",
                }
            )
            if not run_date:
                raise ValueError(f"Could not parse date expression: '{date_expression}'")

            run_date = correct_run_date(run_date)
            new_event = scheduler_service.create_event(
                name=name,
                description=description or f"Event for {name}",
                run_date=run_date.isoformat()
            )

            if "error" in new_event:
                return new_event

            readable_date = run_date.strftime("%B %d, %Y at %I:%M %p")
            return {
                "status": "success",
                "message": f"Event '{name}' scheduled for {readable_date}.",
                "run_date": run_date.isoformat(),
                "job_id": new_event.get("id", "unknown")
            }

        elif action == "delete":
            if not job_id:
                return {"error": "Missing 'job_id' for delete action."}
            return scheduler_service.delete_event(event_id=job_id)

        elif action == "update":
            if not job_id:
                return {"error": "Missing 'job_id' for update action."}

            run_date_iso = None
            if date_expression:
                run_date = dateparser.parse(date_expression, settings={"PREFER_DATES_FROM": "future"})
                if run_date:
                    run_date = correct_run_date(run_date)
                    run_date_iso = run_date.isoformat()

            return scheduler_service.update_event(
                event_id=job_id,
                name=name if name != "Unnamed Event" else None,
                description=description,
                run_date=run_date_iso
            )

        elif action == "list":
            return {"status": "success", "events": scheduler_service.list_events()}

        else:
            return {"error": f"Unknown action '{action}'."}

    except Exception as e:
        logger.error(f"[Calendar] manage_calendar_events error: {e}", exc_info=True)
        return {"error": str(e)}