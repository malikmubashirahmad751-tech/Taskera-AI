import re
import uuid
from typing import Optional, Dict, Any, Union
from datetime import datetime, timezone
from pydantic import BaseModel, Field, field_validator
from app.core.database import supabase
from app.core.logger import logger
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

class UserIDValidator(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=100)
    
    @field_validator('user_id')
    @classmethod
    def validate_format(cls, v: str) -> str:
        if not re.match(r'^[a-zA-Z0-9_\-:@.]+$', v):
            raise ValueError("Invalid user ID format")
        return v

def validate_user_id(user_id: str) -> str:
    try:
        validated = UserIDValidator(user_id=str(user_id).strip())
        return validated.user_id
    except Exception as e:
        logger.warning(f"[CRUD] Invalid user_id '{user_id}': {e}")
        raise ValueError(f"Invalid user ID: {e}")

class UserCRUD:
    @staticmethod
    def get_or_create_user(user_id: str, email: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Used for Google Auth (Social Login)"""
        if not supabase: return None
        
        try:
            safe_uid = validate_user_id(user_id)
            
            response = supabase.table("users").select("*").eq("id", safe_uid).execute()
            if response.data:
                return response.data[0]
            
            new_user_data = {
                "id": safe_uid,
                "email": email,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            new_user = supabase.table("users").insert(new_user_data).execute()
            if new_user.data:
                logger.info(f"[CRUD] Created new user: {safe_uid}")
                return new_user.data[0]
            
            return None
            
        except Exception as e:
            logger.error(f"[CRUD] User operation error: {e}", exc_info=True)
            return None

    @staticmethod
    def create_user(email: str, password: str) -> Optional[Dict[str, Any]]:
        """Used for Standard Auth (Email/Password Signup)"""
        if not supabase: return None

        try:
            existing = supabase.table("users").select("email").eq("email", email).execute()
            if existing.data:
                return None  

            hashed_pw = get_password_hash(password)
            new_uid = str(uuid.uuid4())
            
            new_user_data = {
                "id": new_uid,
                "email": email,
                "password_hash": hashed_pw, 
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            data = supabase.table("users").insert(new_user_data).execute()
            if data.data:
                user = data.data[0]
                user['user_id'] = user['id']  
                return user
            return None
            
        except Exception as e:
            logger.error(f"[CRUD] Create user error: {e}")
            raise e

    @staticmethod
    def authenticate_user(email: str, password: str) -> Union[Dict[str, Any], bool]:
        """Used for Standard Auth (Login)"""
        if not supabase: return False

        try:
            response = supabase.table("users").select("*").eq("email", email).execute()
            if not response.data:
                return False
            
            user = response.data[0]
            stored_hash = user.get("password_hash")
            
            if not stored_hash:
                return False 
            
            if verify_password(password, stored_hash):
                user['user_id'] = user['id']
                return user
                
            return False
        except Exception as e:
            logger.error(f"[CRUD] Auth error: {e}")
            return False

class QuotaCRUD:
    @staticmethod
    def get_quota(identifier: str) -> Dict[str, Any]:
        if not supabase:
            return {"request_count": 0, "is_registered": False}
        
        try:
            response = supabase.table("usage_quotas").select("*").eq("identifier", identifier).execute()
            if response.data:
                return response.data[0]
            return {"request_count": 0, "is_registered": False}
        except Exception as e:
            logger.error(f"[CRUD] Quota fetch error: {e}")
            return {"request_count": 0, "is_registered": False}
    
    @staticmethod
    def increment_quota(identifier: str, is_registered: bool = False) -> bool:
        if not supabase: return True
        
        try:
            current = QuotaCRUD.get_quota(identifier)
            new_count = current.get("request_count", 0) + 1
            
            supabase.table("usage_quotas").upsert({
                "identifier": identifier,
                "request_count": new_count,
                "is_registered": is_registered,
                "last_request_at": datetime.now(timezone.utc).isoformat()
            }, on_conflict="identifier").execute()
            return True
        except Exception as e:
            logger.error(f"[CRUD] Quota increment error: {e}")
            return False

get_or_create_user = UserCRUD.get_or_create_user
create_user = UserCRUD.create_user
authenticate_user = UserCRUD.authenticate_user
increment_quota = QuotaCRUD.increment_quota
get_quota = QuotaCRUD.get_quota