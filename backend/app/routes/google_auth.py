import os
import requests
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow

from app.core.config import get_settings
from app.core.crud import save_refresh_token
from app.core.logger import logger
from slowapi import Limiter
from slowapi.util import get_remote_address

settings = get_settings()
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/auth", tags=["authentication"])

os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

def get_google_flow(redirect_uri: str = None) -> Flow:
    """Create Google OAuth flow"""
    if not redirect_uri:
        redirect_uri = settings.GOOGLE_REDIRECT_URI
    
    return Flow.from_client_config(
        client_config={
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token"
            }
        },
        scopes=[
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile"
        ],
        redirect_uri=redirect_uri
    )

@router.get("/google")
@limiter.limit("5/minute")
async def google_oauth_start(request: Request, user_id: str):
    """Initiate Google OAuth flow"""
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google OAuth not configured"
        )
    
    try:
        flow = get_google_flow()
        authorization_url, state = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            state=user_id
        )
        
        logger.info(f"[OAuth] Starting Google auth for user: {user_id}")
        return RedirectResponse(authorization_url)
        
    except Exception as e:
        logger.error(f"[OAuth] Failed to start flow: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate Google authentication"
        )

@router.get("/google/callback")
async def google_oauth_callback(request: Request, code: str, state: str):
    """Handle Google OAuth callback"""
    try:
        flow = get_google_flow()
        flow.fetch_token(code=code)
        creds = flow.credentials
        
        user_info_response = requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {creds.token}"},
            timeout=10
        )
        user_info_response.raise_for_status()
        user_info = user_info_response.json()
        
        email = user_info.get("email", "google_user")
        real_user_id = user_info.get("id", state)
        
        if creds.refresh_token:
            save_refresh_token(real_user_id, creds.refresh_token)
            logger.info(f"[OAuth] Saved refresh token for user: {email}")
        else:
            logger.warning(f"[OAuth] No refresh token received for: {email}")
        
        redirect_url = (
            f"http://127.0.0.1:5500/frontend/index.html"
            f"?google_auth=success"
            f"&access_token={creds.token}"
            f"&email={email}"
            f"&user_id={real_user_id}"
        )
        
        return RedirectResponse(redirect_url)
        
    except requests.RequestException as e:
        logger.error(f"[OAuth] Failed to fetch user info: {e}")
        return RedirectResponse(
            "http://127.0.0.1:5500/frontend/index.html?google_auth=error&reason=user_info_failed"
        )
    except Exception as e:
        logger.error(f"[OAuth] Callback error: {e}", exc_info=True)
        return RedirectResponse(
            "http://127.0.0.1:5500/frontend/index.html?google_auth=error&reason=unknown"
        )