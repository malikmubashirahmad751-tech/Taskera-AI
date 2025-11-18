from typing import List, Optional
from pydantic.v1 import BaseModel, Field
from langchain_core.tools import StructuredTool
from app.mcp_client import call_mcp


class ListEventsArgs(BaseModel):
    max_results: int = Field(10, description="The number of upcoming events to fetch.")
    time_min_iso: Optional[str] = Field(None, description="ISO timestamp to start listing from (e.g. '2024-11-20T09:00:00Z'). Defaults to now.")

class ScheduleEventArgs(BaseModel):
    summary: str = Field(..., description="Title of the meeting or event.")
    start_time: str = Field(..., description="Start time in ISO format (YYYY-MM-DDTHH:MM:SS).")
    end_time: str = Field(..., description="End time in ISO format (YYYY-MM-DDTHH:MM:SS).")
    description: str = Field("", description="Description or agenda for the event.")
    attendees: Optional[List[str]] = Field(None, description="List of email addresses to invite.")


def create_google_calendar_tools(user_id: str) -> List[StructuredTool]:
    """
    Returns the suite of Calendar tools bound to a specific user_id.
    """
    
    async def list_events_proxy(max_results: int = 10, time_min_iso: Optional[str] = None):
        return await call_mcp("google_calendar_list", {
            "user_id": user_id, 
            "max_results": max_results,
            "time_min_iso": time_min_iso
        })

    async def schedule_event_proxy(summary: str, start_time: str, end_time: str, description: str = "", attendees: List[str] = None):
        return await call_mcp("google_calendar_create", {
            "user_id": user_id,
            "summary": summary,
            "start_time": start_time,
            "end_time": end_time,
            "description": description,
            "attendees": attendees
        })

    return [
        StructuredTool.from_function(
            name="google_calendar_list",
            coroutine=list_events_proxy,
            args_schema=ListEventsArgs,
            description="View the user's calendar to check for conflicts or upcoming events."
        ),
        StructuredTool.from_function(
            name="google_calendar_schedule",
            coroutine=schedule_event_proxy,
            args_schema=ScheduleEventArgs,
            description="Add a new event/meeting to the user's Google Calendar."
        )
    ]