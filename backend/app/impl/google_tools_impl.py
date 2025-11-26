import google.oauth2.credentials
import google.auth.transport.requests
from googleapiclient.discovery import build
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Any

from app.core.logger import logger
from app.core.config import settings
from app.core.crud import get_refresh_token
from app.core.context import get_current_user_id

def _get_authenticated_service() -> Tuple[Optional[Any], Optional[str]]:
    """
    Returns an authenticated Google Calendar service object if the user is logged in.
    If the user is not logged in, returns (None, "Authentication required. Please log in via Google.").

    If an error occurs during authentication, returns (None, f"Google Authorization failed: {str(e)}. Please log in again.").

    :return: A tuple containing an authenticated Google Calendar service object and an error message if applicable.
    :rtype: Tuple[Optional[Any], Optional[str]]
    """
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
    """
    Lists the user's upcoming events on their Google Calendar.

    :param max_results: The maximum number of events to fetch. Defaults to 5.
    :return: A string containing a list of the user's upcoming events.
    :rtype: str
    :raises Exception: If an error occurs while accessing the user's Google Calendar.
    """
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

def create_calendar_event_impl(summary: str, start_time: str, end_time: str, description: str = "", attendees: List[str] = None) -> str:
    """
    Creates a new event on the user's Google Calendar.

    :param summary: The title of the event.
    :param start_time: The start time of the event in ISO format (YYYY-MM-DDTHH:MM:SSZ).
    :param end_time: The end time of the event in ISO format (YYYY-MM-DDTHH:MM:SSZ).
    :param description: The description of the event. Defaults to an empty string.
    :param attendees: A list of attendee emails. Defaults to None.
    :return: A string containing a success message and the event's HTML link if the event was created successfully, or an error message if an error occurred.
    :rtype: str
    :raises Exception: If an error occurs while accessing the user's Google Calendar.
    """
    service, error = _get_authenticated_service()
    if error: return error

    try:
        event_body = {
            'summary': summary,
            'description': description,
            'start': {'dateTime': start_time, 'timeZone': 'UTC'},
            'end': {'dateTime': end_time, 'timeZone': 'UTC'},
        }
        if attendees:
            event_body['attendees'] = [{'email': a.strip()} for a in attendees]

        event = service.events().insert(calendarId='primary', body=event_body).execute()
        return f"Success! Event created: {event.get('htmlLink')}"
    except Exception as e:
        return f"Failed to schedule event: {str(e)}"