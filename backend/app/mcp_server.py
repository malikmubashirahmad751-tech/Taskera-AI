import sys
import asyncio
import platform
import functools
import os
import uuid
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Optional, List, Any, Dict, Union

from fastapi import (
    FastAPI, HTTPException, Body, Request,
    Form, File, UploadFile, Depends, status, Query
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.sessions import SessionMiddleware
from langchain_core.messages import HumanMessage

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

if platform.system() == 'Windows':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.core.config import settings
from app.core.logger import logger
from app.core.database import db_manager, supabase
from app.core.crud import UserCRUD, QuotaCRUD
from app.core.context import set_current_user_id, reset_current_user_id
from app.core.memory_manager import initialize_memory, shutdown_memory, get_memory_stats
from app.routes.google_auth import router as auth_router
from app.core.conversations import HistoryService 
from app.routes.voice_routes import router as voice_router

process_executor = ThreadPoolExecutor(
    max_workers=min(4, (os.cpu_count() or 1)),
    thread_name_prefix="taskera_worker"
)

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"],
    storage_uri="memory://"
)

async def _init_voice_service():
    """
    Initialize voice service asynchronously to avoid blocking startup.
    Voice model is loaded lazily on first transcription request.
    """
    try:
        from app.services.voice_service import voice_service
        logger.info("Voice service initialized (lazy loading enabled)")
    except ImportError as e:
        logger.warning(f"Voice service dependencies not installed: {e}")
    except Exception as e:
        logger.warning(f"Voice service init failed (non-critical): {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle manager
    Handles startup and shutdown tasks
    """
    logger.info(">>> Taskera AI Server Starting...")
    
    try:
        asyncio.create_task(_init_voice_service())
        
        from app.services.scheduler import start_scheduler
        start_scheduler()
        
        checkpointer = await initialize_memory()
        
        from app.agents.controller_agent import workflow as agent_workflow
        app.state.agent_graph = agent_workflow.compile(checkpointer=checkpointer)
        logger.info("Agent Graph Compiled & Memory Connected")
        
        if await db_manager.health_check():
            logger.info("Database Connected")
        else:
            logger.warning("Database Unavailable (Degraded Mode)")
            
        yield
        
    except Exception as e:
        logger.error(f"Startup Failed: {e}", exc_info=True)
        raise
    
    logger.info(">>> Shutting Down...")
    try:
        from app.services.scheduler import shutdown_scheduler
        from app.mcp_client import shutdown_mcp_client
        
        shutdown_scheduler()
        await shutdown_mcp_client()
        
        try:
            await asyncio.wait_for(shutdown_memory(), timeout=15.0)
        except asyncio.TimeoutError:
            logger.warning("Memory shutdown timeout - forcing close")
        
        process_executor.shutdown(wait=True, cancel_futures=True)
        logger.info("Graceful shutdown complete")
        
    except Exception as e:
        logger.error(f"Shutdown Error: {e}")

app = FastAPI(
    title="Taskera AI",
    description="Production-Ready AI Agent API with Multi-Tool Capabilities",
    version="3.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(auth_router)
app.include_router(voice_router, prefix="/api/voice", tags=["Voice"])

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """
    Add security headers to all responses
    Protects against XSS, clickjacking, MIME sniffing
    """
    response = await call_next(request)
    
    response.headers["X-Content-Type-Options"] = "nosniff"
    
    response.headers["X-Frame-Options"] = "DENY"
    
    response.headers["X-XSS-Protection"] = "1; mode=block"
    
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    
    if not settings.DEBUG:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self' https://*.supabase.co https://*.google.com https://*.googleapis.com"
        )
    
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

app.add_middleware(
    SessionMiddleware, 
    secret_key=settings.JWT_SECRET_KEY, 
    max_age=86400,  
    same_site="lax", 
    https_only=not settings.DEBUG
)

class AuthCredentials(BaseModel):
    """Authentication credentials for login/signup"""
    email: str = Field(..., pattern=r"^\S+@\S+\.\S+$")
    password: str = Field(..., min_length=8, max_length=100)

class SecureChatInput(BaseModel):
    """Validated chat input with security checks"""
    user_id: str = Field(..., min_length=1, max_length=100)
    query: str = Field(..., max_length=10000)
    
    @field_validator('query')
    @classmethod
    def validate_query(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Query cannot be empty")
        return v.replace('\x00', '').replace('\r\n', '\n').strip()
    
    @field_validator('user_id')
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        import re
        if not re.match(r'^[a-zA-Z0-9_\-:@.]+$', v):
            raise ValueError("Invalid user ID format")
        return v.strip()

class MCPRequest(BaseModel):
    """JSON-RPC 2.0 request for MCP endpoint"""
    jsonrpc: str = Field(..., pattern="^2.0$")
    method: str
    params: Optional[Dict[str, Any]] = None
    id: Union[int, str]

class MCPResponse(BaseModel):
    """JSON-RPC 2.0 response for MCP endpoint"""
    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[dict] = None
    id: Union[int, str]

class RenameThreadRequest(BaseModel):
    """Request body for renaming conversation threads"""
    title: str = Field(..., min_length=1, max_length=200)

async def verify_quota(request: Request, user_id: str = Form(...)) -> str:
    """
    Verify user quota for POST requests
    Enforces guest limits and tracks usage
    """
    user_id = user_id.strip()
    is_guest = user_id.startswith("guest") or user_id in ["unknown", "undefined", ""]
    identifier = request.client.host if is_guest else user_id
    
    try:
        quota = QuotaCRUD.get_quota(identifier)
        current_count = quota.get("request_count", 0)
        is_registered = quota.get("is_registered", False)
        limit = settings.GUEST_REQUEST_LIMIT
        
        if is_guest and not is_registered and current_count >= limit:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "error": "quota_exceeded", 
                    "message": f"Guest limit ({limit} requests) reached. Please register to continue."
                }
            )
        
        QuotaCRUD.increment_quota(identifier, not is_guest)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Quota check error: {e}")
        
    return user_id

async def verify_quota_query(request: Request, user_id: str = Query(...)) -> str:
    """
    Verify user quota for GET requests
    Wraps verify_quota with Query parameter
    """
    user_id = user_id.strip()
    is_guest = user_id.startswith("guest") or user_id in ["unknown", "undefined", ""]
    identifier = request.client.host if is_guest else user_id
    
    try:
        quota = QuotaCRUD.get_quota(identifier)
        current_count = quota.get("request_count", 0)
        is_registered = quota.get("is_registered", False)
        limit = settings.GUEST_REQUEST_LIMIT
        
        if is_guest and not is_registered and current_count >= limit:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "error": "quota_exceeded", 
                    "message": f"Guest limit ({limit} requests) reached. Please register."
                }
            )
        
        QuotaCRUD.increment_quota(identifier, not is_guest)       
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Quota check error: {e}")
        
    return user_id

async def handle_file_uploads(user_id: str, files: List[UploadFile]) -> str:
    """
    Handle file uploads with OCR and RAG indexing
    Supports images (OCR) and documents (RAG)
    """
    from app.impl.ocr_service_impl import image_text_extractor_impl
    from app.impl.knowledge_agent_impl import create_rag_tool_impl
    
    user_path = os.path.join(settings.UPLOAD_PATH, user_id)
    os.makedirs(user_path, exist_ok=True)
    
    context_notes = ""
    loop = asyncio.get_running_loop()
    allowed_exts = settings.ALLOWED_EXTENSIONS
    
    for file in files:
        safe_name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
        file_path = os.path.join(user_path, safe_name)
        
        try:
            ext = os.path.splitext(safe_name)[1].lower()            
            if ext not in allowed_exts:
                context_notes += f"\n[Skipped {file.filename}: Invalid format]"
                continue

            content = await file.read()
            
            if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
                context_notes += f"\n[Skipped {file.filename}: Too large (max {settings.MAX_UPLOAD_SIZE_MB}MB)]"
                continue
            
            with open(file_path, "wb") as f:
                f.write(content)
            
            if ext in ['.png', '.jpg', '.jpeg']:
                txt = await loop.run_in_executor(
                    process_executor, 
                    image_text_extractor_impl, 
                    user_id, 
                    safe_name
                )
                context_notes += f"\n[OCR - {file.filename}]: {txt[:500]}..."
            else:
                await loop.run_in_executor(
                    process_executor, 
                    create_rag_tool_impl, 
                    user_id
                )
                context_notes += f"\n[Document {file.filename} Indexed for RAG]"
                
        except Exception as e:
            logger.error(f"Upload failed for {file.filename}: {e}", exc_info=True)
            context_notes += f"\n[Error] Failed to process {file.filename}: {str(e)[:100]}"
            
    return context_notes

@app.get("/health")
async def health_check():
    """
    Health check endpoint
    Returns system status and component health
    """
    try:
        return {
            "status": "healthy", 
            "version": "3.0.0",
            "db": await db_manager.health_check(),
            "memory": await get_memory_stats(),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
        )

@app.get("/api/history")
@limiter.limit("30/minute")
async def get_history(request: Request, user_id: str = Depends(verify_quota_query)):
    """
    Get user conversation history
    Returns list of conversation threads with metadata
    """
    try:
        threads = await HistoryService.get_user_threads(user_id)
        return {
            "success": True, 
            "threads": threads,
            "count": len(threads)
        }
    except Exception as e:
        logger.error(f"Get history failed for {user_id}: {e}")
        raise HTTPException(500, "Failed to retrieve conversation history")

@app.get("/api/threads/{thread_id}")
@limiter.limit("30/minute")
async def get_thread(
    request: Request, 
    thread_id: str, 
    user_id: str = Depends(verify_quota_query)
):
    """
    Get messages from a specific thread
    Returns conversation history for the thread
    """
    try:
        msgs = await HistoryService.get_thread_messages(app.state, thread_id)
        return {
            "success": True, 
            "messages": msgs,
            "thread_id": thread_id
        }
    except Exception as e:
        logger.error(f"Get thread failed for {thread_id}: {e}")
        raise HTTPException(500, "Failed to retrieve thread messages")

@app.patch("/api/threads/{thread_id}")
@limiter.limit("20/minute")
async def rename_thread(
    request: Request, 
    thread_id: str, 
    body: RenameThreadRequest, 
    user_id: str = Depends(verify_quota_query)
):
    """
    Rename a conversation thread
    Updates thread title in database
    """
    try:
        await HistoryService.rename_thread(thread_id, user_id, body.title)
        return {
            "success": True, 
            "title": body.title,
            "thread_id": thread_id
        }
    except Exception as e:
        logger.error(f"Rename thread failed for {thread_id}: {e}")
        raise HTTPException(500, "Failed to rename thread")

@app.delete("/api/threads/{thread_id}")
@limiter.limit("20/minute")
async def delete_thread(
    request: Request, 
    thread_id: str, 
    user_id: str = Depends(verify_quota_query)
):
    """
    Delete a conversation thread
    Removes thread and all associated messages
    """
    try:
        await HistoryService.delete_thread(thread_id, user_id)
        return {
            "success": True,
            "thread_id": thread_id
        }
    except Exception as e:
        logger.error(f"Delete thread failed for {thread_id}: {e}")
        raise HTTPException(500, "Failed to delete thread")

@app.post("/api/chat")
@limiter.limit("30/minute")
async def chat_endpoint(
    request: Request,
    query: str = Form(""),
    user_id: str = Depends(verify_quota),
    thread_id: Optional[str] = Form(None), 
    email: Optional[str] = Form(None),
    files: List[UploadFile] = File([])
):
    """
    Main chat endpoint
    Processes user queries through the AI agent
    Supports file uploads, multi-turn conversations, and tool usage
    """
    token = set_current_user_id(user_id)
    try:
        is_new = False
        if not thread_id or thread_id in ["null", "undefined", ""]:
            thread_id = f"{user_id}__{uuid.uuid4().hex[:8]}"
            is_new = True

        file_context = ""
        if files:
            file_context = await handle_file_uploads(user_id, files)

        full_prompt = f"{query}{file_context}"
        if email: 
            full_prompt += f"\n[Context: User Email: {email}]"

        input_data = {
            "messages": [HumanMessage(content=full_prompt)],
            "user_id": user_id,
            "user_email": email or "guest",
            "retry_count": 0
        }
        
        if not hasattr(app.state, "agent_graph"):
            raise HTTPException(503, "Agent not initialized. Please try again in a moment.")

        config = {
            "configurable": {"thread_id": thread_id}, 
            "recursion_limit": 25
        }
        
        final_state = await asyncio.wait_for(
            app.state.agent_graph.ainvoke(input_data, config), 
            timeout=120.0
        )
        
        if not final_state.get("messages"):
            raise HTTPException(500, "Agent produced no response")

        ai_msg = final_state['messages'][-1].content
        answer = str(ai_msg) if ai_msg else "Processing complete."
        
        if is_new:
            asyncio.create_task(
                HistoryService.create_or_update_thread(
                    user_id, thread_id, query, answer
                )
            )
        else:
            asyncio.create_task(
                HistoryService.create_or_update_thread(
                    user_id, thread_id, None, None
                )
            )
        
        return {
            "success": True, 
            "answer": answer, 
            "thread_id": thread_id, 
            "user_id": user_id,
            "timestamp": datetime.now().isoformat()
        }

    except asyncio.TimeoutError:
        logger.error(f"Chat timeout for user {user_id}")
        raise HTTPException(504, "Request timed out. Please try a simpler query or try again.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat failed for user {user_id}: {e}", exc_info=True)
        raise HTTPException(500, "Internal server error. Please try again.")
    finally:
        reset_current_user_id(token)

@app.post("/mcp", response_model=MCPResponse)
@limiter.limit("100/minute")
async def mcp_endpoint(request: Request, mcp_req: MCPRequest = Body(...)):
    """
    Unified MCP (Model Context Protocol) Tool Endpoint
    Routes JSON-RPC 2.0 requests to implementation functions dynamically
    
    Supported methods:
    - web_search, wikipedia_search, weather_search
    - headless_browser_search, latest_news_tool
    - calculator_tool, summarize_tool, translator_tool
    - image_text_extractor, index_rag_documents, local_document_retriever
    - schedule_research_task, manage_calendar_events
    - delete_specific_user_file, delete_all_user_files, delete_user_vectorstore
    - rename_conversation
    """
    from app.impl.tools_agent_impl import (
        duckduckgo_search_wrapper, wikipedia_query_wrapper, weather_search,
        headless_browser_search, latest_news_tool_function, calculator_tool_function,
        summarize_text, translator_tool_function
    )
    from app.impl.ocr_service_impl import image_text_extractor_impl
    from app.impl.knowledge_agent_impl import create_rag_tool_impl, retrieve_info_impl
    from app.impl.services_agent_impl import schedule_research_task_impl, manage_calendar_events_impl
    from app.services.file_handler import delete_specific_user_file, delete_all_user_files
    from app.services.rag_service import delete_user_vectorstore
    
    async def rename_conversation_tool(thread_id: str, new_title: str, user_id: str = None):
        """Internal tool for renaming conversations"""
        if not user_id: 
            return "Error: user_id required"
        try:
            await HistoryService.rename_thread(thread_id, user_id, new_title)
            return f"Conversation renamed to '{new_title}'"
        except Exception as e:
            logger.error(f"Rename conversation failed: {e}")
            return f"Rename failed: {str(e)}"

    TOOL_REGISTRY = {
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
        "rename_conversation": rename_conversation_tool,
    }
    
    method = mcp_req.method
    params = mcp_req.params or {}
    
    provided_user_id = params.get("user_id")
    token = set_current_user_id(provided_user_id) if provided_user_id else None
    
    try:
        if method not in TOOL_REGISTRY:
            return MCPResponse(
                error={
                    "code": -32601, 
                    "message": f"Method '{method}' not found. Available methods: {', '.join(TOOL_REGISTRY.keys())}"
                }, 
                id=mcp_req.id
            )
            
        func = TOOL_REGISTRY[method]
        
        if asyncio.iscoroutinefunction(func):
            result = await func(**params)
        else:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                process_executor, 
                functools.partial(func, **params)
            )
            
        return MCPResponse(result=result, id=mcp_req.id)
        
    except TypeError as e:
        logger.error(f"MCP Parameter Error ({method}): {e}")
        return MCPResponse(
            error={
                "code": -32602, 
                "message": f"Invalid parameters for method '{method}': {str(e)}"
            }, 
            id=mcp_req.id
        )
    except Exception as e:
        logger.error(f"MCP Tool Error ({method}): {e}", exc_info=True)
        return MCPResponse(
            error={
                "code": -32000, 
                "message": f"Internal error executing '{method}': {str(e)}"
            }, 
            id=mcp_req.id
        )
    finally:
        if token: 
            reset_current_user_id(token)

@app.delete("/users/{user_id}/data")
@limiter.limit("5/minute")
async def delete_user_data(request: Request, user_id: str):
    """
    Delete all user data
    Removes uploaded files and vector store
    WARNING: This action is irreversible
    """
    from app.services.file_handler import delete_all_user_files
    from app.services.rag_service import delete_user_vectorstore
    
    try:
        delete_all_user_files(user_id)
        
        delete_user_vectorstore(user_id)
        
        logger.info(f"Deleted all data for user: {user_id}")
        
        return {
            "success": True, 
            "message": "User data cleared successfully",
            "user_id": user_id
        }
    except Exception as e:
        logger.error(f"Delete user data failed for {user_id}: {e}")
        raise HTTPException(500, "Failed to delete user data")
@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    """Custom 404 handler"""
    return JSONResponse(
        status_code=404,
        content={
            "error": "not_found",
            "message": "The requested endpoint does not exist",
            "path": str(request.url.path)
        }
    )

@app.exception_handler(500)
async def internal_error_handler(request: Request, exc: Exception):
    """Custom 500 handler"""
    logger.error(f"Internal server error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred. Please try again later."
        }
    )