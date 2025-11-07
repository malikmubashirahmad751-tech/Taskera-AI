import os
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List 

from app.core.config import settings
from app.core.logger import logger
from app.services.file_handler import delete_specific_user_file, delete_all_user_files
from app.services.rag_service import delete_user_vectorstore
from app.agents.knowledge_agent import create_rag_tool
from app.services.ocr_service import image_text_extractor

from app.agents.controller_agent import app as agent_app
from app.core.memory_manager import get_user_checkpointer, clear_user_session, update_session_on_response
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage

router = APIRouter()
UPLOAD_PATH = "user_files"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".gif"}

class ResearchRequest(BaseModel):
    query: str = Field(...)
    user_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


@router.post(
    "/api/chat",
    summary="Process a user query, with or without file(s)",
    responses={
        200: {"description": "Successful response from the agent."},
        422: {"description": "Validation Error (e.g., missing user_id)."},
        500: {"description": "Internal server error while processing."}
    }
)
async def handle_chat_query(
    user_id: str = Form(...),
    query: str = Form(...),
    files: Optional[List[UploadFile]] = File(None, alias="files") 
):
    """
    This is the main endpoint. It accepts FormData containing:
    - user_id (required)
    - query (required, can be empty string)
    - files (optional, can be multiple)
    
    It will process all files (if provided), sorting them into
    Images (for OCR) and Documents (for RAG), then create a unified
    prompt for the agent.
    """
    
    user_checkpointer: MemorySaver = get_user_checkpointer(user_id)
    
    agent_input = query 
    
    ocr_texts = []
    doc_names = []
    image_names = []
    has_docs_for_rag = False

    if files:
        logger.info(f"{len(files)} file(s) detected for user '{user_id}'")
        user_upload_path = os.path.join(UPLOAD_PATH, user_id)
        os.makedirs(user_upload_path, exist_ok=True)

        for file in files:
            file_path = os.path.join(user_upload_path, file.filename)
            
            try:
                with open(file_path, "wb") as f:
                    f.write(await file.read())
                logger.info(f"File for user '{user_id}' saved to: {file_path}")
            except Exception as e:
                logger.error(f"Failed to save file {file.filename} for user '{user_id}': {e}")
                continue

            file_ext = os.path.splitext(file.filename)[1].lower()

            if file_ext in IMAGE_EXTENSIONS:
                logger.info(f"Image file detected: {file.filename}. Running OCR.")
                image_names.append(file.filename)
                try:
                    extracted_text = image_text_extractor.invoke({
                        "user_id": user_id,
                        "file_name": file.filename
                    })
                    ocr_texts.append(f"--- Text from '{file.filename}' ---\n{extracted_text}\n")
                    logger.info(f"Successfully extracted text from {file.filename}")
                except Exception as e:
                    logger.error(f"Failed OCR for {file.filename}: {e}")
                    ocr_texts.append(f"--- FAILED to extract text from '{file.filename}' ---")

            else:
                logger.info(f"Document file detected: {file.filename}. Marking for RAG.")
                doc_names.append(file.filename)
                has_docs_for_rag = True
    
    if has_docs_for_rag:
        try:
            logger.info(f"Document(s) detected. Indexing RAG for user '{user_id}'.")
            create_rag_tool(api_key=settings.gemini_api_key, user_id=user_id)
            logger.info(f"RAG tool re-indexed for user '{user_id}'.")
        except Exception as e:
            logger.error(f"Failed to index RAG for user '{user_id}': {e}")
            
    system_prompt_parts = []
    
    if doc_names:
        system_prompt_parts.append(
            f"The user has uploaded {len(doc_names)} document(s): {', '.join(doc_names)}. "
            "I have successfully indexed them for RAG. "
            "The user can ask questions about them using the 'local_document_retriever' tool."
        )

    if image_names:
        system_prompt_parts.append(
            f"The user has also uploaded {len(image_names)} image(s): {', '.join(image_names)}. "
            f"I have extracted the following text from them:\n\n{''.join(ocr_texts)}"
        )

    if not system_prompt_parts:
        agent_input = query
    else:
        if not query and (doc_names or image_names):
            query_part = (
                "The user did not provide a prompt. Please just confirm you "
                "have received the file(s) and their contents (summarize the OCR text briefly "
                "or confirm the doc indexing) and ask what they would like to do."
            )
        else:
            query_part = f"The user's prompt is: '{query}'. Please answer it using the context from the files provided."
        
        agent_input = "\n\n".join(system_prompt_parts) + f"\n\n{query_part}"


    if not agent_input.strip() and not files:
        return JSONResponse(
            content={"answer": "Please provide a message or upload a file.", "user_id": user_id},
            status_code=200
        )
        
    try:
        logger.info(f"Sending final prompt to graph for user '{user_id}': '{agent_input[:250]}...'")
        graph_with_memory = agent_app.with_config(checkpointer=user_checkpointer)
        config = {"configurable": {"thread_id": user_id}}
        input_message = {
            "messages": [HumanMessage(content=agent_input)],
            "user_id": user_id 
        }

        final_state = await graph_with_memory.ainvoke(input_message, config)
        
        if not final_state.get('messages') or not isinstance(final_state['messages'], list):
             raise HTTPException(status_code=500, detail="Agent returned an invalid state.")
             
        result_message = final_state['messages'][-1]
        result = result_message.content

        update_session_on_response(user_id, result)

        return JSONResponse(
            content={"answer": result, "user_id": user_id},
            status_code=200
        )
    except Exception as e:
        logger.exception(f"Error processing query for user '{user_id}': {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred.")


@router.delete(
    "/users/{user_id}/files/{filename}",
    summary="Delete a specific user file",
)
def delete_file(user_id: str, filename: str):
    success = delete_specific_user_file(user_id, filename)
    if not success:
        raise HTTPException(status_code=404, detail="File not found or error during deletion.")
    try:
        logger.info(f"Re-indexing RAG for user '{user_id}' after file deletion.")
        create_rag_tool(api_key=settings.gemini_api_key, user_id=user_id)
    except Exception as e:
        logger.error(f"Failed to re-index RAG after deleting file for user '{user_id}': {e}")
    
    return {"status": "success", "message": f"File '{filename}' deleted and index updated."}


@router.delete(
    "/users/{user_id}/data",
    summary="Delete all of a user's data",
)
def delete_all_data(user_id: str):
    try:
        delete_all_user_files(user_id)
        delete_user_vectorstore(user_id)
        clear_user_session(user_id)
        
        logger.info(f"All data (files, index, session) for user {user_id} has been cleared.")
        return {"status": "success", "message": f"All data for user {user_id} has been cleared."}
    except Exception as e:
        logger.error(f"Error during full data deletion for user '{user_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred.")