import os
import asyncio
import uvicorn
from typing import Optional, Any, Dict, List
from fastapi import (
    FastAPI, HTTPException, Body, Request,
    Form, File, UploadFile
)
from fastapi.middleware.cors import CORSMiddleware  
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logger import logger
from app.services.scheduler import start_scheduler, shutdown_scheduler

from app.core.memory_manager import get_user_checkpointer, update_session_on_response, clear_user_session
from app.agents.controller_agent import app as agent_app
from app.mcp_client import call_mcp, MCPError, shutdown_mcp_client

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

from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from app.core.crud import save_refresh_token
from app.impl.google_tools_impl import list_calendar_events_impl, create_calendar_event_impl

app = FastAPI(
    title="Taskera AI Unified Server (MCP + ACP)",
    description="Provides all tools and chat via a single API"
)

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

UPLOAD_PATH = "user_files"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".gif"}


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

def delete_all_user_data_impl(user_id: str) -> dict:
    """A helper to combine multiple delete actions for the admin agent."""
    if not user_id:
        raise ValueError("user_id is required")
    try:
        delete_all_user_files(user_id)
        delete_user_vectorstore(user_id)
        clear_user_session(user_id) 
        logger.info(f"[MCP-Admin] All data deleted for user: {user_id}")
        return {"status": "success", "user_id": user_id}
    except Exception as e:
        logger.error(f"[MCP-Admin] Error deleting all data for user {user_id}: {e}", exc_info=True)
        raise e

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
    "delete_all_user_data": delete_all_user_data_impl,
}

@app.get("/")
def read_root():
    return {"message": "Taskera AI Unified Server is running."}


@app.get("/auth/google")
async def auth_google_start(user_id: str):
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
        access_type="offline",
        prompt="consent",
        state=user_id  
    )
    
    logger.info(f"Redirecting user {user_id} to Google for auth...")
    return RedirectResponse(authorization_url)


@app.get("/auth/google/callback")
async def auth_google_callback(request: Request, code: str, state: str):
    user_id = state 
    logger.info(f"Received Google auth callback for user: {user_id}")

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
        
        refresh_token = credentials.refresh_token
        if not refresh_token:
            logger.error(f"No refresh token received for user {user_id}.")
            return {"status": "error", "message": "No refresh token. Please revoke app access in your Google account and try again."}

        success = save_refresh_token(user_id_string=user_id, token=refresh_token)
        
        if success:
            logger.info(f"Successfully saved refresh token for user: {user_id}")
            return RedirectResponse("http://localhost:5500?auth=success")
        else:
            raise HTTPException(status_code=500, detail="Failed to save refresh token to database.")
            
    except Exception as e:
        logger.error(f"Error in Google callback for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@app.post("/mcp", response_model=MCPResponse)
async def mcp_endpoint(request: MCPRequest = Body(...)):
    method_name = request.method
    params = request.params or {}
    logger.info(f"[MCP Server] Request: '{method_name}'")

    if method_name not in TOOL_REGISTRY:
        return MCPResponse(
            error={"code": -32601, "message": "Method not found"},
            id=request.id
        )
    try:
        func = TOOL_REGISTRY[method_name]
        if asyncio.iscoroutinefunction(func):
            result = await func(**params)
        else:
            result = func(**params)
        return MCPResponse(result=result, id=request.id)
    except Exception as e:
        logger.error(f"[MCP Server] Error in '{method_name}': {e}", exc_info=True)
        return MCPResponse(
            error={"code": -32000, "message": str(e)},
            id=request.id
        )

@app.post("/api/chat")
async def http_chat_endpoint(
    query: str = Form(""),
    user_id: str = Form(...),
    files: List[UploadFile] = File([])
):
    
    logger.info(f"[HTTP API-POST] Chat request for user_id: {user_id}")
    
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
            try:
                with open(file_path, "wb") as f:
                    f.write(await file.read())
            except Exception as e:
                logger.error(f"Failed to save file {file.filename}: {e}")
                continue

            file_ext = os.path.splitext(file.filename)[1].lower()
            if file_ext in IMAGE_EXTENSIONS:
                image_names.append(file.filename)
                try:
                    extracted_text = await call_mcp("image_text_extractor", {
                        "user_id": user_id, "file_name": file.filename
                    })
                    ocr_texts.append(f"--- Text from '{file.filename}' ---\n{extracted_text}\n")
                except MCPError as e:
                    ocr_texts.append(f"--- OCR FAILED for '{file.filename}': {e} ---")
            else:
                doc_names.append(file.filename)
                has_docs_for_rag = True
    
    if has_docs_for_rag:
        try:
            await call_mcp("index_rag_documents", {"user_id": user_id})
        except MCPError as e:
            logger.error(f"Failed MCP-RAG indexing: {e}")
            
    system_prompt_parts = []
    if doc_names:
        system_prompt_parts.append(f"User uploaded {len(doc_names)} docs: {', '.join(doc_names)}. I indexed them.")
    if image_names:
        system_prompt_parts.append(f"User uploaded {len(image_names)} images: {', '.join(image_names)}. OCR Results:\n{''.join(ocr_texts)}")
    
    if not system_prompt_parts:
        agent_input_content = query
    else:
        query_part = f"User prompt: '{query}'" if query else "Confirm receipt of files."
        agent_input_content = "\n\n".join(system_prompt_parts) + f"\n\n{query_part}"

    if not agent_input_content.strip() and not files:
        raise HTTPException(status_code=400, detail="Provide message or file.")
        
    try:
        graph_with_memory = agent_app.with_config(checkpointer=user_checkpointer)
        input_message = {"messages": [("human", agent_input_content)], "user_id": user_id}
        final_state = await graph_with_memory.ainvoke(input_message, config)
        
        if final_state.get('messages'):
            result_message = final_state['messages'][-1]
            answer = str(result_message.content)
            update_session_on_response(user_id, answer)
            return {"answer": answer, "user_id": user_id}
        else:
            raise HTTPException(status_code=500, detail="No response from agent.")
    except Exception as e:
        logger.exception(f"Graph error: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {e}")

@app.delete("/users/{user_id}/data")
def delete_user_data_endpoint(user_id: str):
    try:
        result = delete_all_user_data_impl(user_id)
        return {"message": "Data cleared.", "details": result}
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
    uvicorn.run("app.mcp_server:app", host="127.0.0.1", port=8000, reload=True)