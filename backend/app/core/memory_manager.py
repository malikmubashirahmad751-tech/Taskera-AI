import time
import logging
import threading
import asyncio

from langgraph.checkpoint.memory import MemorySaver
from app.core.logger import logger
from app.mcp_client import call_mcp, MCPError 
SESSION_EXPIRY_SECONDS = 3600  
QUESTION_EXPIRY_SECONDS = 300  
user_sessions = {}
session_lock = threading.Lock()

def get_user_checkpointer(user_id: str) -> MemorySaver:
    """
    Fetch or create a user's persistent LangGraph checkpointer
    in a thread-safe manner.
    
    This is called by the acp_server.
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
                logger.info(f"[Session] Session expired for user: {user_id}. Resetting checkpointer.")
                user_sessions[user_id]["checkpointer"] = MemorySaver()
                user_sessions[user_id]["expiry_duration"] = SESSION_EXPIRY_SECONDS
            
            user_sessions[user_id]["last_active"] = current_time

        return user_sessions[user_id]["checkpointer"]

def update_session_on_response(user_id: str, agent_response: str):
    """
    Update session timers based on agent's behavior.
    This is called by the acp_server after a graph run.
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
            
        user_sessions[user_id]["last_active"] = time.time()

def _clear_expired_sessions_memory() -> list[str]:
    """
    (Internal) Checks and clears expired sessions from the in-memory dict.
    Returns a list of user_ids that were expired for backend cleanup.
    """
    current_time = time.time()
    expired_users = []

    with session_lock:
        for user_id, data in list(user_sessions.items()):
            if current_time - data["last_active"] > data["expiry_duration"]:
                logger.info(f"[Session] Clearing expired in-memory session for user: {user_id}")
                del user_sessions[user_id]
                expired_users.append(user_id)
    
    return expired_users

async def run_expired_session_cleanup():
    """
    This is the function the ACP scheduler will run periodically.
    It cleans local memory, then calls the MCP server to clean backend data.
    """
    logger.info("[Session Cleanup Job] Running...")
    
    expired_users = _clear_expired_sessions_memory()
    
    if not expired_users:
        logger.info("[Session Cleanup Job] No expired sessions found.")
        return

    logger.info(f"[Session Cleanup Job] Cleared {len(expired_users)} in-memory sessions. Now performing I/O cleanup via MCP.")
    
    for user_id in expired_users:
        try:
            logger.info(f"[Session Cleanup Job] Calling MCP to delete data for expired user: {user_id}")
            await call_mcp("delete_all_user_data", {"user_id": user_id})
        except MCPError as e:
            logger.error(f"[Session Cleanup Job] Failed to clear backend data for user {user_id}: {e}")
        except Exception as e:
            logger.error(f"[Session Cleanup Job] Unexpected error during MCP call for user {user_id}: {e}")

def clear_user_session(user_id: str):
    """
    (Sync) Fully removes a user's in-memory session upon request.
    This is called by the admin_agent in acp_server.
    The admin_agent is responsible for *also* calling the MCP
    server to delete backend data.
    """
    session_found = False
    with session_lock:
        if user_id in user_sessions:
            del user_sessions[user_id]
            logger.info(f"[Session] Cleared in-memory checkpointer for user: {user_id}")
            session_found = True
        else:
            logger.warning(f"[Session] No active session found to clear for user: {user_id}")
    
    return session_found