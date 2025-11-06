import os
from datetime import datetime,timedelta
from typing import Literal, Optional

from dotenv import load_dotenv
from supabase import create_client, Client
from langchain_core.tools import tool
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
    """
    Create event in Supabase AND schedule it locally.
    This is the single function for creating events.
    """
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
    """Update event details in Supabase and reschedule the job."""
    try:
        update_data = {}
        if name: update_data["name"] = name
        if description: update_data["description"] = description
        
        current_name = name or supabase.table("events").select("name").eq("id", event_id).single().execute().data['name']

        if run_date: 
            run_dt = datetime.fromisoformat(run_date)
            update_data["run_date"] = run_dt.isoformat()
 
            remove_task(event_id)
            add_new_task(run_research_task, job_id=event_id, trigger="date", run_date=run_dt, args=[current_name])

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
def manage_calendar_events(
    action: Action,
    name: Optional[str] = "Unnamed Event",
    date_expression: Optional[str] = None,
    description: Optional[str] = None,
    job_id: Optional[str] = None
):
    """
    Manage calendar events (create, delete, etc.) for meetings or reminders.

    Args:
        action: The action to perform: 'create', 'delete', 'update', or 'list'.
        name: (Optional) The event name/title. Defaults to 'Unnamed Event'.
        date_expression: (Optional) Required for 'create'. Natural or ISO-style date/time (e.g., 'tomorrow at 3pm').
        description: (Optional) A description for the event. (Used in 'create')
        job_id: (Optional) A specific ID for the event. Required for 'delete' or 'update'.
    """
    
    if action == "create":
        if not date_expression:
            logger.error(" Missing 'date_expression' for event creation.")
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

            run_date = correct_run_date(run_date) 

            new_event_or_error = create_event(
                name=name,
                description=description or f"Event for {name}",
                run_date=run_date.isoformat() 
            )

            if "error" in new_event_or_error:
                raise Exception(new_event_or_error["error"])
            
            readable_date = run_date.strftime("%B %d, %Y at %I:%M %p")
            logger.info(f" Created event '{name}' for {readable_date}")

            return {
                "status": "success",
                "message": f"The event '{name}' has been scheduled for {readable_date}.",
                "run_date": run_date.isoformat(),
                "job_id": new_event_or_error.get('id', 'unknown_id')
            }

        except Exception as e:
            logger.exception(f" Error creating event: {e}")
            return {"error": f"Failed to parse and schedule event: {str(e)}"}

    elif action == "delete":
        if not job_id:
            return {"error": "Missing 'job_id' for delete action."}
        try:
            delete_event(event_id=job_id)
            logger.info(f"🗑 Deleted event '{name}' (job_id={job_id})")
            return {
                "status": "success",
                "message": f"Event '{name}' deleted successfully."
            }
        except Exception as e:
            logger.exception(f" Error deleting event: {e}")
            return {"error": str(e)}
    
    elif action == "update":
        if not job_id:
            return {"error": "Missing 'job_id' for update action."}
        try:
            run_date_iso = None
            if date_expression:
                run_date = dateparser.parse(date_expression, settings={'PREFER_DATES_FROM': 'future'})
                run_date = correct_run_date(run_date)
                run_date_iso = run_date.isoformat()
            
            update_event(
                event_id=job_id,
                name=name if name != "Unnamed Event" else None,
                description=description,
                run_date=run_date_iso
            )
            return {"status": "success", "message": f"Event {job_id} updated."}
        except Exception as e:
            logger.exception(f" Error updating event: {e}")
            return {"error": str(e)}

    elif action == "list":
        try:
            events = list_events()
            return {"status": "success", "events": events}
        except Exception as e:
            logger.exception(f" Error listing events: {e}")
            return {"error": str(e)}

    else:
        logger.error(f" Unknown action '{action}' provided.")
        return {"error": f"Unknown action '{action}' provided."}