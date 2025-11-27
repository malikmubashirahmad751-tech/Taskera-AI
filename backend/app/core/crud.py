import re
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field, field_validator
from app.core.database import supabase
from app.core.logger import logger

class UserIDValidator(BaseModel):
    """Validates user ID format"""
    user_id: str = Field(..., min_length=1, max_length=100)
    
    @field_validator('user_id')
    @classmethod
    def validate_format(cls, v: str) -> str:
        if not re.match(r'^[a-zA-Z0-9_\-:@.]+$', v):
            raise ValueError("Invalid user ID format")
        return v

def validate_user_id(user_id: str) -> str:
    """Validate and sanitize user ID"""
    try:
        validated = UserIDValidator(user_id=str(user_id).strip())
        return validated.user_id
    except Exception as e:
        logger.warning(f"[CRUD] Invalid user_id '{user_id}': {e}")
        raise ValueError(f"Invalid user ID: {e}")

class UserCRUD:
    """User database operations"""
    
    @staticmethod
    def get_or_create_user(user_id: str) -> Optional[Dict[str, Any]]:
        """Get existing user or create new one"""
        if not supabase:
            logger.warning("[CRUD] Database not available")
            return None
        
        try:
            safe_uid = validate_user_id(user_id)
            
            response = supabase.table("users")\
                .select("*")\
                .eq("user_id_string", safe_uid)\
                .execute()
            
            if response.data:
                return response.data[0]
            
            new_user_data = {
                "user_id_string": safe_uid,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            new_user = supabase.table("users")\
                .insert(new_user_data)\
                .execute()
            
            if new_user.data:
                logger.info(f"[CRUD] Created new user: {safe_uid}")
                return new_user.data[0]
            
            logger.error(f"[CRUD] Failed to create user: {safe_uid}")
            return None
            
        except Exception as e:
            logger.error(f"[CRUD] User operation error: {e}", exc_info=True)
            return None
    
    @staticmethod
    def save_refresh_token(user_id: str, token: str) -> bool:
        """Save Google refresh token for user"""
        if not supabase:
            return False
        
        try:
            safe_uid = validate_user_id(user_id)
            
            UserCRUD.get_or_create_user(safe_uid)
            
            data = {
                "user_id_string": safe_uid,
                "google_refresh_token": token,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            supabase.table("users")\
                .upsert(data, on_conflict="user_id_string")\
                .execute()
            
            logger.info(f"[CRUD] Saved refresh token for user: {safe_uid}")
            return True
            
        except Exception as e:
            logger.error(f"[CRUD] Token save error: {e}", exc_info=True)
            return False
    
    @staticmethod
    def get_refresh_token(user_id: str) -> Optional[str]:
        """Get Google refresh token for user"""
        if not supabase:
            return None
        
        try:
            safe_uid = validate_user_id(user_id)
            
            response = supabase.table("users")\
                .select("google_refresh_token")\
                .eq("user_id_string", safe_uid)\
                .execute()
            
            if response.data and response.data[0].get("google_refresh_token"):
                return response.data[0]["google_refresh_token"]
            
            return None
            
        except Exception as e:
            logger.error(f"[CRUD] Token retrieval error: {e}", exc_info=True)
            return None

class QuotaCRUD:
    """Usage quota operations"""
    
    @staticmethod
    def get_quota(identifier: str) -> Dict[str, Any]:
        """Get usage quota for identifier"""
        if not supabase:
            return {"request_count": 0, "is_registered": False}
        
        try:
            response = supabase.table("usage_quotas")\
                .select("*")\
                .eq("identifier", identifier)\
                .execute()
            
            if response.data:
                return response.data[0]
            
            return {"request_count": 0, "is_registered": False}
            
        except Exception as e:
            logger.error(f"[CRUD] Quota fetch error: {e}")
            return {"request_count": 0, "is_registered": False}
    
    @staticmethod
    def increment_quota(identifier: str, is_registered: bool = False) -> bool:
        """
        Increment usage quota with race-condition handling.
        Solves error 23505 (Duplicate Key)
        """
        if not supabase:
            return True 
        
        try:
            current = QuotaCRUD.get_quota(identifier)
            new_count = current.get("request_count", 0) + 1
            
            supabase.table("usage_quotas")\
                .upsert({
                    "identifier": identifier,
                    "request_count": new_count,
                    "is_registered": is_registered,
                    "last_request_at": datetime.now(timezone.utc).isoformat()
                }, on_conflict="identifier")\
                .execute()
            
            return True
            
        except Exception as e:
            
            if "23505" in str(e) or "duplicate key" in str(e):
                logger.warning(f"[CRUD] Race condition for {identifier}, retrying via UPDATE...")
                try:
                    supabase.table("usage_quotas")\
                        .update({
                            "request_count": new_count,
                            "last_request_at": datetime.now(timezone.utc).isoformat()
                        })\
                        .eq("identifier", identifier)\
                        .execute()
                    return True
                except Exception as retry_e:
                    logger.error(f"[CRUD] Retry failed: {retry_e}")
                    return False
            
            logger.error(f"[CRUD] Quota increment error: {e}")
            return False

get_or_create_user = UserCRUD.get_or_create_user
save_refresh_token = UserCRUD.save_refresh_token
get_refresh_token = UserCRUD.get_refresh_token