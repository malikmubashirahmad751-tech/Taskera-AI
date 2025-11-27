import json
import dateparser
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Any, Dict

import google.oauth2.credentials
import google.auth.transport.requests
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.core.logger import logger
from app.core.config import get_settings
from app.core.crud import get_refresh_token
from app.core.context import get_current_user_id

settings = get_settings()

_EVENT_DRAFTS: Dict[str, Dict] = {}

def _save_draft(user_id: str, event_data: Dict):
    _EVENT_DRAFTS[user_id] = event_data
    logger.debug(f"[Google] Draft saved for {user_id}")

def _get_draft(user_id: str) -> Optional[Dict]:
    return _EVENT_DRAFTS.get(user_id)

def _clear_draft(user_id: str):
    if user_id in _EVENT_DRAFTS:
        del _EVENT_DRAFTS[user_id]

def _get_authenticated_service() -> Tuple[Optional[Any], Optional[str]]:
    user_id = get_current_user_id()
    if not user_id: return None, "System error: No user context found"
    
    token = get_refresh_token(user_id)
    if not token:
        return None, "Google Calendar not connected. Please authenticate via the 'Continue with Google' button."
    
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
        service = build('calendar', 'v3', credentials=creds)
        return service, None
    except Exception as e:
        logger.error(f"[Google] Auth failed for {user_id}: {e}")
        return None, f"Authentication failed: {str(e)}"


def list_calendar_events_impl(max_results: int = 5) -> str:
    """
    List upcoming events from user's Google Calendar.
    Updated to return Event IDs for deletion logic.
    """
    service, error = _get_authenticated_service()
    if error: return error
    
    try:
        now = datetime.now(timezone.utc).isoformat()
        
        events_result = service.events().list(
            calendarId='primary',
            timeMin=now,
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        if not events:
            return "No upcoming events found on your calendar."
        
        output = ["**Your Upcoming Events:**"]
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            summary = event.get('summary', 'No Title')
            event_id = event.get('id') 
            
            try:
                dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                formatted_time = dt.strftime('%A, %B %d at %I:%M %p')
            except:
                formatted_time = start
            
            event_str = f"- **{summary}** on {formatted_time} (ID: `{event_id}`)"
            output.append(event_str)
        
        return "\n".join(output)
        
    except HttpError as e:
        logger.error(f"[Google] List error: {e}")
        return f"Failed to fetch events: {e.reason}"
    except Exception as e:
        logger.error(f"[Google] Unexpected error: {e}")
        return f"Error accessing calendar: {str(e)}"

def stage_calendar_event_impl(
    summary: str,
    start_time: str,
    end_time: str,
    description: str = "",
    attendees: List[str] = None
) -> str:
    """Stage (draft) a calendar event for user confirmation"""
    user_id = get_current_user_id()
    if not user_id: return "Error: Could not identify user context"
    
    try:
        parse_settings = {'PREFER_DATES_FROM': 'future', 'RETURN_AS_TIMEZONE_AWARE': True}
        start_dt = dateparser.parse(start_time, settings=parse_settings)
        end_dt = dateparser.parse(end_time, settings=parse_settings)
        
        if not start_dt: return f"Invalid start time: '{start_time}'"
        if not end_dt: return f"Invalid end time: '{end_time}'"
        if end_dt <= start_dt: return "End time must be after start time"
        
        event_data = {
            "summary": summary,
            "description": description,
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
            "attendees": attendees or []
        }
        
        _save_draft(user_id, event_data)
        
        readable_start = start_dt.strftime('%A, %B %d at %I:%M %p')
        readable_end = end_dt.strftime('%I:%M %p')
        
        return (
            f"✓ Event drafted:\n**{summary}**\n"
            f"Time: {readable_start} - {readable_end}\n"
            f"Shall I create this event?"
        )
    except Exception as e:
        logger.error(f"[Google] Stage error: {e}")
        return f"Failed to stage event: {str(e)}"

def commit_calendar_event_impl(confirm: str = "yes") -> str:
    """Commit the staged event to Google Calendar"""
    user_id = get_current_user_id()
    event_data = _get_draft(user_id)
    
    if not event_data: return "No pending event found to confirm."
    
    service, error = _get_authenticated_service()
    if error: return error
    
    try:
        api_body = {
            'summary': event_data['summary'],
            'description': event_data.get('description', ''),
            'start': {'dateTime': event_data['start'], 'timeZone': 'UTC'},
            'end': {'dateTime': event_data['end'], 'timeZone': 'UTC'}
        }
        if event_data.get('attendees'):
            api_body['attendees'] = [{'email': e} for e in event_data['attendees']]
        
        event = service.events().insert(calendarId='primary', body=api_body).execute()
        _clear_draft(user_id)
        
        return f"Event created! View here: {event.get('htmlLink', '')}"
    except Exception as e:
        logger.error(f"[Google] Commit error: {e}")
        return f"Failed to create event: {str(e)}"

def delete_calendar_event_impl(event_id: str) -> str:
    """
    Delete an event from Google Calendar by ID.
    """
    service, error = _get_authenticated_service()
    if error: return error
    
    try:
        service.events().delete(calendarId='primary', eventId=event_id).execute()
        logger.info(f"[Google] Event deleted: {event_id}")
        return f"Successfully deleted event (ID: {event_id})."
        
    except HttpError as e:
        if e.resp.status == 404:
            return f"Event not found (ID: {event_id}). It may have already been deleted."
        if e.resp.status == 410:
            return "Event is already deleted."
        
        logger.error(f"[Google] Delete API error: {e}")
        return f"Failed to delete event: {e.reason}"
    except Exception as e:
        logger.error(f"[Google] Delete unexpected error: {e}")
        return f"Error deleting event: {str(e)}"