import os
import re
import asyncio
import uvicorn
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Optional, List, Any, Dict, Union

from fastapi import (
    FastAPI, HTTPException, Body, Request,
    Form, File, UploadFile, Depends, status
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.sessions import SessionMiddleware
from starlette_csrf.middleware import CSRFMiddleware

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.core.config import get_settings
from app.core.logger import logger
from app.core.database import db_manager, supabase
from app.core.crud import UserCRUD, QuotaCRUD, save_refresh_token
from app.core.context import user_id_context

from app.routes.google_auth import router as auth_router

settings = get_settings()

process_executor = ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="taskera_worker"
)

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE if hasattr(settings, 'RATE_LIMIT_PER_MINUTE') else 60}/minute"]
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown"""
    logger.info("Starting Taskera AI Server")
    
    try:
        from app.services.scheduler import start_scheduler
        from app.core.memory_manager import initialize_memory
        from app.agents.controller_agent import workflow as agent_workflow
        
        start_scheduler()
        logger.info("Scheduler started")
        
        checkpointer = await initialize_memory()
        logger.info("Memory system initialized")
        
        app.state.agent_graph = agent_workflow.compile(checkpointer=checkpointer)
        logger.info("Agent graph compiled")
        
        if hasattr(db_manager, 'health_check'):
            if await db_manager.health_check():
                logger.info("Database connected")
            else:
                logger.warning("Database unavailable (running in degraded mode)")
        
        logger.info(f"Server ready on {settings.SERVER_HOST}:{settings.SERVER_PORT}")
        
        yield
        
    except Exception as e:
        logger.error(f"Startup failed: {e}", exc_info=True)
        raise
    
    logger.info("Shutting down Taskera AI Server...")
    
    try:
        from app.services.scheduler import shutdown_scheduler
        from app.mcp_client import shutdown_mcp_client
        
        shutdown_scheduler()
        await shutdown_mcp_client()
        process_executor.shutdown(wait=False)
        
        logger.info("Graceful shutdown complete")
        
    except Exception as e:
        logger.error(f"Shutdown error: {e}")

app = FastAPI(
    title="Taskera AI",
    description="Production-Ready AI Agent with Multi-Tool Integration",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(auth_router)

if settings.DEBUG:
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

default_origins = [
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "https://taskera-ai.vercel.app"
]

origins = settings.CORS_ORIGINS if hasattr(settings, "CORS_ORIGINS") else default_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-CSRF-Token"]
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        "localhost", 
        "127.0.0.1", 
        "::1", 
        "mubashir751-taskera-ai-backend.hf.space",
        "*.hf.space",
        "*.taskera.ai"
    ]
)


class AuthCredentials(BaseModel):
    email: str = Field(..., pattern=r"^\S+@\S+\.\S+$")
    password: str = Field(..., min_length=6, max_length=100)

class SecureChatInput(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=100)
    query: str = Field(..., max_length=5000)
    
    @field_validator('query')
    @classmethod
    def block_injection(cls, v: str) -> str:
        dangerous_patterns = [
            "ignore all previous instructions",
            "system override",
            "developer mode",
            "jailbreak"
        ]
        v_lower = v.lower()
        if any(pattern in v_lower for pattern in dangerous_patterns):
            logger.warning("Potential prompt injection detected")
            raise ValueError("Potential prompt injection detected")
        return v.strip()

class MCPRequest(BaseModel):
    jsonrpc: str = Field(..., pattern="^2.0$")
    method: str
    params: Optional[Dict[str, Any]] = None
    id: Union[int, str]

class MCPResponse(BaseModel):
    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[dict] = None
    id: Union[int, str]



async def verify_quota(request: Request, user_id: str = Form(...)) -> str:
    """Verify user has not exceeded quota"""
    user_id = user_id.strip()
    is_guest = user_id.startswith("guest") or user_id in ["unknown", "undefined"]
    identifier = request.client.host if is_guest else user_id
    
    try:
        quota = QuotaCRUD.get_quota(identifier)
        current_count = quota.get("request_count", 0)
        is_registered = quota.get("is_registered", False)
        
        limit = getattr(settings, "GUEST_REQUEST_LIMIT", 10)
        
        if is_guest and not is_registered and current_count >= limit:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Free trial limit reached. Please create an account."
            )
        
        QuotaCRUD.increment_quota(identifier, not is_guest)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Quota check error: {e}")
    
    return user_id



@app.get("/")
async def root():
    return {
        "message": "Taskera AI Server Online",
        "version": "2.0.0",
        "status": "operational"
    }

@app.get("/health")
async def health_check_endpoint():
    db_status = await db_manager.health_check() if hasattr(db_manager, 'health_check') else False
    return {
        "status": "healthy" if db_status else "degraded",
        "database": "connected" if db_status else "disconnected",
        "version": "2.0.0"
    }

@app.get("/csrf-token")
async def get_csrf_token_endpoint(request: Request):
    token = request.scope.get("csrf_token", "")
    return {"csrf_token": token}


@app.post("/auth/signup")
@limiter.limit("5/minute")
async def auth_signup_endpoint(creds: AuthCredentials, request: Request):
    if not supabase:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Auth service unavailable")
    
    try:
        auth_response = supabase.auth.sign_up({
            "email": creds.email, 
            "password": creds.password
        })
        
        if not auth_response.user:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Signup failed. Email may exist.")
        
        user_id = auth_response.user.id
        QuotaCRUD.increment_quota(user_id, is_registered=True)
        
        logger.info(f"New user registered: {creds.email}")
        return {"message": "Signup successful", "user_id": user_id, "email": creds.email}
        
    except Exception as e:
        logger.error(f"Signup error: {e}")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

@app.post("/auth/login")
@limiter.limit("10/minute")
async def auth_login_endpoint(creds: AuthCredentials, request: Request):
    if not supabase:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Auth service unavailable")
    
    try:
        auth_response = supabase.auth.sign_in_with_password({
            "email": creds.email, 
            "password": creds.password
        })
        
        if not auth_response.user or not auth_response.session:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
        
        logger.info(f"User logged in: {creds.email}")
        return {
            "message": "Login successful",
            "access_token": auth_response.session.access_token,
            "user_id": auth_response.user.id,
            "email": auth_response.user.email
        }
    except Exception as e:
        logger.warning(f"Login error: {e}")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")


async def handle_file_uploads(user_id: str, files: List[UploadFile]) -> str:
    """Handle file uploads, OCR, and RAG Indexing"""
    from app.impl.ocr_service_impl import image_text_extractor_impl
    from app.impl.knowledge_agent_impl import create_rag_tool_impl
    
    user_path = os.path.join(settings.UPLOAD_PATH, user_id)
    os.makedirs(user_path, exist_ok=True)
    
    ocr_context = ""
    loop = asyncio.get_running_loop()
    
    allowed_exts = getattr(settings, "ALLOWED_EXTENSIONS", {'.png', '.jpg', '.jpeg', '.pdf', '.txt', '.md'})
    
    for file in files:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in allowed_exts:
            continue
        
        content = await file.read()
        file_size = len(content)
        max_size = getattr(settings, "MAX_UPLOAD_SIZE_MB", 10) * 1024 * 1024
        
        if file_size > max_size:
            ocr_context += f"\n[File {file.filename} skipped: too large]"
            continue
        
        file_path = os.path.join(user_path, file.filename)
        with open(file_path, "wb") as f:
            f.write(content)
        
        # Image -> OCR
        if ext in ['.png', '.jpg', '.jpeg']:
            try:
                txt = await loop.run_in_executor(
                    process_executor,   
                    image_text_extractor_impl,
                    user_id, file.filename
                )
                ocr_context += f"\n[Image {file.filename} Content]: {txt}"
            except Exception as e:
                logger.error(f"OCR error: {e}")
                ocr_context += f"\n[OCR Error for {file.filename}]"
        else:
            try:
                await loop.run_in_executor(
                    process_executor,
                    create_rag_tool_impl,
                    user_id
                )
                ocr_context += f"\n[Document {file.filename} Indexed for RAG. Use 'local_document_retriever' to read it.]"
            except Exception as e:
                logger.error(f"RAG indexing error: {e}")

    return ocr_context

@app.post("/api/chat")
@limiter.limit("20/minute")
async def chat_endpoint(
    request: Request,
    query: str = Form(""),
    user_id: str = Depends(verify_quota),
    email: Optional[str] = Form(None),
    files: List[UploadFile] = File([])
):
    """Main chat endpoint"""
    from app.core.memory_manager import update_session_on_response
    from langchain_core.messages import HumanMessage
    
    token = user_id_context.set(user_id)
    
    try:
        try:
            safe_input = SecureChatInput(user_id=user_id, query=query)
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
        
        logger.info(f"[Chat] Request from {safe_input.user_id}")
        
        ocr_context = ""
        if files:
            ocr_context = await handle_file_uploads(user_id, files)
        
        import datetime
        now = datetime.datetime.now()
        full_query = (
            f"{query}{ocr_context}\n\n"
            f"[Context: {now.strftime('%A')}, {now.strftime('%Y-%m-%d')}, "
            f"Email: {email or 'unknown'}]"
        )
        
        input_message = {
            "messages": [HumanMessage(content=full_query)],
            "user_id": user_id,
            "user_email": email or "unknown"
        }
        
        config = {"configurable": {"thread_id": user_id}}
        
        if not hasattr(app.state, "agent_graph"):
             raise HTTPException(500, "Agent not initialized")
             
        final_state = await app.state.agent_graph.ainvoke(input_message, config)
        
        if not final_state.get("messages"):
             raise HTTPException(500, "Agent produced no output")
        
        raw = final_state['messages'][-1].content
        answer = " ".join([str(x) for x in raw]) if isinstance(raw, list) else str(raw)
        
        if not answer.strip():
            answer = "Task completed successfully."
        
        update_session_on_response(user_id, answer)
        
        return {"answer": answer, "user_id": user_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Chat error: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "An error occurred processing your request")
    finally:
        user_id_context.reset(token)



@app.post("/mcp", response_model=MCPResponse)
@limiter.limit("60/minute")
async def mcp_endpoint(request: Request, mcp_req: MCPRequest = Body(...)):
    """Model Context Protocol endpoint for tool execution"""
    
    from app.impl.google_tools_impl import (
        list_calendar_events_impl, stage_calendar_event_impl, commit_calendar_event_impl
    )
    from app.impl.tools_agent_impl import (
        duckduckgo_search_wrapper, wikipedia_query_wrapper, weather_search,
        headless_browser_search, latest_news_tool_function, calculator_tool_function,
        summarize_text, translator_tool_function
    )
    from app.impl.ocr_service_impl import image_text_extractor_impl
    from app.impl.knowledge_agent_impl import create_rag_tool_impl, retrieve_info_impl
    from app.impl.services_agent_impl import (
        schedule_research_task_impl, manage_calendar_events_impl
    )
    from app.services.file_handler import delete_specific_user_file, delete_all_user_files
    from app.services.rag_service import delete_user_vectorstore
    
    TOOL_REGISTRY = {
        "google_calendar_list": list_calendar_events_impl,
        "google_calendar_stage": stage_calendar_event_impl,
        "google_calendar_commit": commit_calendar_event_impl,
        "web_search": duckduckgo_search_wrapper,
        "wikipedia_search": wikipedia_query_wrapper,
        "weather_search": weather_search,
        "headless_browser_search": headless_browser_search,
        "latest_news_tool": latest_news_tool_function,
        "calculator_tool": calculator_tool_function,
        "summarize_tool": summarize_text,
        "translator_tool": translator_tool_function,
        "image_text_extractor": image_text_extractor_impl,
        "index_rag_documents": create_rag_tool_impl,
        "local_document_retriever": retrieve_info_impl,
        "schedule_research_task": schedule_research_task_impl,
        "manage_calendar_events": manage_calendar_events_impl,
        "delete_specific_user_file": delete_specific_user_file,
        "delete_all_user_files": delete_all_user_files,
        "delete_user_vectorstore": delete_user_vectorstore,
    }
    
    method_name = mcp_req.method
    params = mcp_req.params or {}
    
    if method_name not in TOOL_REGISTRY:
        return MCPResponse(
            error={"code": -32601, "message": f"Method '{method_name}' not found"},
            id=mcp_req.id
        )
    
    provided_user_id = params.get("user_id")
    token = user_id_context.set(provided_user_id) if provided_user_id else None
    
    try:
        func = TOOL_REGISTRY[method_name]
        
        if asyncio.iscoroutinefunction(func):
            result = await func(**params)
        else:
            result = func(**params)
        
        return MCPResponse(result=result, id=mcp_req.id)
        
    except Exception as e:
        logger.error(f"MCP execution error ({method_name}): {e}", exc_info=True)
        return MCPResponse(
            error={"code": -32000, "message": str(e)},
            id=mcp_req.id
        )
    finally:
        if token:
            user_id_context.reset(token)


@app.delete("/users/{user_id}/data")
async def delete_user_data_endpoint(request: Request, user_id: str):
    """Delete all user data"""
    from app.services.file_handler import delete_all_user_files
    from app.services.rag_service import delete_user_vectorstore
    
    try:
        delete_all_user_files(user_id)
        delete_user_vectorstore(user_id)
        
        logger.info(f"Deleted all data for user: {user_id}")
        return {"message": "User data cleared successfully"}
        
    except Exception as e:
        logger.error(f"Data deletion error: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to delete user data")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred", "type": "internal_error"}
    )

if __name__ == "__main__":
    uvicorn.run(
        "app.mcp_server:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=settings.DEBUG,
        log_level="info"
    )