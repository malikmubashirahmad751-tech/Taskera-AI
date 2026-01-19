from dotenv import load_dotenv
load_dotenv()

import os
import sys
import platform
import asyncio
import uvicorn
from app.core.config import settings 

def main():
    """
    Production Launcher
    Ensures the correct Event Loop Policy is set for Windows + Postgres compatibility
    before Uvicorn boots up.
    """
    if platform.system() == 'Windows':
        print("Applying Windows SelectorEventLoop policy for Psycopg...")
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    port = settings.SERVER_PORT if hasattr(settings, 'SERVER_PORT') else int(os.getenv("PORT", 7860))
    
    print(f"Starting Taskera AI on Port {port}...")

    uvicorn.run(
       "app.mcp_server:app",
       host="0.0.0.0",
       port=port,
       reload=settings.DEBUG,
       log_level="info",
       access_log=settings.DEBUG,
       workers=1 
    )

if __name__ == "__main__":
    main()