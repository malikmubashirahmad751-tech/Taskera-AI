from app.core.database import supabase
from app.core.logger import logger

def get_or_create_user(user_id_string: str) -> dict | None:
    """
    Fetches a user by their unique string ID. If they don't exist,
    creates them. This is our main "login" function.
    """
    if not supabase:
        logger.error("[CRUD] Supabase client not available.")
        return None

    try:
        response = supabase.table("users") \
                           .select("*") \
                           .eq("user_id_string", user_id_string) \
                           .limit(1) \
                           .execute()
        
        if response.data:
            logger.info(f"[CRUD] Found existing user: {user_id_string}")
            return response.data[0]
        
        logger.info(f"[CRUD] No user found. Creating new user: {user_id_string}")
        insert_response = supabase.table("users") \
                                  .insert({"user_id_string": user_id_string}) \
                                  .execute()
        
        if insert_response.data:
            logger.info(f"[CRUD] Successfully created new user: {user_id_string}")
            return insert_response.data[0]
        else:
            logger.error(f"[CRUD] Failed to create user: {insert_response.error.message}")
            return None

    except Exception as e:
        logger.error(f"[CRUD] Error in get_or_create_user for {user_id_string}: {e}", exc_info=True)
        return None

def save_refresh_token(user_id_string: str, token: str) -> bool:
    """
    Saves the Google refresh_token for a specific user.
    """
    if not supabase:
        logger.error("[CRUD] Supabase client not available.")
        return False
        
    try:
        user = get_or_create_user(user_id_string)
        if not user:
            return False 
        response = supabase.table("users") \
                           .update({"google_refresh_token": token}) \
                           .eq("user_id_string", user_id_string) \
                           .execute()
        
        if response.data:
            logger.info(f"[CRUD] Successfully saved refresh token for user: {user_id_string}")
            return True
        else:
            logger.error(f"[CRUD] Failed to save token: {response.error.message}")
            return False
            
    except Exception as e:
        logger.error(f"[CRUD] Error saving refresh token for {user_id_string}: {e}", exc_info=True)
        return False

def get_refresh_token(user_id_string: str) -> str | None:
    """
    Retrieves the Google refresh_token for a specific user.
    """
    if not supabase:
        logger.error("[CRUD] Supabase client not available.")
        return None
        
    try:
        response = supabase.table("users") \
                           .select("google_refresh_token") \
                           .eq("user_id_string", user_id_string) \
                           .limit(1) \
                           .execute()
                           
        if response.data and response.data[0].get("google_refresh_token"):
            logger.info(f"[CRUD] Retrieved refresh token for user: {user_id_string}")
            return response.data[0]["google_refresh_token"]
        else:
            logger.warning(f"[CRUD] No refresh token found for user: {user_id_string}")
            return None
            
    except Exception as e:
        logger.error(f"[CRUD] Error getting refresh token for {user_id_string}: {e}", exc_info=True)
        return None