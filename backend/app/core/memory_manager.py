import os
import aiosqlite
import asyncio
from typing import Optional
from datetime import datetime, timedelta
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from app.core.logger import logger

_checkpointer: Optional[AsyncSqliteSaver] = None
_connection: Optional[aiosqlite.Connection] = None
_cleanup_task: Optional[asyncio.Task] = None
_lock = asyncio.Lock()

async def initialize_memory() -> AsyncSqliteSaver:
    """Initialize persistent memory with SQLite + WAL mode"""
    global _checkpointer, _connection, _cleanup_task
    
    async with _lock:
        if _checkpointer is not None:
            logger.warning("Memory already initialized")
            return _checkpointer
        
        try:
            db_path = "checkpoints.sqlite"
            
            _connection = await aiosqlite.connect(
                db_path,
                timeout=30.0,
                isolation_level=None,
                check_same_thread=False
            )
            
            await _connection.execute("PRAGMA journal_mode=WAL;")
            await _connection.execute("PRAGMA synchronous=NORMAL;")
            await _connection.execute("PRAGMA cache_size=-64000;")
            await _connection.execute("PRAGMA temp_store=MEMORY;")
            await _connection.execute("PRAGMA mmap_size=268435456;")  
            await _connection.execute("PRAGMA page_size=4096;")
            await _connection.commit()
            
            _checkpointer = AsyncSqliteSaver(_connection)
            await _checkpointer.setup()
            
            logger.info(" SQLite memory initialized (WAL mode)")
            
            if os.path.exists(db_path):
                size_mb = os.path.getsize(db_path) / (1024 * 1024)
                logger.info(f"  Database size: {size_mb:.2f} MB")
            
            _cleanup_task = asyncio.create_task(periodic_cleanup())
            
            return _checkpointer
            
        except Exception as e:
            logger.error(f"CRITICAL: Memory init failed: {e}", exc_info=True)
            if _connection:
                await _connection.close()
                _connection = None
            raise

def get_global_checkpointer() -> Optional[AsyncSqliteSaver]:
    """Get the global checkpointer instance"""
    return _checkpointer

async def periodic_cleanup():
    """Background task for periodic cleanup"""
    while True:
        try:
            await asyncio.sleep(86400)  
            await cleanup_old_sessions(days=30)
        except asyncio.CancelledError:
            logger.info("Cleanup task cancelled")
            break
        except Exception as e:
            logger.error(f"Cleanup task error: {e}")

async def cleanup_old_sessions(days: int = 30):
    """Clean up old sessions from database"""
    if not _connection:
        logger.warning("Cannot cleanup: No connection")
        return
    
    async with _lock:
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            cutoff_timestamp = cutoff_date.timestamp()
            
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
                logger.info(f"Cleaned {count[0]} old sessions (>{days} days)")
            
        except Exception as e:
            logger.error(f"Session cleanup error: {e}")

async def optimize_database():
    """Optimize the database (VACUUM)"""
    if not _connection:
        return
    
    async with _lock:
        try:
            logger.info("Running database optimization...")
            await _connection.execute("VACUUM;")
            await _connection.execute("ANALYZE;")
            logger.info("Database optimization complete")
        except Exception as e:
            logger.error(f"Optimization error: {e}")

def update_session_on_response(user_id: str, agent_response: str):
    """Hook for session analytics (placeholder)"""
    pass

def clear_user_session(user_id: str):
    """Clear specific user session"""
    logger.info(f"Clear session requested: {user_id}")

async def get_memory_stats() -> dict:
    """Get memory system statistics"""
    if not _connection:
        return {"status": "unavailable"}
    
    try:
        async with _lock:
            cursor = await _connection.execute("SELECT COUNT(*) FROM checkpoints")
            checkpoint_count = (await cursor.fetchone())[0]
            
            cursor = await _connection.execute(
                "SELECT SUM(LENGTH(checkpoint)) FROM checkpoints"
            )
            total_size = (await cursor.fetchone())[0] or 0
            
            db_path = "checkpoints.sqlite"
            file_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
            
            return {
                "status": "active",
                "checkpoint_count": checkpoint_count,
                "total_size_mb": total_size / (1024 * 1024),
                "file_size_mb": file_size / (1024 * 1024),
                "wal_mode": "enabled"
            }
        
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        return {"status": "error", "error": str(e)}

async def shutdown_memory():
    """Gracefully close memory connections"""
    global _connection, _checkpointer, _cleanup_task
    
    logger.info("Shutting down memory system...")
    
    if _cleanup_task and not _cleanup_task.done():
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass
    
    if _connection:
        async with _lock:
            try:
                await _connection.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                await _connection.commit()
                await _connection.close()
                logger.info("Memory system shut down")
            except Exception as e:
                logger.error(f"Memory shutdown error: {e}")
    
    _connection = None
    _checkpointer = None
    _cleanup_task = None