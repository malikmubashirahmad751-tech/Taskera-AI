import asyncio
from typing import Optional, Dict, Any, List
from supabase import create_client, Client
from app.core.config import get_settings
from app.core.logger import logger

class DatabaseManager:
    """Singleton database manager with connection pooling"""
    
    _instance: Optional['DatabaseManager'] = None
    _client: Optional[Client] = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._client is None:
            self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Supabase client with error handling"""
        try:
            settings = get_settings()
            
            if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
                logger.error("Supabase credentials missing. Database disabled.")
                return
            
            self._client = create_client(
                settings.SUPABASE_URL,
                settings.SUPABASE_KEY
            )
            logger.info(" Supabase client initialized successfully")
            
            try:
                self._client.table("users").select("count", count="exact").limit(1).execute()
                logger.info(" Database connection verified")
            except Exception as e:
                logger.warning(f"Database connection test failed: {e}")
                
        except Exception as e:
            logger.error(f"Failed to initialize Supabase: {e}")
            self._client = None
    
    @property
    def client(self) -> Optional[Client]:
        """Get the Supabase client instance"""
        return self._client
    
    @property
    def is_connected(self) -> bool:
        """Check if database is connected"""
        return self._client is not None
    
    async def health_check(self) -> bool:
        """Async health check for database"""
        if not self.is_connected:
            return False
        
        try:
            async with self._lock:
                self._client.table("users").select("count", count="exact").limit(1).execute()
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False

_db_manager = DatabaseManager()

def get_database() -> Optional[Client]:
    """Get database client (for backward compatibility)"""
    return _db_manager.client

supabase = get_database()
db_manager = _db_manager