import json
import os
import dateparser
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Any, Dict

import google.oauth2.credentials
import google.auth.transport.requests
from googleapiclient.discovery import build

from app.core.logger import logger
from app.core.config import settings
from app.core.crud import get_refresh_token
from app.core.context import get_current_user_id


_EVENT_DRAFTS: Dict[str, Dict] = {}

def _save_draft(user_id: str, event_data: Dict):
    _EVENT_DRAFTS[user_id] = event_data

def _get_draft(user_id: str) -> Optional[Dict]:
    return _EVENT_DRAFTS.get(user_id)

def _clear_draft(user_id: str):
    if user_id in _EVENT_DRAFTS:
        del _EVENT_DRAFTS[user_id]

def _get_authenticated_service() -> Tuple[Optional[Any], Optional[str]]:
    user_id = get_current_user_id()
    if not user_id: return None, "System Error: No user context found."

    token = get_refresh_token(user_id)
    if not token:
        return None, "Authentication required. Please log in via Google."

    try:
        creds = google.oauth2.credentials.Credentials(
            token=None,
            refresh_token=token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            scopes=["https://www.googleapis.com/auth/calendar"]
        )
        request = google.auth.transport.requests.Request()
        creds.refresh(request)
        return build('calendar', 'v3', credentials=creds), None
    except Exception as e:
        logger.error(f"[Google] Auth failed for {user_id}: {e}")
        return None, f"Google Authorization failed: {str(e)}. Please log in again."


def list_calendar_events_impl(max_results: int = 5) -> str:
    service, error = _get_authenticated_service()
    if error: return error

    try:
        now = datetime.now(timezone.utc).isoformat()
        events_result = service.events().list(
            calendarId='primary', timeMin=now,
            maxResults=max_results, singleEvents=True, orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        if not events: return "No upcoming events found."

        output = ["**Your Upcoming Events:**"]
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            summary = event.get('summary', 'No Title')
            output.append(f"- {summary} at {start}")
        return "\n".join(output)
    except Exception as e:
        return f"Error accessing calendar: {str(e)}"

def stage_calendar_event_impl(summary: str, start_time: str, end_time: str, description: str = "", attendees: List[str] = None) -> str:
    """
    Validates event details and saves them to the server-side draft store.
    """
    user_id = get_current_user_id()
    if not user_id:
        return "Error: Could not identify user context."

    try:
        settings = {'PREFER_DATES_FROM': 'future'}
        start_dt = dateparser.parse(start_time, settings=settings)
        end_dt = dateparser.parse(end_time, settings=settings)
        
        if not start_dt or not end_dt:
            return f"Error: Could not understand dates '{start_time}' or '{end_time}'. Please provide ISO format."
            
    except Exception as e:
        return f"Date parsing error: {str(e)}"

    event_data = {
        "summary": summary,
        "description": description,
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat(),
        "attendees": attendees or []
    }
    
    _save_draft(user_id, event_data)
    
    readable_start = start_dt.strftime('%A, %B %d at %I:%M %p')
    attendee_str = f"with {', '.join(attendees)}" if attendees else ""
    
    return (
        f"SUCCESS: I have drafted the event '{summary}' for {readable_start} {attendee_str}.\n"
        f"Action Required: Ask the user to confirm. If they say 'Yes', simply call 'google_calendar_commit'."
    )

def commit_calendar_event_impl(confirm: str = "yes") -> str:
    """
    Retrieves the drafted event for the current user and executes the API call.
    Accepts a 'confirm' argument to satisfy tool schema requirements, but ignores it.
    """
    user_id = get_current_user_id()
    if not user_id: return "Error: No user context."

    event_data = _get_draft(user_id)
    if not event_data:
        return "Error: No pending event found. Please ask the user to provide the meeting details again."

    service, error = _get_authenticated_service()
    if error: return error

    try:
        api_body = {
            'summary': event_data['summary'],
            'description': event_data.get('description', ''),
            'start': {'dateTime': event_data['start'], 'timeZone': 'UTC'},
            'end': {'dateTime': event_data['end'], 'timeZone': 'UTC'},
        }
        if event_data.get('attendees'):
            api_body['attendees'] = [{'email': a} for a in event_data['attendees']]

        event = service.events().insert(calendarId='primary', body=api_body).execute()
        
        _clear_draft(user_id)
        
        return f"Confirmed! Event created successfully: {event.get('htmlLink')}"
    except Exception as e:
        logger.error(f"Calendar API Error: {e}")
        return f"Failed to create event in Google Calendar: {str(e)}"