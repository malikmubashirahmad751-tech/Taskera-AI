import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.routes.api import router as api_router
from app.services.scheduler import start_scheduler, shutdown_scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start and stop background scheduler."""
    start_scheduler()
    yield
    shutdown_scheduler()

app = FastAPI(
    title="Devis AI Backend",
    lifespan=lifespan
)

origins = [
    "http://localhost:3000",
    "http://localhost",
    "http://127.0.0.1:5500",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", summary="Root Health Check")
def home():
    """API health check."""
    return {"message": "AI Research Assistant API is running successfully."}

app.include_router(api_router)

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)