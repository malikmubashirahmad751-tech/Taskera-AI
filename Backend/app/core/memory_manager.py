import time
import logging
import threading

from langgraph.checkpoint.memory import MemorySaver
from app.core.logger import logger
from app.services.file_handler import delete_all_user_files
from app.services.rag_service import delete_user_vectorstore

SESSION_EXPIRY_SECONDS = 3600  
QUESTION_EXPIRY_SECONDS = 300  
user_sessions = {}
session_lock = threading.Lock()

def get_user_checkpointer(user_id: str) -> MemorySaver:
    """
    Fetch or create a user's persistent LangGraph checkpointer
    in a thread-safe manner.
    
    Automatically resets checkpointer (and clears data) if the session expired.
    """
    with session_lock:
        current_time = time.time()

        if user_id not in user_sessions:
            logger.info(f"[Session] Creating new session and checkpointer for user_id: {user_id}")
            user_sessions[user_id] = {
                "checkpointer": MemorySaver(),
                "last_active": current_time,
                "expiry_duration": SESSION_EXPIRY_SECONDS
            }

        else:
            session_data = user_sessions[user_id]

            if current_time - session_data["last_active"] > session_data["expiry_duration"]:
                logger.info(f"[Session] Session expired for user: {user_id}. Performing full cleanup.")
                delete_all_user_files(user_id)
                delete_user_vectorstore(user_id)

                user_sessions[user_id]["checkpointer"] = MemorySaver()

            user_sessions[user_id]["last_active"] = current_time
            user_sessions[user_id]["expiry_duration"] = SESSION_EXPIRY_SECONDS

        return user_sessions[user_id]["checkpointer"]


def update_session_on_response(user_id: str, agent_response: str):
    """
    Update session timers based on agent's behavior.
    If the AI ends with a question → use shorter expiry.
    Otherwise → use full session expiry.
    """
    with session_lock:
        if user_id not in user_sessions:
            logger.warning(f"[Session] Attempted to update non-existent session for user: {user_id}")
            return

        is_question = agent_response.strip().endswith("?")

        if is_question:
            user_sessions[user_id]["expiry_duration"] = QUESTION_EXPIRY_SECONDS
            logger.info(f"[Session] AI asked a question → shorter expiry ({QUESTION_EXPIRY_SECONDS}s) for user: {user_id}")
        else:
            user_sessions[user_id]["expiry_duration"] = SESSION_EXPIRY_SECONDS

        user_sessions[user_id]["last_active"] = time.time()


def clear_expired_sessions():
    """
    Periodic job that checks and clears expired sessions.
    Performs full cleanup (files + vectorstore).
    """
    current_time = time.time()
    expired_users = []

    with session_lock:
        for user_id, data in list(user_sessions.items()):
            if current_time - data["last_active"] > data["expiry_duration"]:
                expired_users.append(user_id)

    if expired_users:
        logger.info(f"[Session] Found {len(expired_users)} expired sessions to clear.")
        for user_id in expired_users:
            logger.info(f"[Session] Clearing expired session for user: {user_id}")
            clear_user_session(user_id)
    else:
        logger.debug("[Session] No expired sessions found.")


def clear_user_session(user_id: str):
    """
    Fully removes a user's session and related data:
    1. In-memory checkpointer (by deleting it from the dict)
    2. Uploaded files
    3. Vectorstore (ChromaDB)
    """
    with session_lock:
        if user_id in user_sessions:
            del user_sessions[user_id]
            logger.info(f"[Session] Cleared in-memory checkpointer for user: {user_id}")
        else:
            logger.warning(f"[Session] No active session found for user: {user_id}")

    try:
        delete_all_user_files(user_id)
    except Exception as e:
        logger.error(f"[Cleanup] Error deleting files for user {user_id}: {e}", exc_info=True)

    try:
        delete_user_vectorstore(user_id)
    except Exception as e:
        logger.error(f"[Cleanup] Error deleting vectorstore for user {user_id}: {e}", exc_info=True)

    logger.info(f"[Session] Completed full cleanup for user: {user_id}")