from datetime import datetime
from app.core.database import supabase
from app.core.logger import logger
from app.services.scheduler import add_new_task, remove_task, run_research_task

def create_event(name: str, description: str, run_date: str):
    """
    Create event in database and schedule it
    """
    if not supabase:
        logger.warning("[Calendar] Database not available")
        return {"error": "Database unavailable"}
    
    try:
        run_dt = datetime.fromisoformat(run_date)
        
        response = supabase.table("events").insert({
            "name": name,
            "description": description,
            "run_date": run_dt.isoformat(),
            "status": "scheduled"
        }).execute()
        
        if not response.data or not isinstance(response.data, list):
            raise ValueError("No event returned from database")
        
        new_event = response.data[0]
        event_id = str(new_event["id"])
        
        add_new_task(
            func=run_research_task,
            job_id=event_id,
            trigger="date",
            run_date=run_dt,
            args=[name]
        )
        
        logger.info(f"[Calendar] Event created: {name} (ID: {event_id})")
        return new_event
        
    except Exception as e:
        logger.error(f"[Calendar] Create error: {e}", exc_info=True)
        return {"error": str(e)}

def list_events():
    """
    List all events from database
    """
    if not supabase:
        return []
    
    try:
        result = supabase.table("events")\
            .select("*")\
            .order("run_date")\
            .execute()
        
        return result.data or []
        
    except Exception as e:
        logger.error(f"[Calendar] List error: {e}")
        return []

def update_event(
    event_id: str,
    name: str = None,
    description: str = None,
    run_date: str = None
):
    """
    Update event in database and reschedule if needed
    """
    if not supabase:
        return {"error": "Database unavailable"}
    
    try:
        update_data = {}
        
        if name:
            update_data["name"] = name
        if description:
            update_data["description"] = description
        
        current_event = supabase.table("events")\
            .select("name")\
            .eq("id", event_id)\
            .single()\
            .execute()
        
        current_name = name or (
            current_event.data.get("name") if current_event.data else "Unnamed"
        )
        
        if run_date:
            run_dt = datetime.fromisoformat(run_date)
            update_data["run_date"] = run_dt.isoformat()
            
            remove_task(event_id)
            add_new_task(
                func=run_research_task,
                job_id=event_id,
                trigger="date",
                run_date=run_dt,
                args=[current_name]
            )
        
        supabase.table("events")\
            .update(update_data)\
            .eq("id", event_id)\
            .execute()
        
        logger.info(f"[Calendar] Event {event_id} updated")
        return {"status": "success", "event_id": event_id}
        
    except Exception as e:
        logger.error(f"[Calendar] Update error: {e}", exc_info=True)
        return {"error": str(e)}

def delete_event(event_id: str):
    """
    Delete event from database and cancel scheduled task
    """
    if not supabase:
        return {"error": "Database unavailable"}
    
    try:
        supabase.table("events")\
            .delete()\
            .eq("id", event_id)\
            .execute()
        
        remove_task(event_id)
        
        logger.info(f"[Calendar] Event {event_id} deleted")
        return {"status": "success"}
        
    except Exception as e:
        logger.error(f"[Calendar] Delete error: {e}", exc_info=True)
        return {"error": str(e)}