from typing import List, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool
from app.impl.google_tools_impl import (
    list_calendar_events_impl, 
    stage_calendar_event_impl, 
    commit_calendar_event_impl
)

class ListEventsArgs(BaseModel):
    max_results: int = Field(5, description="Number of events to fetch.")

class StageEventArgs(BaseModel):
    summary: str = Field(..., description="Title of the event.")
    start_time: str = Field(..., description="Start time (e.g. 'tomorrow at 5pm').")
    end_time: str = Field(..., description="End time.")
    description: str = Field("", description="Agenda or details.")
    attendees: Optional[List[str]] = Field(None, description="List of attendee emails.")

class CommitEventArgs(BaseModel):
    
    confirm: str = Field("yes", description="Confirmation flag. Always pass 'yes'.")

google_calendar_tools = [
    StructuredTool.from_function(
        func=list_calendar_events_impl,
        name="google_calendar_list",
        description="List upcoming events on the user's Google Calendar.",
        args_schema=ListEventsArgs
    ),
    StructuredTool.from_function(
        func=stage_calendar_event_impl,
        name="google_calendar_stage",
        description="STEP 1: Draft a calendar event. Stores details in memory and returns a summary for user confirmation.",
        args_schema=StageEventArgs
    ),
    StructuredTool.from_function(
        func=commit_calendar_event_impl,
        name="google_calendar_commit",
        description="STEP 2: Finalize the drafted event. Call this ONLY after the user says 'Yes' to the draft.",
        args_schema=CommitEventArgs
    )
]