import dateparser
from datetime import datetime
from typing import Literal, Optional

from app.core.logger import logger
from app.services.scheduler import add_new_task, correct_run_date, run_research_task
from app.services import scheduler_service

def schedule_research_task_impl(query: str, run_date_iso: str) -> str:
    """
    Schedule a research task for a specific date/time
    """
    try:
        run_date = dateparser.parse(
            run_date_iso,
            settings={"PREFER_DATES_FROM": "future"}
        )
        
        if not run_date:
            return f"Could not understand date: '{run_date_iso}'. Try 'tomorrow at 3pm' or '2024-01-15 14:00'"
        
        run_date = correct_run_date(run_date)
        
        result = add_new_task(
            func=run_research_task,
            trigger='date',
            run_date=run_date,
            args=[query]
        )
        
        if "error" in result:
            return f" Failed to schedule: {result['error']}"
        
        formatted_date = run_date.strftime('%A, %B %d at %I:%M %p')
        return (
            f"Research task scheduled!\n\n"
            f"**Query:** {query}\n"
            f"**When:** {formatted_date}\n"
            f"**Job ID:** {result['job_id']}"
        )
        
    except ValueError as e:
        logger.warning(f"[Scheduler] Invalid date: {e}")
        return f" Invalid date format: {str(e)}"
        
    except Exception as e:
        logger.error(f"[Scheduler] Error: {e}", exc_info=True)
        return f" Scheduling error: {str(e)}"

Action = Literal["create", "list", "update", "delete"]

def manage_calendar_events_impl(
    action: Action,
    name: Optional[str] = "Unnamed Event",
    date_expression: Optional[str] = None,
    description: Optional[str] = None,
    job_id: Optional[str] = None
) -> dict:
    """
    Manage internal calendar events
    """
    try:
        if action == "create":
            if not date_expression:
                return {"error": "Missing 'date_expression' for event creation"}
            
            run_date = dateparser.parse(
                date_expression,
                settings={
                    "PREFER_DATES_FROM": "future",
                    "RELATIVE_BASE": datetime.now(),
                    "DATE_ORDER": "DMY"
                }
            )
            
            if not run_date:
                return {"error": f"Could not parse date: '{date_expression}'"}
            
            run_date = correct_run_date(run_date)
            
            new_event = scheduler_service.create_event(
                name=name,
                description=description or f"Event: {name}",
                run_date=run_date.isoformat()
            )
            
            if "error" in new_event:
                return new_event
            
            formatted_date = run_date.strftime('%B %d, %Y at %I:%M %p')
            
            return {
                "status": "success",
                "message": f" Event '{name}' scheduled for {formatted_date}",
                "run_date": run_date.isoformat(),
                "job_id": new_event.get("id", "unknown")
            }
        
        elif action == "delete":
            if not job_id:
                return {"error": "Missing 'job_id' for delete"}
            
            result = scheduler_service.delete_event(event_id=job_id)
            
            if result.get("status") == "success":
                return {"status": "success", "message": f" Event {job_id} deleted"}
            
            return result
        
        elif action == "update":
            if not job_id:
                return {"error": "Missing 'job_id' for update"}
            
            run_date_iso = None
            if date_expression:
                run_date = dateparser.parse(
                    date_expression,
                    settings={"PREFER_DATES_FROM": "future"}
                )
                if run_date:
                    run_date = correct_run_date(run_date)
                    run_date_iso = run_date.isoformat()
            
            result = scheduler_service.update_event(
                event_id=job_id,
                name=name if name != "Unnamed Event" else None,
                description=description,
                run_date=run_date_iso
            )
            
            if result.get("status") == "success":
                return {"status": "success", "message": f"Event {job_id} updated"}
            
            return result
        
        elif action == "list":
            events = scheduler_service.list_events()
            return {"status": "success", "events": events}
        
        else:
            return {"error": f"Unknown action: '{action}'"}
        
    except Exception as e:
        logger.error(f"[Calendar] Error: {e}", exc_info=True)
        return {"error": str(e)}