from typing import List, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool
from app.impl.google_tools_impl import (
    list_calendar_events_impl,
    stage_calendar_event_impl,
    commit_calendar_event_impl,
    delete_calendar_event_impl 
)

class ListEventsArgs(BaseModel):
    """Arguments for listing calendar events"""
    max_results: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of upcoming events to fetch (1-20)"
    )

class StageEventArgs(BaseModel):
    """Arguments for staging a calendar event"""
    summary: str = Field(..., description="Event title/summary")
    start_time: str = Field(
        ...,
        description="Start time in natural language (e.g., 'tomorrow at 3pm', '2024-01-15 14:00')"
    )
    end_time: str = Field(
        ...,
        description="End time in natural language"
    )
    description: str = Field(
        default="",
        description="Optional event description/agenda"
    )
    attendees: Optional[List[str]] = Field(
        default=None,
        description="List of attendee email addresses"
    )

class CommitEventArgs(BaseModel):
    """Arguments for committing a staged event"""
    confirm: str = Field(
        default="yes",
        description="Confirmation flag (always 'yes' when user confirms)"
    )

class DeleteEventArgs(BaseModel):
    """Arguments for deleting a calendar event"""
    event_id: str = Field(
        ...,
        description="The unique ID of the event to delete (get this from google_calendar_list first)"
    )


google_calendar_list = StructuredTool.from_function(
    func=list_calendar_events_impl,
    name="google_calendar_list",
    description=(
        "List the user's upcoming Google Calendar events. "
        "Returns event titles, dates, times, and IDs."
    ),
    args_schema=ListEventsArgs
)

google_calendar_stage = StructuredTool.from_function(
    func=stage_calendar_event_impl,
    name="google_calendar_stage",
    description=(
        "STEP 1 of 2: Draft a Google Calendar event. "
        "This validates the details and stores them for confirmation. "
        "After calling this, show the draft to the user and ask for confirmation."
    ),
    args_schema=StageEventArgs
)

google_calendar_commit = StructuredTool.from_function(
    func=commit_calendar_event_impl,
    name="google_calendar_commit",
    description=(
        "STEP 2 of 2: Create the staged event in Google Calendar. "
        "ONLY call this after the user explicitly confirms (says 'yes', 'confirm', 'do it', etc.). "
        "Do NOT ask for event details again - they are already stored from the stage step."
    ),
    args_schema=CommitEventArgs
)

google_calendar_delete = StructuredTool.from_function(
    func=delete_calendar_event_impl,
    name="google_calendar_delete",
    description=(
        "Delete an event from Google Calendar. "
        "You MUST first call `google_calendar_list` to find the correct `event_id`. "
        "Ask for user confirmation before deleting."
    ),
    args_schema=DeleteEventArgs
)

google_calendar_tools = [
    google_calendar_list,
    google_calendar_stage,
    google_calendar_commit,
    google_calendar_delete 
]