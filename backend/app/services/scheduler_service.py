import os
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client
from app.core.logger import logger
from app.services.scheduler import add_new_task, run_research_task, remove_task, correct_run_date, supabase

def create_event(name: str, description: str, run_date: str):
    """Create an event in Supabase and schedule it locally."""
    try:
        run_dt = datetime.fromisoformat(run_date)

        response = supabase.table("events").insert({
            "name": name,
            "description": description,
            "run_date": run_dt.isoformat(),
            "status": "scheduled"
        }).execute()

        if not response.data or not isinstance(response.data, list):
            raise ValueError("No event returned from Supabase insert.")

        new_event = response.data[0]
        event_id = str(new_event["id"])

        add_new_task(
            func=run_research_task,
            job_id=event_id,
            trigger="date",
            run_date=run_dt,
            args=[name] 
        )
        logger.info(f"[Calendar] Event '{name}' (ID: {event_id}) scheduled for {run_dt}")
        return new_event

    except Exception as e:
        logger.error(f"[Calendar] Error creating event: {e}", exc_info=True)
        return {"error": str(e)}


def list_events():
    """Fetch all events from Supabase."""
    try:
        result = supabase.table("events").select("*").order("run_date").execute()
        return result.data or []
    except Exception as e:
        logger.error(f"[Calendar] Error fetching events: {e}", exc_info=True)
        return []


def update_event(event_id: str, name=None, description=None, run_date=None):
    """Update event details in Supabase and reschedule the job if needed."""
    try:
        update_data = {}
        if name:
            update_data["name"] = name
        if description:
            update_data["description"] = description

        current_event = (
            supabase.table("events").select("name").eq("id", event_id).single().execute().data
        )
        current_name = name or (current_event.get("name") if current_event else "Unnamed Event")

        if run_date:
            run_dt = datetime.fromisoformat(run_date)
            update_data["run_date"] = run_dt.isoformat()

            remove_task(event_id)
            add_new_task(run_research_task, job_id=event_id, trigger="date", run_date=run_dt, args=[current_name])

        supabase.table("events").update(update_data).eq("id", event_id).execute()
        logger.info(f"[Calendar] Event {event_id} updated successfully.")
        return {"status": "success", "event_id": event_id}

    except Exception as e:
        logger.error(f"[Calendar] Error updating event: {e}", exc_info=True)
        return {"error": str(e)}


def delete_event(event_id: str):
    """Delete an event from Supabase and remove its scheduled task."""
    try:
        supabase.table("events").delete().eq("id", event_id).execute()
        remove_task(event_id)
        logger.info(f"[Calendar] Event {event_id} deleted successfully.")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"[Calendar] Error deleting event: {e}", exc_info=True)
        return {"error": str(e)}