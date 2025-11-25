import re
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, ValidationError
from app.core.database import supabase
from app.core.logger import logger

class UserIDValidator(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_\-:]+$")

def validate_user_id(user_id: str) -> str:
    try:
        model = UserIDValidator(user_id=str(user_id))
        return model.user_id
    except ValidationError as e:
        logger.warning(f"[CRUD] Invalid user_id: {user_id}")
        raise ValueError("Invalid user ID format.")

def get_or_create_user(user_id_string: str) -> Optional[Dict[str, Any]]:
    if not supabase: return None
    try:
        safe_uid = validate_user_id(user_id_string)
        response = supabase.table("users").select("*").eq("user_id_string", safe_uid).execute()
        if response.data: return response.data[0]
        
        new_user = supabase.table("users").insert({"user_id_string": safe_uid}).execute()
        if new_user.data: return new_user.data[0]
    except Exception as e:
        logger.error(f"[CRUD] User fetch error: {e}")
    return None

def save_refresh_token(user_id_string: str, token: str) -> bool:
    if not supabase: return False
    try:
        safe_uid = validate_user_id(user_id_string)
        get_or_create_user(safe_uid) 
        
        data = {
            "user_id_string": safe_uid,
            "google_refresh_token": token,
            "updated_at": "now()"
        }
        supabase.table("users").upsert(data, on_conflict="user_id_string").execute()
        logger.info(f"[CRUD] Saved Google token for {safe_uid}")
        return True
    except Exception as e:
        logger.error(f"[CRUD] Save token error: {e}")
        return False

def get_refresh_token(user_id_string: str) -> Optional[str]:
    if not supabase: return None
    try:
        safe_uid = validate_user_id(user_id_string)
        response = supabase.table("users").select("google_refresh_token").eq("user_id_string", safe_uid).execute()
        if response.data and response.data[0].get("google_refresh_token"):
            return response.data[0]["google_refresh_token"]
    except Exception as e:
        logger.error(f"[CRUD] Get token error: {e}")
    return None