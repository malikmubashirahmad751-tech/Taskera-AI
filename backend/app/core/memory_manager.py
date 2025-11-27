import os
import aiosqlite
from typing import Optional
from datetime import datetime, timedelta
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from app.core.logger import logger

_checkpointer: Optional[AsyncSqliteSaver] = None
_connection: Optional[aiosqlite.Connection] = None

async def initialize_memory() -> AsyncSqliteSaver:
    """
    Initialize persistent memory with SQLite + WAL mode
    """
    global _checkpointer, _connection
    
    try:
        db_path = "checkpoints.sqlite"
        
        # Create connection with proper settings
        _connection = await aiosqlite.connect(
            db_path,
            timeout=30.0,
            isolation_level=None  # Autocommit mode
        )
        
        # Enable WAL mode for better concurrency
        await _connection.execute("PRAGMA journal_mode=WAL;")
        await _connection.execute("PRAGMA synchronous=NORMAL;")
        await _connection.execute("PRAGMA cache_size=-64000;")  # 64MB cache
        await _connection.execute("PRAGMA temp_store=MEMORY;")
        await _connection.commit()
        
        # Create checkpointer
        _checkpointer = AsyncSqliteSaver(_connection)
        await _checkpointer.setup()
        
        logger.info("✓ SQLite memory initialized (WAL mode enabled)")
        
        # Log database size
        if os.path.exists(db_path):
            size_mb = os.path.getsize(db_path) / (1024 * 1024)
            logger.info(f"  Database size: {size_mb:.2f} MB")
        
        return _checkpointer
        
    except Exception as e:
        logger.error(f"CRITICAL: Memory initialization failed: {e}", exc_info=True)
        raise

def get_global_checkpointer() -> Optional[AsyncSqliteSaver]:
    """Get the global checkpointer instance"""
    return _checkpointer

async def cleanup_old_sessions(days: int = 30):
    """
    Clean up old sessions from database
    """
    if not _connection:
        logger.warning("Cannot cleanup: No database connection")
        return
    
    try:
        cutoff_date = datetime.now() - timedelta(days=days)
        cutoff_timestamp = cutoff_date.timestamp()
        
        # Note: This requires knowledge of LangGraph's internal schema
        # Adjust table/column names based on actual schema
        cursor = await _connection.execute(
            "SELECT COUNT(*) FROM checkpoints WHERE created_at < ?",
            (cutoff_timestamp,)
        )
        count = await cursor.fetchone()
        
        if count and count[0] > 0:
            await _connection.execute(
                "DELETE FROM checkpoints WHERE created_at < ?",
                (cutoff_timestamp,)
            )
            await _connection.commit()
            logger.info(f"Cleaned up {count[0]} old sessions (older than {days} days)")
        
    except Exception as e:
        logger.error(f"Session cleanup error: {e}")

def update_session_on_response(user_id: str, agent_response: str):
    """
    Hook for session analytics (placeholder for future use)
    """
    # Could be used to track conversation quality, user satisfaction, etc.
    pass

def clear_user_session(user_id: str):
    """
    Clear specific user session
    Note: Actual deletion requires raw SQL as LangGraph doesn't expose this
    """
    logger.info(f"Clear session requested for user: {user_id}")
    # In production, you'd need to delete from the checkpoints table
    # where thread_id matches the user_id

async def get_memory_stats() -> dict:
    """Get memory system statistics"""
    if not _connection:
        return {"status": "unavailable"}
    
    try:
        cursor = await _connection.execute("SELECT COUNT(*) FROM checkpoints")
        checkpoint_count = (await cursor.fetchone())[0]
        
        cursor = await _connection.execute(
            "SELECT SUM(LENGTH(checkpoint)) FROM checkpoints"
        )
        total_size = (await cursor.fetchone())[0] or 0
        
        return {
            "status": "active",
            "checkpoint_count": checkpoint_count,
            "total_size_mb": total_size / (1024 * 1024),
            "wal_mode": "enabled"
        }
        
    except Exception as e:
        logger.error(f"Failed to get memory stats: {e}")
        return {"status": "error", "error": str(e)}

async def shutdown_memory():
    """Gracefully close memory connections"""
    global _connection, _checkpointer
    
    if _connection:
        try:
            await _connection.close()
            logger.info("Memory system shut down")
        except Exception as e:
            logger.error(f"Memory shutdown error: {e}")
    
    _connection = None
    _checkpointer = None