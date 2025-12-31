import os
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
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.sessions import SessionMiddleware

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.core.config import get_settings
from app.core.logger import logger
from app.core.database import db_manager, supabase
from app.core.crud import UserCRUD, QuotaCRUD
from app.core.context import user_id_context

from app.routes.google_auth import router as auth_router

settings = get_settings()

process_executor = ThreadPoolExecutor(
    max_workers=min(4, (os.cpu_count() or 1) * 2),
    thread_name_prefix="taskera_worker"
)

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{getattr(settings, 'RATE_LIMIT_PER_MINUTE', 60)}/minute"],
    storage_uri="memory://"
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan with proper cleanup"""
    logger.info("Starting Taskera AI Server")
    
    try:
        from app.services.scheduler import start_scheduler
        start_scheduler()
        
        from app.core.memory_manager import initialize_memory
        checkpointer = await initialize_memory()
        logger.info("Memory system initialized")
        
        from app.agents.controller_agent import workflow as agent_workflow
        app.state.agent_graph = agent_workflow.compile(checkpointer=checkpointer)
        logger.info("Agent graph compiled")
        
        if hasattr(db_manager, 'health_check'):
            if await db_manager.health_check():
                logger.info("Database connected")
            else:
                logger.warning("Database unavailable (degraded mode)")
        
        logger.info("Server ready")
        yield
        
    except Exception as e:
        logger.error(f"Startup failed: {e}", exc_info=True)
        raise
    
    # Shutdown
    logger.info("Shutting down...")
    
    try:
        from app.services.scheduler import shutdown_scheduler
        from app.mcp_client import shutdown_mcp_client
        from app.core.memory_manager import shutdown_memory
        
        shutdown_scheduler()
        await shutdown_mcp_client()
        await shutdown_memory()
        process_executor.shutdown(wait=True, cancel_futures=True)
        
        logger.info("Graceful shutdown complete")
        
    except Exception as e:
        logger.error(f"Shutdown error: {e}")

app = FastAPI(
    title="Taskera AI",
    description="Production-Ready AI Agent API",
    version="2.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(auth_router)

if settings.DEBUG:
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

origins_str = os.getenv("BACKEND_CORS_ORIGINS", "http://127.0.0.1:5500,http://localhost:5500,https://taskera-ai.vercel.app")
origins = [origin.strip() for origin in origins_str.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
    max_age=3600
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.JWT_SECRET_KEY,
    max_age=86400,
    same_site="lax",
    https_only=not settings.DEBUG
)

class AuthCredentials(BaseModel):
    email: str = Field(..., pattern=r"^\S+@\S+\.\S+$")
    password: str = Field(..., min_length=8, max_length=100)

class SecureChatInput(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=100)
    query: str = Field(..., max_length=10000)
    
    @field_validator('query')
    @classmethod
    def validate_query(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Query cannot be empty")
        
        v = v.replace('\x00', '')
        
        return v.strip()
    
    @field_validator('user_id')
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        import re
        if not re.match(r'^[a-zA-Z0-9_\-]+$', v):
            raise ValueError("Invalid user ID format")
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
    """Rate limiting with quota check"""
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
                detail={
                    "error": "quota_exceeded",
                    "message": "Free trial limit reached. Please create an account.",
                    "current": current_count,
                    "limit": limit
                }
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
        "service": "Taskera AI",
        "version": "2.1.0",
        "status": "operational",
        "docs": "/docs" if settings.DEBUG else "disabled"
    }

@app.get("/health")
async def health_check():
    db_status = await db_manager.health_check() if hasattr(db_manager, 'health_check') else False
    
    from app.core.memory_manager import get_memory_stats
    memory_stats = await get_memory_stats()
    
    return {
        "status": "healthy" if db_status else "degraded",
        "database": "connected" if db_status else "disconnected",
        "memory": memory_stats.get("status", "unknown"),
        "version": "2.1.0",
        "timestamp": asyncio.get_event_loop().time()
    }

@app.post("/auth/signup")
@limiter.limit("5/minute")
async def signup(creds: AuthCredentials, request: Request):
    if not supabase:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Auth service unavailable")
    
    try:
        auth_response = supabase.auth.sign_up({
            "email": creds.email,
            "password": creds.password
        })
        
        if not auth_response.user:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Signup failed")
        
        user_id = auth_response.user.id
        QuotaCRUD.increment_quota(user_id, is_registered=True)
        
        logger.info(f"New user: {creds.email}")
        return {
            "success": True,
            "message": "Account created successfully",
            "user_id": user_id,
            "email": creds.email
        }
        
    except Exception as e:
        logger.error(f"Signup error: {e}")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

@app.post("/auth/login")
@limiter.limit("10/minute")
async def login(creds: AuthCredentials, request: Request):
    if not supabase:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Auth service unavailable")
    
    try:
        auth_response = supabase.auth.sign_in_with_password({
            "email": creds.email,
            "password": creds.password
        })
        
        if not auth_response.user or not auth_response.session:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
        
        logger.info(f"User login: {creds.email}")
        return {
            "success": True,
            "access_token": auth_response.session.access_token,
            "user_id": auth_response.user.id,
            "email": auth_response.user.email
        }
    except Exception as e:
        logger.warning(f"Login error: {e}")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

async def handle_file_uploads(user_id: str, files: List[UploadFile]) -> str:
    """Process uploaded files with validation"""
    from app.impl.ocr_service_impl import image_text_extractor_impl
    from app.impl.knowledge_agent_impl import create_rag_tool_impl
    
    user_path = os.path.join(settings.UPLOAD_PATH, user_id)
    os.makedirs(user_path, exist_ok=True)
    
    ocr_context = ""
    loop = asyncio.get_running_loop()
    
    allowed_exts = getattr(settings, "ALLOWED_EXTENSIONS", ['.png', '.jpg', '.jpeg', '.pdf', '.txt', '.md'])
    max_size = getattr(settings, "MAX_UPLOAD_SIZE_MB", 10) * 1024 * 1024
    
    for file in files:
        ext = os.path.splitext(file.filename)[1].lower()
        
        if ext not in allowed_exts:
            ocr_context += f"\n[File {file.filename} skipped: unsupported format]"
            continue
        
        content = await file.read()
        if len(content) > max_size:
            ocr_context += f"\n[File {file.filename} skipped: exceeds size limit]"
            continue
        
        safe_filename = "".join(c for c in file.filename if c.isalnum() or c in "._- ").strip()
        if not safe_filename:
            safe_filename = f"upload_{asyncio.get_event_loop().time()}{ext}"
        
        file_path = os.path.join(user_path, safe_filename)
        
        try:
            with open(file_path, "wb") as f:
                f.write(content)
        except Exception as e:
            logger.error(f"File write error: {e}")
            ocr_context += f"\n[File {file.filename} upload failed]"
            continue
        
        if ext in ['.png', '.jpg', '.jpeg']:
            try:
                txt = await loop.run_in_executor(
                    process_executor,
                    image_text_extractor_impl,
                    user_id, safe_filename
                )
                ocr_context += f"\n[Image {safe_filename}]: {txt[:500]}"
            except Exception as e:
                logger.error(f"OCR error: {e}")
                ocr_context += f"\n[OCR failed for {safe_filename}]"
        else:
            try:
                await loop.run_in_executor(
                    process_executor,
                    create_rag_tool_impl,
                    user_id
                )
                ocr_context += f"\n[Document {safe_filename} indexed. Use 'local_document_retriever' to query it.]"
            except Exception as e:
                logger.error(f"RAG error: {e}")
                ocr_context += f"\n[Indexing failed for {safe_filename}]"
    
    return ocr_context

@app.post("/api/chat")
@limiter.limit("30/minute")
async def chat(
    request: Request,
    query: str = Form(""),
    user_id: str = Depends(verify_quota),
    email: Optional[str] = Form(None),
    files: List[UploadFile] = File([])
):
    """Main chat endpoint with enhanced error handling"""
    from app.core.memory_manager import update_session_on_response
    from langchain_core.messages import HumanMessage
    
    token = user_id_context.set(user_id)
    
    try:
        try:
            safe_input = SecureChatInput(user_id=user_id, query=query)
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, {"error": "validation_error", "message": str(e)})
        
        logger.info(f"[Chat] {safe_input.user_id[:10]}... | Query length: {len(query)}")
        
        ocr_context = ""
        if files:
            ocr_context = await handle_file_uploads(user_id, files)
        
        import datetime
        now = datetime.datetime.now()
        full_query = (
            f"{query}{ocr_context}\n\n"
            f"[Context: {now.strftime('%A, %Y-%m-%d %H:%M')}, Email: {email or 'guest'}]"
        )
        
        input_message = {
            "messages": [HumanMessage(content=full_query)],
            "user_id": user_id,
            "user_email": email or "guest",
            "retry_count": 0
        }
        
        config = {
            "configurable": {"thread_id": user_id},
            "recursion_limit": 25
        }
        
        if not hasattr(app.state, "agent_graph"):
            raise HTTPException(500, {"error": "service_unavailable", "message": "Agent not initialized"})
        
        try:
            final_state = await asyncio.wait_for(
                app.state.agent_graph.ainvoke(input_message, config),
                timeout=120.0
            )
        except asyncio.TimeoutError:
            raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, {
                "error": "timeout",
                "message": "Request took too long. Please try a simpler query."
            })
        
        if not final_state.get("messages"):
            raise HTTPException(500, {"error": "no_output", "message": "Agent produced no response"})
        
        raw = final_state['messages'][-1].content
        answer = " ".join([str(x) for x in raw]) if isinstance(raw, list) else str(raw)
        
        if not answer.strip():
            answer = "Task completed successfully."
        
        update_session_on_response(user_id, answer)
        
        return {
            "success": True,
            "answer": answer,
            "user_id": user_id,
            "timestamp": now.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Chat error: {e}")
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            {"error": "internal_error", "message": "An error occurred processing your request"}
        )
    finally:
        user_id_context.reset(token)

@app.post("/mcp", response_model=MCPResponse)
@limiter.limit("100/minute")
async def mcp_endpoint(request: Request, mcp_req: MCPRequest = Body(...)):
    """MCP endpoint with proper error handling"""
    
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
        
        call_params = params.copy()
        if "user_id" in call_params:
            del call_params["user_id"]
        
        if asyncio.iscoroutinefunction(func):
            result = await asyncio.wait_for(func(**call_params), timeout=60.0)
        else:
            result = func(**call_params)
        
        return MCPResponse(result=result, id=mcp_req.id)
        
    except asyncio.TimeoutError:
        logger.error(f"MCP timeout ({method_name})")
        return MCPResponse(
            error={"code": -32000, "message": "Tool execution timeout"},
            id=mcp_req.id
        )
    except Exception as e:
        logger.error(f"MCP error ({method_name}): {e}", exc_info=True)
        return MCPResponse(
            error={"code": -32000, "message": str(e)},
            id=mcp_req.id
        )
    finally:
        if token:
            user_id_context.reset(token)

@app.delete("/users/{user_id}/data")
@limiter.limit("5/minute")
async def delete_user_data(request: Request, user_id: str):
    """Delete all user data"""
    from app.services.file_handler import delete_all_user_files
    from app.services.rag_service import delete_user_vectorstore
    
    try:
        delete_all_user_files(user_id)
        delete_user_vectorstore(user_id)
        
        logger.info(f"Deleted data for: {user_id}")
        return {"success": True, "message": "User data cleared"}
        
    except Exception as e:
        logger.error(f"Delete error: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to delete data")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_error",
            "message": "An internal server error occurred",
            "type": type(exc).__name__
        }
    )

if __name__ == "__main__":
    port = int(os.getenv("PORT", 7860))
    
    uvicorn.run(
        "app.mcp_server:app",
        host="0.0.0.0",
        port=port,
        reload=settings.DEBUG,
        log_level="info",
        access_log=settings.DEBUG,
        workers=1
    )