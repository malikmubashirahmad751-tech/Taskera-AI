import os
import re
import asyncio
import uvicorn
from typing import Optional, Any, Dict, List

from fastapi import (
    FastAPI, HTTPException, Body, Request,
    Form, File, UploadFile, Depends
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from fastapi.responses import RedirectResponse, JSONResponse
from google_auth_oauthlib.flow import Flow

from langchain_core.messages import HumanMessage 

from starlette.middleware.sessions import SessionMiddleware
from starlette_csrf.middleware import CSRFMiddleware

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.logger import logger
from app.core.database import supabase
from app.services.scheduler import start_scheduler, shutdown_scheduler
from app.core.memory_manager import get_user_checkpointer, update_session_on_response, clear_user_session
from app.agents.controller_agent import app as agent_app
from app.mcp_client import MCPError, shutdown_mcp_client
from app.core.crud import save_refresh_token

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
from app.impl.google_tools_impl import list_calendar_events_impl, create_calendar_event_impl

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Taskera AI Unified Server",
    description="Unified MCP + ACP Server with Real-World Auth & Quotas"
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

origins = [
    "http://localhost:5500",
    "http://127.0.0.1:5500",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = os.getenv("CSRF_SESSION_SECRET", "unsafe-local-secret-key-change-me")
CSRF_SECRET = os.getenv("CSRF_TOKEN_SECRET", "unsafe-local-csrf-secret-change-me")

app.add_middleware(
    CSRFMiddleware,
    secret=CSRF_SECRET,
    sensitive_cookies={"taskera_session"},
    cookie_path="/",
    header_name="x-csrftoken", 
    exempt_urls=[
        re.compile(r"^/auth/google"), 
        re.compile(r"^/auth/signup"), 
        re.compile(r"^/auth/login"), 
    ])

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="taskera_session",
    max_age=3600 
)

UPLOAD_PATH = "user_files"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".gif"}

class AuthCredentials(BaseModel):
    email: str = Field(..., pattern=r"^\S+@\S+\.\S+$")
    password: str = Field(..., min_length=6)

@app.post("/auth/signup")
@limiter.limit("5/minute")
async def auth_signup(creds: AuthCredentials, request: Request):
    """
    Creates a new user in Supabase.
    """
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not connected.")
    
    try:
        auth_response = supabase.auth.sign_up({
            "email": creds.email,
            "password": creds.password,
        })
        
        if not auth_response.user:
             raise HTTPException(status_code=400, detail="Signup failed. User already exists or invalid data.")

        user_id = auth_response.user.id
        
        supabase.table("usage_quotas").upsert({
            "identifier": user_id,
            "is_registered": True,
            "request_count": 0,
            "last_request_at": "now()"
        }).execute()

        return {
            "message": "Signup successful", 
            "user_id": user_id, 
            "email": creds.email
        }
        
    except Exception as e:
        logger.error(f"Signup Error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/auth/login")
@limiter.limit("10/minute")
async def auth_login(creds: AuthCredentials, request: Request):
    """
    Logs in a user and returns their real User ID (UUID).
    """
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not connected.")
        
    try:
        auth_response = supabase.auth.sign_in_with_password({
            "email": creds.email,
            "password": creds.password,
        })
        
        if not auth_response.user:
            raise HTTPException(status_code=401, detail="Invalid credentials.")

        return {
            "message": "Login successful",
            "access_token": auth_response.session.access_token,
            "user_id": auth_response.user.id, 
            "email": auth_response.user.email
        }
    except Exception as e:
        logger.warning(f"Login failed for {creds.email}: {e}")
        raise HTTPException(status_code=401, detail="Invalid email or password.")



async def check_usage_quota(request: Request, user_id: str = Form(...)):
    """
    Enforces 10 request limit for 'guest' users.
    Registered users (UUIDs) bypass this check.
    """
    if not supabase:
        return user_id

    
    is_guest_session = user_id.startswith("guest") or user_id == "unknown" or user_id == "undefined"
    
    client_ip = request.client.host
    identifier = client_ip if is_guest_session else user_id

    try:
        response = supabase.table("usage_quotas").select("*").eq("identifier", identifier).execute()
        
        current_count = 0
        is_registered = False
        
        if response.data and isinstance(response.data, dict):
            record = response.data.get(0)
            if record:
                current_count = record.get("request_count", 0)
                is_registered = record.get("is_registered", False)
        
        FREE_LIMIT = 10
        if is_guest_session and not is_registered and current_count >= FREE_LIMIT:
            logger.warning(f"[Quota] Limit reached for guest IP {client_ip}")
            raise HTTPException(
                status_code=402, 
                detail="Free trial ended. Please create an account to continue."
            )

        if response.data:
            supabase.table("usage_quotas").update({
                "request_count": current_count + 1,
                "last_request_at": "now()"
            }).eq("identifier", identifier).execute()
        else:
            supabase.table("usage_quotas").insert({
                "identifier": identifier,
                "request_count": 1,
                "is_registered": not is_guest_session
            }).execute()
            
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"[Quota] Error checking quota: {e}")
        pass

    return user_id


class MCPRequest(BaseModel):
    jsonrpc: str = Field(..., pattern="^2.0$")
    method: str
    params: Optional[Dict[str, Any]] = None
    id: int | str

class MCPResponse(BaseModel):
    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[dict] = None
    id: int | str

