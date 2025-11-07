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


# --- NEW HELPER FUNCTION ---
def _perform_data_cleanup(user_id: str):
    """
    Internal helper to safely delete user files and vectorstore.
    This function does NOT lock and should be called after a
    session has been removed from the user_sessions dict.
    """
    try:
        delete_all_user_files(user_id)
    except Exception as e:
        logger.error(f"[Cleanup] Error deleting files for user {user_id}: {e}", exc_info=True)

    try:
        delete_user_vectorstore(user_id)
    except Exception as e:
        logger.error(f"[Cleanup] Error deleting vectorstore for user {user_id}: {e}", exc_info=True)


# --- MODIFIED FUNCTION ---
def get_user_checkpointer(user_id: str) -> MemorySaver:
    """
    Fetch or create a user's persistent LangGraph checkpointer
    in a thread-safe manner.
    
    Automatically resets checkpointer (and clears data) if the session expired.
    """
    perform_cleanup = False
    checkpointer = None

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

            # Check if session expired
            if current_time - session_data["last_active"] > session_data["expiry_duration"]:
                logger.info(f"[Session] Session expired for user: {user_id}. Performing reset.")
                
                # Mark for cleanup, but do it *outside* the lock
                perform_cleanup = True 
                
                # Reset the checkpointer and timers
                user_sessions[user_id]["checkpointer"] = MemorySaver()
                user_sessions[user_id]["last_active"] = current_time
                user_sessions[user_id]["expiry_duration"] = SESSION_EXPIRY_SECONDS
            
            else:
                # --- THIS IS THE KEY FIX ---
                # Session is active. ONLY update last_active.
                # DO NOT touch expiry_duration, or it will break the
                # short expiry for questions.
                user_sessions[user_id]["last_active"] = current_time

        checkpointer = user_sessions[user_id]["checkpointer"]
    
    # --- Perform slow I/O cleanup *outside* the lock ---
    if perform_cleanup:
        logger.info(f"[Session] Performing post-reset data cleanup for user: {user_id}")
        _perform_data_cleanup(user_id)

    return checkpointer


def update_session_on_response(user_id: str, agent_response: str):
    """
    Update session timers based on agent's behavior.
    If the AI ends with a question -> use shorter expiry.
    Otherwise -> use full session expiry.
    
    (This function was logically correct, but its effect
     was being erased by the bug in get_user_checkpointer)
    """
    with session_lock:
        if user_id not in user_sessions:
            logger.warning(f"[Session] Attempted to update non-existent session for user: {user_id}")
            return

        if isinstance(agent_response, list):
            agent_response = " ".join(str(x) for x in agent_response)
        elif not isinstance(agent_response, str):
            agent_response = str(agent_response)

        is_question = agent_response.strip().endswith("?")

        if is_question:
            user_sessions[user_id]["expiry_duration"] = QUESTION_EXPIRY_SECONDS
            logger.info(f"[Session] AI asked a question -> shorter expiry ({QUESTION_EXPIRY_SECONDS}s) for user: {user_id}")
        else:
            user_sessions[user_id]["expiry_duration"] = SESSION_EXPIRY_SECONDS
            # We can optionally log this, but it might be noisy
            # logger.debug(f"[Session] Reset to full expiry ({SESSION_EXPIRY_SECONDS}s) for user: {user_id}")

        user_sessions[user_id]["last_active"] = time.time()


# --- MODIFIED FUNCTION ---
def clear_expired_sessions():
    """
    Periodic job that checks and clears expired sessions.
    Performs full cleanup (files + vectorstore).
    This is now race-condition-safe.
    """
    current_time = time.time()
    expired_users = []

    # --- Step 1: Acquire lock, find expired users, and delete from dict ---
    with session_lock:
        # Use list() to create a copy for safe iteration while modifying
        for user_id, data in list(user_sessions.items()):
            if current_time - data["last_active"] > data["expiry_duration"]:
                logger.info(f"[Session] Clearing expired session for user: {user_id}")
                del user_sessions[user_id]
                expired_users.append(user_id)

    # --- Step 2: Release lock, then perform slow I/O cleanup ---
    if expired_users:
        logger.info(f"[Session] Cleared {len(expired_users)} in-memory sessions. Now performing I/O cleanup.")
        for user_id in expired_users:
            logger.info(f"[Session] Performing full data cleanup for expired user: {user_id}")
            _perform_data_cleanup(user_id)
    else:
        logger.debug("[Session] No expired sessions found.")


# --- MODIFIED FUNCTION ---
def clear_user_session(user_id: str):
    """
    Fully removes a user's session and related data upon request.
    1. In-memory checkpointer (by deleting it from the dict)
    2. Uploaded files
    3. Vectorstore (ChromaDB)
    """
    session_found = False
    with session_lock:
        if user_id in user_sessions:
            del user_sessions[user_id]
            logger.info(f"[Session] Cleared in-memory checkpointer for user: {user_id}")
            session_found = True
        else:
            logger.warning(f"[Session] No active session found to clear for user: {user_id}")

    # Always attempt cleanup even if session wasn't in memory,
    # in case of orphaned files/vectors.
    if session_found:
        logger.info(f"[Session] Performing full data cleanup for user: {user_id}")
    else:
        logger.warning(f"[Session] Performing opportunistic cleanup for user {user_id} (no session found).")

    _perform_data_cleanup(user_id)

    # --- FIX: Added missing closing parenthesis ---
    logger.info(f"[Session] Completed full cleanup for user: {user_id}")