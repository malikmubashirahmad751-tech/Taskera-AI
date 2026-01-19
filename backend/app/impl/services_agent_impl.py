import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
from app.core.database import supabase
from app.core.logger import logger
from app.core.context import get_current_user_id

async def list_schedules_internal(user_id: str) -> str:
    """List events from Supabase for a user."""
    if not supabase:
        return "Database unavailable. Cannot retrieve events."
    
    try:
        now = datetime.now(timezone.utc).isoformat()
        response = supabase.table("events")\
            .select("*")\
            .eq("user_id", user_id)\
            .gte("start_time", now)\
            .order("start_time", desc=False)\
            .limit(20)\
            .execute()
            
        events = response.data
        if not events or len(events) == 0:
            return "No upcoming events found in your calendar."

        output = ["**Upcoming Events:**\n"]
        for event in events:
            event_id = event.get('id', 'unknown')
            title = event.get('title', 'Untitled')
            start_raw = event.get('start_time', '')
            status = event.get('status', 'pending')
            description = event.get('description', '')
            
            try:
                start_dt = datetime.fromisoformat(start_raw.replace('Z', ''))
                formatted_time = start_dt.strftime('%Y-%m-%d %H:%M')
            except:
                formatted_time = start_raw
            
            output.append(f" **{title}**")
            output.append(f"   Time: {formatted_time}")
            output.append(f"   Status: {status.upper()}")
            output.append(f"   ID: `{event_id}`")
            if description and len(description) > 0:
                desc_preview = description[:100] + "..." if len(description) > 100 else description
                output.append(f"   Note: {desc_preview}")
            output.append("")
            
        return "\n".join(output)
        
    except Exception as e:
        logger.error(f"[Calendar] List Error: {e}", exc_info=True)
        return f"Error retrieving schedule: {str(e)}"

async def manage_calendar_events_impl(
    action: str, 
    title: Optional[str] = None, 
    start_time: Optional[str] = None, 
    description: Optional[str] = "",
    event_id: Optional[str] = None,
    user_id: Optional[str] = None  
) -> str:
    """
    Implementation for Supabase Calendar Management
    """
    if not supabase:
        return "Database unavailable. Calendar features are disabled."
    
    user_id = user_id or get_current_user_id()
    
    if not user_id or user_id == "unknown": 
        return "Error: No user logged in. Please authenticate first."

    try:
        action = action.lower().strip()
        
        if action == "list":
            return await list_schedules_internal(user_id)

        elif action == "create":
            if not title or not start_time:
                return "Error: Both 'title' and 'start_time' are required to create an event."
            
            try:
                start_time_clean = start_time.replace('Z', '').strip()
                dt_start = datetime.fromisoformat(start_time_clean)
                
                if dt_start.tzinfo is None:
                    dt_start = dt_start.replace(tzinfo=timezone.utc)
                
                dt_end = dt_start + timedelta(hours=1)
                
                start_time_iso = dt_start.isoformat()
                end_time_iso = dt_end.isoformat()
                
            except ValueError as ve:
                logger.error(f"[Calendar] Invalid datetime format: {start_time}")
                return f"Error: Invalid date/time format. Use ISO 8601 format (YYYY-MM-DDTHH:MM:SS). Example: 2025-12-25T14:00:00"

            data = {
                "user_id": user_id,
                "title": title.strip(),
                "description": description.strip() if description else "",
                "start_time": start_time_iso,
                "end_time": end_time_iso,
                "status": "pending"
            }
            
            logger.info(f"[Calendar] Creating event for user {user_id}: {title} at {start_time_iso}")
            
            try:
                res = supabase.table("events").insert(data).execute()
                
                if res.data and len(res.data) > 0:
                    created_event = res.data[0]
                    event_id = created_event.get('id')
                    logger.info(f"[Calendar] Event created successfully: {event_id}")
                    return f"Event **'{title}'** scheduled for {dt_start.strftime('%Y-%m-%d %H:%M')} UTC\nEvent ID: `{event_id}`"
                else:
                    logger.error(f"[Calendar] Insert returned no data")
                    return "Error: Event creation failed (no data returned from database)."
                    
            except Exception as db_error:
                logger.error(f"[Calendar] Database insert error: {db_error}", exc_info=True)
                return f"Database error: {str(db_error)}"

        elif action == "update":
            if not event_id:
                return "Error: 'event_id' is required for updating an event."
            
            update_data = {}
            if title:
                update_data['title'] = title.strip()
            if description is not None:
                update_data['description'] = description.strip()
            if start_time:
                try:
                    start_time_clean = start_time.replace('Z', '').strip()
                    dt_start = datetime.fromisoformat(start_time_clean)
                    if dt_start.tzinfo is None:
                        dt_start = dt_start.replace(tzinfo=timezone.utc)
                    dt_end = dt_start + timedelta(hours=1)
                    update_data['start_time'] = dt_start.isoformat()
                    update_data['end_time'] = dt_end.isoformat()
                except ValueError:
                    return "Error: Invalid date/time format for start_time."
            
            if not update_data:
                return "Error: No fields provided to update."
            
            logger.info(f"[Calendar] Updating event {event_id} for user {user_id}")
            
            try:
                res = supabase.table("events").update(update_data)\
                    .eq("id", event_id)\
                    .eq("user_id", user_id)\
                    .execute()
                
                if res.data and len(res.data) > 0:
                    return f"Event **'{event_id}'** updated successfully."
                else:
                    return f"Event not found or you don't have permission to update it."
                    
            except Exception as db_error:
                logger.error(f"[Calendar] Update error: {db_error}", exc_info=True)
                return f"Update failed: {str(db_error)}"

        elif action == "delete":
            if not event_id:
                return "Error: 'event_id' is required for deletion."
            
            logger.info(f"[Calendar] Deleting event {event_id} for user {user_id}")
            
            try:
                res = supabase.table("events").delete()\
                    .eq("id", event_id)\
                    .eq("user_id", user_id)\
                    .execute()
                
                if res.data and len(res.data) > 0:
                    return f"Event **'{event_id}'** deleted successfully."
                else:
                    return f"Event not found or you don't have permission to delete it."
                    
            except Exception as db_error:
                logger.error(f"[Calendar] Delete error: {db_error}", exc_info=True)
                return f"Delete failed: {str(db_error)}"

        else:
            return f"Unknown action: '{action}'. Supported actions: create, list, update, delete"

    except Exception as e:
        logger.error(f"[Calendar] Implementation Error: {e}", exc_info=True)
        return f"System Error: {str(e)}"

async def schedule_research_task_impl(
    query: str, 
    run_date_iso: str, 
    user_id: Optional[str] = None 
) -> str:
    """
    Special wrapper to create a Research Task event
    """
    user_id = user_id or get_current_user_id()

    if not query or not query.strip():
        return "Error: Research query cannot be empty."
    
    if not run_date_iso or not run_date_iso.strip():
        return "Error: run_date_iso is required."
    
    logger.info(f"[Scheduler] Scheduling research task: '{query}' at {run_date_iso} for user {user_id}")
    
    title = f"Research Task: {query}"
    description = f"Automated research query: {query}\nScheduled via schedule_research_task tool."
    
    result = await manage_calendar_events_impl(
        action="create",
        title=title,
        start_time=run_date_iso,
        description=description,
        user_id=user_id 
    )
    
    return result