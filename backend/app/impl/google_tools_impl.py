import google.oauth2.credentials
import google.auth.transport.requests
from googleapiclient.discovery import build
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from app.core.logger import logger
from app.core.config import settings
from app.core.crud import get_refresh_token

def _get_creds(user_id: str):
    """
    Reconstructs Google Credentials from Supabase Refresh Token.
    Automatically refreshes the access token if expired.
    """
    token = get_refresh_token(user_id)
    if not token:
        logger.warning(f"[Google Impl] No refresh token found for user: {user_id}")
        return None

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
        return creds
    except Exception as e:
        logger.error(f"[Google Impl] Auth refresh failed for {user_id}: {e}")
        return None

def list_calendar_events_impl(user_id: str, max_results: int = 10, time_min_iso: str = None) -> str:
    """
    Lists upcoming events.
    """
    creds = _get_creds(user_id)
    if not creds: 
        return "Auth Required: Please ask the user to log in via /auth/google"
    
    try:
        service = build('calendar', 'v3', credentials=creds)
        
        if not time_min_iso:
            time_min_iso = datetime.now(timezone.utc).isoformat()
        
        logger.info(f"[Google Impl] Fetching events for {user_id} from {time_min_iso}")

        events_result = service.events().list(
            calendarId='primary',
            timeMin=time_min_iso,
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        if not events:
            return "No upcoming events found."

        output = [" **Your Calendar:**"]
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            summary = event.get('summary', 'No Title')
            output.append(f"- {summary} (at {start})")
            
        return "\n".join(output)

    except Exception as e:
        logger.error(f"[Google Impl] List Error: {e}", exc_info=True)
        return f"Error accessing calendar: {str(e)}"

def create_calendar_event_impl(
    user_id: str, 
    summary: str, 
    start_time: str, 
    end_time: str, 
    description: str = "",
    attendees: List[str] = None
) -> str:
    """
    Creates a new event.
    start_time/end_time must be ISO format (e.g. 2024-11-20T15:00:00)
    """
    creds = _get_creds(user_id)
    if not creds: 
        return "Auth Required"

    try:
        service = build('calendar', 'v3', credentials=creds)
        
        event_body = {
            'summary': summary,
            'description': description,
            'start': {
                'dateTime': start_time,
                'timeZone': 'UTC', 
            },
            'end': {
                'dateTime': end_time,
                'timeZone': 'UTC',
            },
        }

        if attendees:
            event_body['attendees'] = [{'email': email.strip()} for email in attendees]

        logger.info(f"[Google Impl] Creating event '{summary}' for {user_id}")

        event = service.events().insert(calendarId='primary', body=event_body).execute()
        
        return f"Event created successfully! Link: {event.get('htmlLink')}"

    except Exception as e:
        logger.error(f"[Google Impl] Create Error: {e}", exc_info=True)
        return f"Failed to schedule event: {str(e)}"