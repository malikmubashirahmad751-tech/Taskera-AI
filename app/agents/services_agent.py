import asyncio
from typing import Literal, Optional
from pydantic.v1 import BaseModel, Field
from langchain_core.tools import StructuredTool
from app.core.logger import logger
from app.mcp_client import call_mcp
from app.core.context import get_current_user_id

class ScheduleTaskArgs(BaseModel):
    """Arguments for scheduling research tasks"""
    query: str = Field(..., description="The research query to execute")
    run_date_iso: str = Field(
        ...,
        description="ISO 8601 formatted date/time (e.g. '2025-10-15T14:30:00')"
    )

async def _schedule_research_task_proxy(query: str, run_date_iso: str) -> str:
    """Proxy to MCP server for scheduling research tasks"""
    logger.info(f"[Scheduler] Scheduling research: '{query}' at {run_date_iso}")
    
    user_id = get_current_user_id()
    params = {
        "query": query,
        "run_date_iso": run_date_iso
    }
    if user_id:
        params["user_id"] = user_id

    try:
        return await call_mcp("schedule_research_task", params)
    except Exception as e:
        logger.error(f"[Scheduler] Error: {e}")
        return f"Failed to schedule task: {str(e)}"

schedule_research_task = StructuredTool.from_function(
    name="schedule_research_task",
    coroutine=_schedule_research_task_proxy,
    args_schema=ScheduleTaskArgs,
    description="Schedule a background research task. The system will auto-execute this at the specified time."
)

Action = Literal["create", "list", "update", "delete"]

class ManageEventsArgs(BaseModel):
    """Arguments for managing internal calendar events"""
    action: Action = Field(..., description="The action to perform: 'create', 'list', 'update', or 'delete'.")
    title: Optional[str] = Field(default="Unnamed Event", description="Event Title (Required for 'create')")
    start_time: Optional[str] = Field(
        default=None,
        description="ISO 8601 Start Time (Required for 'create'). Example: '2025-12-25T14:00:00'"
    )
    description: Optional[str] = Field(default=None, description="Event description")
    event_id: Optional[str] = Field(default=None, description="The Event ID (REQUIRED for 'delete' and 'update' actions).")

async def _manage_calendar_events_proxy(
    action: Action,
    title: Optional[str] = "Unnamed Event",
    start_time: Optional[str] = None,
    description: Optional[str] = None,
    event_id: Optional[str] = None
) -> str:
    """Proxy to MCP server for Supabase calendar management"""
    
    user_id = get_current_user_id()
    params = {
        "action": action,
        "title": title,
        "start_time": start_time,
        "description": description,
        "event_id": event_id
    }
    if user_id:
        params["user_id"] = user_id

    try:
        result = await call_mcp("manage_calendar_events", params)
        if isinstance(result, dict) and "message" in result:
            return result["message"]
        return str(result)
    except Exception as e:
        logger.error(f"[Calendar] Error: {e}")
        return f"Failed to manage event: {str(e)}"

manage_calendar_events = StructuredTool.from_function(
    name="manage_calendar_events",
    coroutine=_manage_calendar_events_proxy,
    args_schema=ManageEventsArgs,
    description="Manage the user's personal calendar in Supabase. Use this tool to CREATE new events, LIST upcoming schedules, UPDATE details, or DELETE events by ID."
)