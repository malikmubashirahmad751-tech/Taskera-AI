from typing import List, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool
from app.impl.google_tools_impl import list_calendar_events_impl, create_calendar_event_impl

class ListEventsArgs(BaseModel):
    max_results: int = Field(5, description="Number of events to fetch.")

class ScheduleEventArgs(BaseModel):
    summary: str = Field(..., description="Title of the event.")
    start_time: str = Field(..., description="ISO format start time (YYYY-MM-DDTHH:MM:SS).")
    end_time: str = Field(..., description="ISO format end time.")
    description: str = Field("", description="Description.")
    attendees: Optional[List[str]] = Field(None, description="Attendee emails.")

google_calendar_tools = [
    StructuredTool.from_function(
        func=list_calendar_events_impl,
        name="google_calendar_list",
        description="List upcoming events on the user's Google Calendar.",
        args_schema=ListEventsArgs
    ),
    StructuredTool.from_function(
        func=create_calendar_event_impl,
        name="google_calendar_schedule",
        description="Schedule a new event on the user's Google Calendar.",
        args_schema=ScheduleEventArgs
    )
]