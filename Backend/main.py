from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.routes.api import router  # Changed to match your structure
from app.services.scheduler import start_scheduler, shutdown_scheduler
from app.core.logger import logger

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events"""
    # Startup
    logger.info("Starting Taskera AI Backend...")
    start_scheduler()
    logger.info("Application startup complete")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Taskera AI Backend...")
    shutdown_scheduler()
    logger.info("Application shutdown complete")

app = FastAPI(
    title="Taskera AI Backend",
    description="Multi-functional AI agent with RAG, scheduling, and tool integration",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change this to specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(router)

@app.get("/")
async def root():
    return {
        "message": "Taskera AI Backend is running",
        "version": "1.0.0",
        "endpoints": {
            "chat": "/api/chat",
            "delete_file": "/users/{user_id}/files/{filename}",
            "delete_all_data": "/users/{user_id}/data"
        }
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )