import os
from datetime import datetime,timedelta
from typing import Literal, Optional

# Third-Party Library Imports
from dotenv import load_dotenv
from supabase import create_client, Client
from langchain.tools import tool
from app.core.logger import logger
import dateparser
from app.services.scheduler import add_new_task, run_research_task, correct_run_date, remove_task


load_dotenv()

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

if not supabase_url or not supabase_key:
    raise ValueError("Supabase URL and Key must be set in your .env file")

try:
    supabase: Client = create_client(supabase_url, supabase_key)
except Exception as e:
    logger.error(f"Error creating Supabase client: {e}")

    raise

def create_event(name: str, description: str, run_date: str):
    """Create event in Supabase and schedule it locally."""
    try:
        run_dt = datetime.fromisoformat(run_date)
        response = supabase.table("events").insert({
            "name": name,
            "description": description,
            "run_date": run_dt.isoformat(),
            "status": "scheduled"
        }).execute()
        
        new_event = response.data[0]
        event_id = str(new_event['id']) 
        add_new_task(
            func=run_research_task, 
            job_id=event_id, 
            trigger="date", 
            run_date=run_dt, 
            args=[name]
        )
        logger.info(f"Event '{name}' (ID: {event_id}) created and scheduled for {run_dt}")
        return new_event
    except Exception as e:
        logger.error(f"Error creating event: {e}")
        return {"error": str(e)}

def list_events():
    """Fetch all events from Supabase."""
    try:
        result = supabase.table("events").select("*").order("run_date").execute()
        return result.data
    except Exception as e:
        logger.error(f"Error fetching events: {e}")
        return []


def update_event(event_id: str, name=None, description=None, run_date=None):
    """Update event details."""
    try:
        update_data = {}
        if name: update_data["name"] = name
        if description: update_data["description"] = description
        if run_date: 
            run_dt = datetime.fromisoformat(run_date)
            update_data["run_date"] = run_dt.isoformat()
 
            remove_task(event_id)
            add_new_task(run_research_task, job_id=event_id, trigger="date", run_date=run_dt, args=[name or "Scheduled Task"])

        result = supabase.table("events").update(update_data).eq("id", event_id).execute()
        logger.info(f"Event {event_id} updated.")
        return result.data
    except Exception as e:
        logger.error(f"Error updating event: {e}")
        return {"error": str(e)}


def delete_event(event_id: str):
    """Delete event from Supabase and remove the scheduled task."""
    try:
        result = supabase.table("events").delete().eq("id", event_id).execute()

        remove_task(job_id=event_id)
        logger.info(f"Event {event_id} deleted from Supabase and scheduler.")
        return result.data
    except Exception as e:
        logger.error(f"Error deleting event: {e}")
        return {"error": str(e)}



Action = Literal["create", "list", "update", "delete"]

@tool
def manage_calendar_events(params: dict):
    """
    Manage calendar events (create, delete, etc.) for meetings or reminders.

    Expected keys for 'create' action:
        - action: 'create'
        - name: event name/title
        - date_expression: natural or ISO-style date/time string (e.g., 'tomorrow at 3pm', 'next week', '2025-11-05 09:00:00')
        - description: optional
        - job_id: optional custom ID
    """
    action = params.get("action")
    name = params.get("name", "Unnamed Event")
    date_expression = params.get("date_expression")
    job_id = params.get("job_id") or f"job_{name.replace(' ', '_').lower()}_{datetime.now().strftime('%f')}"

    if not action:
        logger.error("❌ No action specified for manage_calendar_events.")
        return {"error": "Missing 'action' parameter."}

    if action == "create":
        if not date_expression:
            logger.error("❌ Missing 'date_expression' for event creation.")
            return {"error": "Missing 'date_expression' to schedule the event."}

        try:
        
            run_date = dateparser.parse(
                date_expression,
                settings={
                    'PREFER_DATES_FROM': 'future',
                    'RELATIVE_BASE': datetime.now(),
                    'DATE_ORDER': 'DMY',
                    'RETURN_AS_TIMEZONE_AWARE': False
                }
            )

            if not run_date:
                raise ValueError(f"Could not parse date expression: '{date_expression}'")

            now = datetime.now()

          
            if run_date < now:
                logger.warning(f"⚠ Date parsed in the past ({run_date}), correcting to next occurrence.")
                run_date = run_date.replace(year=now.year)
                if run_date < now:
                    run_date = run_date.replace(year=now.year + 1)

        
            if run_date < now:
                run_date = now + timedelta(days=1)
                run_date = run_date.replace(hour=10, minute=0, second=0, microsecond=0)

     
            add_new_task(
                func=run_research_task,
                trigger="date",
                run_date=run_date,
                args=[name],
                job_id=job_id
            )

            readable_date = run_date.strftime("%B %d, %Y at %I:%M %p")
            logger.info(f" Created event '{name}' for {readable_date}")

            return {
                "status": "success",
                "message": f"The event '{name}' has been scheduled for {readable_date}.",
                "run_date": run_date.isoformat(),
                "job_id": job_id
            }

        except Exception as e:
            logger.exception(f" Error creating event: {e}")
            return {"error": f"Failed to parse and schedule event: {str(e)}"}

    elif action == "delete":
        from app.services.scheduler import remove_task
        job_id = params.get("job_id")

        if not job_id:
            return {"error": "Missing 'job_id' for delete action."}

        try:
            remove_task(job_id)
            logger.info(f"🗑 Deleted event '{name}' (job_id={job_id})")
            return {
                "status": "success",
                "message": f"Event '{name}' deleted successfully."
            }

        except Exception as e:
            logger.exception(f" Error deleting event: {e}")
            return {"error": str(e)}
    else:
        logger.error(f" Unknown action '{action}' provided.")
        return {"error": f"Unknown action '{action}'."}