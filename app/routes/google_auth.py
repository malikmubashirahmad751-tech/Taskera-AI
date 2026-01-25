import os
from urllib.parse import urlencode
from fastapi import APIRouter, Request, HTTPException, Depends, status
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel
from authlib.integrations.starlette_client import OAuth
from app.core.config import settings
from app.core.crud import get_or_create_user, authenticate_user, create_user 
from app.core.logger import logger
import jwt 
from datetime import datetime, timedelta

router = APIRouter()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 

oauth = OAuth()
oauth.register(
    name='google',
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile', 'prompt': 'select_account'}
)

class AuthRequest(BaseModel):
    email: str
    password: str

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


@router.get("/auth/google")
async def google_login(request: Request):
    """Initiates Google OAuth."""
    redirect_uri = str(settings.GOOGLE_REDIRECT_URI)
    return await oauth.google.authorize_redirect(request, redirect_uri)

@router.get("/auth/google/callback")
async def google_auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        
        if not user_info:
            raise HTTPException(400, "Failed to get user info from Google")

        email = user_info.get('email')
        google_user_id = user_info.get('sub')
        
        db_user = get_or_create_user(user_id=google_user_id, email=email)
        
        frontend_base = settings.FRONTEND_URL 
        
        params = {
            "google_auth": "success",
            "access_token": token.get('access_token'), 
            "user_id": google_user_id,
            "email": email
        }
        
        query_string = urlencode(params)
        return RedirectResponse(url=f"{frontend_base}?{query_string}")
        
    except Exception as e:
        logger.error(f"Auth Callback Failed: {e}")
        frontend_base = settings.FRONTEND_URL
        return RedirectResponse(url=f"{frontend_base}/?error=auth_failed&details={str(e)}")

@router.post("/auth/signup")
async def signup(credentials: AuthRequest):
    """Creates a new user with email/password"""
    try:
        user = create_user(email=credentials.email, password=credentials.password)
        
        if not user:
            raise HTTPException(status_code=400, detail="User already exists or error creating user")

        uid = user.get('user_id_string') or user.get('user_id')

        access_token = create_access_token(data={"sub": uid, "email": user['email']})

        return {
            "access_token": access_token,
            "user_id": uid,
            "email": user['email'],
            "token_type": "bearer"
        }
    except Exception as e:
        logger.error(f"Signup Error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/auth/login")
async def login(credentials: AuthRequest):
    """Logs in an existing user"""
    try:
        user = authenticate_user(email=credentials.email, password=credentials.password)
        
        if not user:
            raise HTTPException(status_code=401, detail="Incorrect email or password")

        uid = user.get('user_id_string') or user.get('user_id')

        access_token = create_access_token(data={"sub": uid, "email": user['email']})

        return {
            "access_token": access_token,
            "user_id": uid,
            "email": user['email'],
            "token_type": "bearer"
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Login Error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")