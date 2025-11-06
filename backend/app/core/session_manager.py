import time
import logging
import threading  
from langchain.memory import ConversationBufferMemory
from app.core import utils 
from app.core.file_handler import delete_all_user_files
from app.services.rag_system import delete_user_vectorstore

logger = logging.getLogger(__name__)

SESSION_EXPIRY_SECONDS = 3600  
QUESTION_EXPIRY_SECONDS = 300  
user_sessions = {}
session_lock = threading.Lock()


def get_user_memory(user_id: str) -> ConversationBufferMemory:
    """
    Always use the provided user_id to fetch or create persistent memory.
    This function is now thread-safe.
    """
    with session_lock:
        current_time = time.time()
        
        if user_id not in user_sessions:
            logger.info(f"Creating new session for user_id: {user_id}")
            user_sessions[user_id] = {
                "memory": ConversationBufferMemory(memory_key="chat_history", return_messages=True),
                "last_active": current_time,
                "expiry_duration": SESSION_EXPIRY_SECONDS
            }
        else:
            session_data = user_sessions[user_id]
            
            if current_time - session_data["last_active"] > session_data["expiry_duration"]:
                logger.info(f"Session expired for user: {user_id}. Performing full cleanup.")
                
                delete_all_user_files(user_id)
                delete_user_vectorstore(user_id)
                
                user_sessions[user_id]["memory"] = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
            
            user_sessions[user_id]["last_active"] = current_time
            user_sessions[user_id]["expiry_duration"] = SESSION_EXPIRY_SECONDS

        return user_sessions[user_id]["memory"]

def update_session_on_response(user_id: str, agent_response: str):
    """
    Update session's active time and expiry duration based on the agent's response.
    This function is now thread-safe.
    """
    with session_lock:
        if user_id not in user_sessions:
            logger.warning(f"Attempted to update a non-existent session for user: {user_id}")
            return

        is_question = utils.is_questioning_response(agent_response)
        
        if is_question:
            user_sessions[user_id]["expiry_duration"] = QUESTION_EXPIRY_SECONDS
            logger.info(f"AI asked a question. Setting shorter expiry ({QUESTION_EXPIRY_SECONDS}s) for user: {user_id}")
        else:
            user_sessions[user_id]["expiry_duration"] = SESSION_EXPIRY_SECONDS

        user_sessions[user_id]["last_active"] = time.time()

def clear_expired_sessions():
    """
    Scheduled job to clear all sessions that have expired.
    This now performs a full cleanup for each expired user.
    """
    current_time = time.time()
    expired_users = []

    with session_lock:
        session_items = list(user_sessions.items()) 
        for user_id, data in session_items:
            if current_time - data["last_active"] > data["expiry_duration"]:
                expired_users.append(user_id)
    
    if expired_users:
        logger.info(f"Scheduler: Found {len(expired_users)} expired sessions to clear.")
        for user_id in expired_users:
            logger.info(f"Scheduler: Clearing expired data for user: {user_id}")
            clear_user_session(user_id)
    else:
        logger.info("Scheduler: No expired sessions found.")

def clear_user_session(user_id: str):
    """
    Manually clears a user's entire dataset (thread-safe):
    1. In-memory conversation session.
    2. All uploaded files from the filesystem.
    3. The associated vector store (ChromaDB).
    
    This function is called by the 'New Session' button in api.py
    and by the clear_expired_sessions scheduler job.
    """
    
    with session_lock:
        if user_id in user_sessions:
            del user_sessions[user_id]
            logger.info(f"Cleared in-memory session for user: {user_id}")
        else:
            logger.warning(f"No active session found for user '{user_id}' to clear from memory.")
    
    try:
        delete_all_user_files(user_id)
    except Exception as e:
        logger.error(f"Error deleting files for user {user_id}: {e}", exc_info=True)
        
    try:
        delete_user_vectorstore(user_id)
    except Exception as e:
        logger.error(f"Error deleting vector store for user {user_id}: {e}", exc_info=True)
    
    logger.info(f"Completed full data cleanup for user: {user_id}")