TOOL_REGISTRY = {
    "google_calendar_list": list_calendar_events_impl,
    "google_calendar_create": create_calendar_event_impl, 
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


@app.get("/csrf-token")
def get_csrf_token(request: Request):
    token = request.scope.get("csrf_token")
    return {"csrf_token": token}

@app.get("/")
@limiter.limit("60/minute")
def read_root(request: Request):
    return {"message": "Taskera AI Unified Server is running."}

@app.get("/auth/google")
@limiter.limit("5/minute")
async def auth_google_start(request: Request, user_id: str):
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Google Auth is not configured.")
    
    flow = Flow.from_client_config(
        client_config={
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=["https://www.googleapis.com/auth/calendar"],
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
    )
    authorization_url, state = flow.authorization_url(
        access_type="offline", prompt="consent", state=user_id  
    )
    return RedirectResponse(authorization_url)

@app.get("/auth/google/callback")
async def auth_google_callback(request: Request, code: str, state: str):
    user_id = state 
    try:
        flow = Flow.from_client_config(
            client_config={
                "web": {
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=["https://www.googleapis.com/auth/calendar"],
            redirect_uri=settings.GOOGLE_REDIRECT_URI,
        )
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        if credentials.refresh_token:
            save_refresh_token(user_id_string=user_id, token=credentials.refresh_token)
            
        return RedirectResponse("http://localhost:5500?auth=success")
            
    except Exception as e:
        logger.error(f"Auth Callback Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/mcp", response_model=MCPResponse)
@limiter.limit("60/minute") 
async def mcp_endpoint(request: Request, mcp_req: MCPRequest = Body(...)):
    method_name = mcp_req.method
    params = mcp_req.params or {}

    if method_name not in TOOL_REGISTRY:
        return MCPResponse(error={"code": -32601, "message": "Method not found"}, id=mcp_req.id)
    try:
        func = TOOL_REGISTRY[method_name]
        if asyncio.iscoroutinefunction(func):
            result = await func(**params)
        else:
            result = func(**params)
        return MCPResponse(result=result, id=mcp_req.id)
    except Exception as e:
        logger.error(f"MCP Error: {e}")
        return MCPResponse(error={"code": -32000, "message": str(e)}, id=mcp_req.id)

class SecureChatInput(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=50)
    query: str = Field(..., max_length=2000)
    
    @field_validator('query')
    @classmethod
    def block_injection(cls, v: str) -> str:
        if "ignore previous instructions" in v.lower():
            raise ValueError("Invalid input detected.")
        return v.strip()

@app.post("/api/chat")
@limiter.limit("20/minute") 
async def http_chat_endpoint(
    request: Request, 
    query: str = Form(""),
    user_id: str = Depends(check_usage_quota), 
    files: List[UploadFile] = File([])
):
    try:
        safe_input = SecureChatInput(user_id=user_id, query=query)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    logger.info(f"[Chat] Request from {safe_input.user_id}")
    
    user_checkpointer = get_user_checkpointer(user_id)
    config = {"configurable": {"thread_id": user_id}}
    
    ocr_texts = []
    doc_names = []
    image_names = []
    has_docs_for_rag = False

    if files:
        user_upload_path = os.path.join(UPLOAD_PATH, user_id)
        os.makedirs(user_upload_path, exist_ok=True)

        for file in files:
            file_path = os.path.join(user_upload_path, file.filename)
            with open(file_path, "wb") as f:
                f.write(await file.read())

            ext = os.path.splitext(file.filename)[1].lower()
            if ext in IMAGE_EXTENSIONS:
                image_names.append(file.filename)
                try:
                    txt = image_text_extractor_impl(user_id, file.filename)
                    ocr_texts.append(f"--- Text from '{file.filename}' ---\n{txt}\n")
                except Exception as e:
                    ocr_texts.append(f"OCR Error: {e}")
            else:
                doc_names.append(file.filename)
                has_docs_for_rag = True
    
    if has_docs_for_rag:
        await create_rag_tool_impl(user_id=user_id)

    system_prompt_parts = []
    if doc_names:
        system_prompt_parts.append(f"User uploaded {len(doc_names)} docs: {', '.join(doc_names)}. I have indexed them.")
    if image_names:
        system_prompt_parts.append(f"User uploaded {len(image_names)} images. OCR Results:\n{''.join(ocr_texts)}")

    if not system_prompt_parts and not query:
        raise HTTPException(status_code=400, detail="Empty request.")

    full_prompt = "\n\n".join(system_prompt_parts) + f"\n\nUser: {query}"

    try:
        input_message = {"messages": [HumanMessage(content=full_prompt)], "user_id": user_id}
        final_state = await agent_app.with_config(checkpointer=user_checkpointer).ainvoke(input_message, config)
        
        if final_state.get('messages'):
            raw_content = final_state['messages'][-1].content
            if isinstance(raw_content, list):
                answer = " ".join([str(x) for x in raw_content])
            else:
                answer = str(raw_content)
            
            if not answer.strip():
                answer = "Task completed (Action performed)."

            update_session_on_response(user_id, answer)
            
            return {
                "answer": answer, 
                "response": answer, 
                "user_id": user_id,
            }
        else:
            raise HTTPException(status_code=500, detail="Agent produced no output.")

    except Exception as e:
        logger.exception(f"Agent Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/users/{user_id}/data")
def delete_user_data_endpoint(request: Request, user_id: str):
    try:
        delete_all_user_files(user_id)
        delete_user_vectorstore(user_id)
        return {"message": "Data cleared."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.on_event("startup")
async def startup_event():
    start_scheduler()

@app.on_event("shutdown")
async def shutdown_event():
    shutdown_scheduler()
    await shutdown_mcp_client()

if __name__ == "__main__":
    uvicorn.run("app.mcp_server:app", host="0.0.0.0", port=8000, reload=True)