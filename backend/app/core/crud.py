import re
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, ValidationError

from app.core.database import supabase
from app.core.logger import logger

class UserIDValidator(BaseModel):
    user_id: str = Field(
        ..., 
        min_length=1, 
        max_length=100, 
        pattern=r"^[a-zA-Z0-9_-]+$", 
        description="Unique identifier for the user"
    )

class TokenValidator(BaseModel):
    token: str = Field(..., min_length=10, description="Google Refresh Token")

def validate_user_id(user_id: str) -> str:
    """Helper to validate user_id format before hitting DB."""
    try:
        model = UserIDValidator(user_id=user_id)
        return model.user_id
    except ValidationError as e:
        logger.warning(f"[CRUD Security] Blocked invalid user_id: {user_id} - {str(e)}")
        raise ValueError("Invalid user ID format.")


def get_or_create_user(user_id_string: str) -> Optional[Dict[str, Any]]:
    """
    Fetches a user. If not found, creates them. 
    Protected against injection via Pydantic validation.
    """
    if not supabase:
        logger.error("[CRUD] Supabase client not available.")
        return None

    try:
        safe_uid = validate_user_id(user_id_string)

        response = supabase.table("users") \
                           .select("*") \
                           .eq("user_id_string", safe_uid) \
                           .limit(1) \
                           .execute()
        
        if response.data:
            logger.info(f"[CRUD] Found existing user: {safe_uid}")
            return response.data[0]
        
        logger.info(f"[CRUD] No user found. Creating new user: {safe_uid}")
        insert_response = supabase.table("users") \
                                  .insert({"user_id_string": safe_uid}) \
                                  .execute()
        
        if insert_response.data:
            logger.info(f"[CRUD] Successfully created new user: {safe_uid}")
            return insert_response.data[0]
        
        logger.error(f"[CRUD] Failed to create user {safe_uid}. DB returned no data.")
        return None

    except ValueError as ve:
        logger.error(f"[CRUD] Security Violation: {ve}")
        return None
    except Exception as e:
        logger.error(f"[CRUD] Unexpected error in get_or_create_user: {e}", exc_info=True)
        return None


def save_refresh_token(user_id_string: str, token: str) -> bool:
    """
    Saves the Google refresh_token using an atomic UPSERT.
    """
    if not supabase:
        logger.error("[CRUD] Supabase client not available.")
        return False
        
    try:
        safe_uid = validate_user_id(user_id_string)
        TokenValidator(token=token) 

        data_payload = {
            "user_id_string": safe_uid,
            "google_refresh_token": token,
             
        }

        response = supabase.table("users") \
                           .upsert(data_payload, on_conflict="user_id_string") \
                           .execute()
        
        if response.data:
            logger.info(f"[CRUD] Successfully saved refresh token for user: {safe_uid}")
            return True
        else:
            logger.error(f"[CRUD] Failed to save token: No data returned.")
            return False
            
    except ValidationError as ve:
        logger.error(f"[CRUD] Invalid data format: {ve}")
        return False
    except Exception as e:
        logger.error(f"[CRUD] Error saving refresh token for {user_id_string}: {e}", exc_info=True)
        return False


def get_refresh_token(user_id_string: str) -> Optional[str]:
    """
    Retrieves the Google refresh_token.
    """
    if not supabase:
        logger.error("[CRUD] Supabase client not available.")
        return None
        
    try:
        safe_uid = validate_user_id(user_id_string)

        response = supabase.table("users") \
                           .select("google_refresh_token") \
                           .eq("user_id_string", safe_uid) \
                           .limit(1) \
                           .execute()
                           
        if response.data and response.data[0].get("google_refresh_token"):
            logger.info(f"[CRUD] Retrieved refresh token for user: {safe_uid}")
            return response.data[0]["google_refresh_token"]
        else:
            logger.warning(f"[CRUD] No refresh token found for user: {safe_uid}")
            return None
            
    except ValueError as ve:
        logger.error(f"[CRUD] Security Violation: {ve}")
        return None
    except Exception as e:
        logger.error(f"[CRUD] Error getting refresh token for {user_id_string}: {e}", exc_info=True)
        return None