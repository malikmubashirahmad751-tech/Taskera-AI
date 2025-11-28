import asyncio
from typing import Literal, Optional
from pydantic.v1 import BaseModel, Field
from langchain_core.tools import StructuredTool
from app.core.logger import logger
from app.mcp_client import call_mcp

class ScheduleTaskArgs(BaseModel):
    """Arguments for scheduling research tasks"""
    query: str = Field(
        ...,
        description="The research query to execute at the scheduled time"
    )
    run_date_iso: str = Field(
        ...,
        description=(
            "When to run the task. "
            "Use natural language like 'tomorrow at 3pm', 'next Monday 10am', "
            "or ISO format '2024-01-15T14:00:00'"
        )
    )

async def _schedule_research_task_proxy(query: str, run_date_iso: str) -> str:
    """Proxy to MCP server for scheduling research tasks"""
    logger.info(f"[Scheduler] Scheduling research: '{query}' at {run_date_iso}")
    
    try:
        result = await call_mcp("schedule_research_task", {
            "query": query,
            "run_date_iso": run_date_iso
        })
        return str(result)
        
    except Exception as e:
        logger.error(f"[Scheduler] Error: {e}")
        return f"Failed to schedule task: {str(e)}"

schedule_research_task = StructuredTool.from_function(
    name="schedule_research_task",
    coroutine=_schedule_research_task_proxy,
    args_schema=ScheduleTaskArgs,
    description=(
        "Schedule a web search/research task to run at a specific date and time. "
        "The results will be logged when the task executes. "
        "Useful for: periodic monitoring, reminder-based searches, delayed information gathering."
    )
)


Action = Literal["create", "list", "update", "delete"]

class ManageEventsArgs(BaseModel):
    """Arguments for managing internal calendar events"""
    action: Action = Field(
        ...,
        description="Action to perform: 'create', 'list', 'update', or 'delete'"
    )
    name: Optional[str] = Field(
        default="Unnamed Event",
        description="Event name/title"
    )
    date_expression: Optional[str] = Field(
        default=None,
        description="When the event occurs (natural language or ISO format)"
    )
    description: Optional[str] = Field(
        default=None,
        description="Optional event description"
    )
    job_id: Optional[str] = Field(
        default=None,
        description="Event ID (required for update/delete operations)"
    )

async def _manage_calendar_events_proxy(
    action: Action,
    name: Optional[str] = "Unnamed Event",
    date_expression: Optional[str] = None,
    description: Optional[str] = None,
    job_id: Optional[str] = None
) -> str:
    """Proxy to MCP server for calendar event management"""
    logger.info(f"[Calendar] Managing event: action={action}, name={name}")
    
    try:
        result = await call_mcp("manage_calendar_events", {
            "action": action,
            "name": name,
            "date_expression": date_expression,
            "description": description,
            "job_id": job_id
        })
        
        if isinstance(result, dict):
            if result.get("status") == "success":
                if action == "list":
                    events = result.get("events", [])
                    if not events:
                        return "No events found."
                    
                    formatted = ["**Your Events:**"]
                    for event in events:
                        formatted.append(
                            f"- {event.get('name')} on {event.get('run_date')} "
                            f"(ID: {event.get('id')})"
                        )
                    return "\n".join(formatted)
                
                return result.get("message", "Operation successful")
            
            elif "error" in result:
                return f"Error: {result['error']}"
        
        return str(result)
        
    except Exception as e:
        logger.error(f"[Calendar] Error: {e}")
        return f"Failed to manage event: {str(e)}"

manage_calendar_events = StructuredTool.from_function(
    name="manage_calendar_events",
    coroutine=_manage_calendar_events_proxy,
    args_schema=ManageEventsArgs,
    description=(
        "Manage internal calendar events (NOT Google Calendar - use google_calendar_* tools for that). "
        "This is for simple reminders and scheduled tasks stored in the application database. "
        "Actions: create, list, update, delete."
    )
)