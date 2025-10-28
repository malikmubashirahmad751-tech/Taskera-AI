import time
import logging
from langchain.memory import ConversationBufferMemory
from app.core import utils 
from app.core.file_handler import delete_all_user_files
from app.services.rag_system import delete_user_vectorstore


logger = logging.getLogger(__name__)


SESSION_EXPIRY_SECONDS = 3600  
QUESTION_EXPIRY_SECONDS = 300  

user_sessions = {}



def get_user_memory(user_id: str) -> ConversationBufferMemory:
    """Always use the provided user_id to fetch or create persistent memory."""
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
            logger.info(f"Session expired for user: {user_id}. Resetting memory.")
            user_sessions[user_id]["memory"] = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
    
    user_sessions[user_id]["last_active"] = current_time
    return user_sessions[user_id]["memory"]



def update_session_on_response(user_id: str, agent_response: str):
    """Update session's active time and expiry duration based on the agent's response."""
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
    """Scheduled job to clear all sessions that have expired."""
    current_time = time.time()
    expired_users = [
        user_id for user_id, data in list(user_sessions.items())
        if current_time - data["last_active"] > data["expiry_duration"]
    ]

    for user_id in expired_users:
        del user_sessions[user_id]
        logger.info(f"Auto-cleared expired session for user: {user_id}")

def clear_user_memory(user_id: str):
    """
    Manually clears a user's entire dataset:
    1. In-memory conversation session.
    2. All uploaded files from the filesystem.
    3. The associated vector store (ChromaDB).
    """
   
    if user_id in user_sessions:
        del user_sessions[user_id]
        logger.info(f"Cleared in-memory session for user: {user_id}")
    else:
        logger.warning(f"No active session found for user '{user_id}' to clear.")


    delete_all_user_files(user_id)
    
    delete_user_vectorstore(user_id)
    
    logger.info(f"Completed full data cleanup for user: {user_id}")       