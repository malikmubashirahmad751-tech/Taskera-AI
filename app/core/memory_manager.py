import os
import asyncio
from typing import Optional
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from app.core.config import get_settings
from app.core.logger import logger

settings = get_settings()

_checkpointer: Optional[AsyncPostgresSaver] = None
_pool: Optional[AsyncConnectionPool] = None
_init_lock = asyncio.Lock()

async def initialize_memory() -> AsyncPostgresSaver:
    """Initialize persistent memory with proper async handling"""
    global _checkpointer, _pool
    
    async with _init_lock:
        if _checkpointer is not None:
            return _checkpointer
        
        db_url = settings.SUPABASE_DB_URL
        
        if not db_url:
            logger.error("CRITICAL: SUPABASE_DB_URL is missing")
            raise ValueError("Missing SUPABASE_DB_URL")

        try:
            logger.info("Initializing Database Pool...")
            
            _pool = AsyncConnectionPool(
                conninfo=db_url,
                min_size=2,
                max_size=20,
                timeout=30.0,
                kwargs={"autocommit": True, "prepare_threshold": None},
                open=False
            )
            
            await _pool.open(wait=True, timeout=30.0)
            
            async with _pool.connection() as conn:
                result = await conn.execute("SELECT 1")
                await result.fetchone()
                
            _checkpointer = AsyncPostgresSaver(_pool)
            await _checkpointer.setup()
            
            logger.info(" Supabase Postgres Memory initialized successfully")
            return _checkpointer
                
        except asyncio.TimeoutError:
            logger.error("Database connection timeout")
            await _cleanup_on_error()
            raise ConnectionError("Database connection timeout")
            
        except Exception as e:
            logger.error(f"Memory init failed: {e}", exc_info=True)
            await _cleanup_on_error()
            raise

async def _cleanup_on_error():
    """Cleanup resources on initialization error"""
    global _pool, _checkpointer
    if _pool:
        try:
            await _pool.close()
        except:
            pass
        _pool = None
    _checkpointer = None

async def get_memory_stats() -> dict:
    """Get memory system statistics with error handling"""
    if not _pool:
        return {"status": "unavailable"}
    
    try:
        async with asyncio.timeout(5.0):
            async with _pool.connection() as conn:
                cursor = await conn.execute(
                    "SELECT COUNT(DISTINCT thread_id) FROM checkpoints"
                )
                thread_count = (await cursor.fetchone())[0]
                
                pool_stats = _pool.get_stats() if hasattr(_pool, "get_stats") else {}
                
                return {
                    "status": "active",
                    "backend": "postgres",
                    "active_threads": thread_count,
                    "pool_size": pool_stats.get("pool_size", 0)
                }
    except asyncio.TimeoutError:
        logger.warning("Stats query timeout")
        return {"status": "timeout"}
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return {"status": "error", "error": str(e)}

async def shutdown_memory():
    """Gracefully shutdown with timeout protection"""
    global _pool, _checkpointer
    
    logger.info("Shutting down memory system...")
    
    if _pool:
        try:
            async with asyncio.timeout(10.0):
                await _pool.close()
            logger.info("Database pool closed")
        except asyncio.TimeoutError:
            logger.warning("Pool shutdown timeout - forcing close")
        except Exception as e:
            logger.error(f"Shutdown error: {e}")
    
    _pool = None
    _checkpointer = None

def get_pool() -> Optional[AsyncConnectionPool]:
    """Thread-safe pool accessor"""
    return _pool

def is_initialized() -> bool:
    """Check if memory system is ready"""
    return _checkpointer is not None and _pool is not None