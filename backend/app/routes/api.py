import os
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from datetime import datetime  # Import datetime

from app.core.agent import research_query
from app.core.config import settings
from app.services.rag_system import create_rag_tool
from app.core.logger import logger
from app.core.file_handler import delete_specific_user_file, delete_all_user_files
from app.tools.image_ocr_tool import image_text_extractor  # Import the OCR tool

# --- MODIFICATION: Import memory and session management functions ---
from app.core.session_manager import get_user_memory
from app.services.rag_system import delete_user_vectorstore
# --- END MODIFICATION ---

router = APIRouter()
UPLOAD_PATH = "user_files"
# Define allowed image extensions
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".gif"} # Added .gif

class ResearchRequest(BaseModel):
    query: str = Field(...)
    user_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

@router.post(
    "/api/upload",
    summary="Upload a user-specific document",
)
async def upload_file(
    file: UploadFile = File(...),
    user_id: str = Form(None, example="a1b2c3d4-e5f6-7890-1234-567890abcdef")
):
    """
    Upload a document for a specific user. The file is stored until
    manually deleted via the DELETE endpoints.

    If an image is uploaded, it will be processed for text and saved to memory.
    If a document is uploaded, it will be indexed for RAG.
    """
    try:
        if not user_id:
            user_id = str(uuid.uuid4())
            logger.info(f"No user_id provided. Generated new one: {user_id}")

        user_upload_path = os.path.join(UPLOAD_PATH, user_id)
        os.makedirs(user_upload_path, exist_ok=True)
        file_path = os.path.join(user_upload_path, file.filename)
        upload_time = datetime.now().isoformat() # Get current time

        with open(file_path, "wb") as f:
            f.write(await file.read())
        logger.info(f"File for user '{user_id}' saved to: {file_path}")

        # --- New Logic: Check File Type ---
        file_ext = os.path.splitext(file.filename)[1].lower()

        file_details = {
            "name": file.filename,
            "uploaded_by": user_id, # Using user_id as uploader
            "upload_time": upload_time
        }

        if file_ext in IMAGE_EXTENSIONS:
            # It's an image: run OCR
            logger.info(f"Image file detected. Running OCR for user '{user_id}' on file '{file.filename}'")

            # --- FIX: Call the tool using .invoke() with a dictionary ---
            extracted_text = image_text_extractor.invoke({
                "user_id": user_id,
                "file_name": file.filename
            })

            # --- MODIFICATION: Save extracted text to agent's memory ---
            try:
                memory = get_user_memory(user_id=user_id)
                # We save this as an 'ai' message (output) from a system 'input'
                memory.save_context(
                    {"input": f"(System note: User uploaded image '{file.filename}')"},
                    {"output": extracted_text}
                )
                logger.info(f"Saved extracted text from '{file.filename}' to memory for user '{user_id}'.")
            except Exception as e:
                logger.error(f"Failed to save extracted text to memory for user '{user_id}': {e}")
            # --- END MODIFICATION ---

            follow_up_prompt = "What would you like to do with this text? (e.g., 'summarize this', 'translate to French', 'find key points')"

            return JSONResponse(
                content={
                    "message": f"Image '{file.filename}' uploaded successfully and text extracted.",
                    "user_id": user_id,
                    "file_details": file_details,
                    "extracted_text": extracted_text,
                    "follow_up_prompt": follow_up_prompt
                },
                status_code=200
            )

        else:
            # It's a document: run RAG indexing (original behavior)
            logger.info(f"Document file detected. Indexing RAG for user '{user_id}'.")
            create_rag_tool(api_key=settings.openai_api_key, user_id=user_id)
            logger.info(f"RAG tool re-indexed for user '{user_id}'.")

            return JSONResponse(
                content={
                    "message": f"File '{file.filename}' uploaded successfully and indexed.",
                    "user_id": user_id,
                    "file_details": file_details,
                    "note": "File is stored and indexed for RAG."
                },
                status_code=200
            )

    except Exception as e:
        logger.exception(f"Critical error during file upload for user '{user_id}': {e}")
        raise HTTPException(status_code=500, detail=f"File upload failed: {e}")


@router.post(
    "/api/research",
    summary="Process a user query (Research Endpoint)",
)
async def handle_research_query(request: ResearchRequest):
    if not request.query:
        raise HTTPException(status_code=422, detail="Query cannot be empty.")
    try:
        result = research_query(request.query, user_id=request.user_id)
        return JSONResponse(
            content={"answer": result, "user_id": request.user_id},
            status_code=200
        )
    except Exception as e:
        logger.exception(f"Error processing query for user '{request.user_id}': {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred.")


@router.post(
    "/api/chat",
    summary="Process a user query (Chat Endpoint)",
    responses={
        200: {"description": "Successful response from the agent."},
        422: {"description": "Validation Error (e.g., missing query)."},
        500: {"description": "Internal server error while processing the query."}
    }
)
async def handle_chat_query(request: ResearchRequest):
    """
    This endpoint is a duplicate of /api/research to satisfy the
    current frontend fetch request.
    """
    return await handle_research_query(request)

@router.delete(
    "/users/{user_id}/files/{filename}",
    summary="Delete a specific user file",
)
def delete_file(user_id: str, filename: str):
    """Endpoint to delete a single file for a user and re-index."""
    success = delete_specific_user_file(user_id, filename)
    if not success:
        raise HTTPException(status_code=404, detail="File not found or error during deletion.")

    # --- MODIFICATION: Re-index RAG after file deletion ---
    try:
        logger.info(f"Re-indexing RAG for user '{user_id}' after file deletion.")
        create_rag_tool(api_key=settings.openai_api_key, user_id=user_id)
    except Exception as e:
        logger.error(f"Failed to re-index RAG after deleting file for user '{user_id}': {e}")
        # Don't fail the request, but log the error
    # --- END MODIFICATION ---
    
    return {"status": "success", "message": f"File '{filename}' deleted and index updated."}


@router.delete(
    "/users/{user_id}/data",
    summary="Delete all of a user's data",
)
def delete_all_data(user_id: str):
    """Endpoint to delete all data (session, files, index) for a user."""
    
    # --- MODIFICATION: Call all cleanup functions ---
    try:
        # 1. Delete all physical files
        delete_all_user_files(user_id)
        
        # 2. Delete the user's vector store (RAG index)
        delete_user_vectorstore(user_id)
        
        # 3. Clear the user's session memory
        clear_user_session(user_id)
        
        logger.info(f"All data (files, index, session) for user {user_id} has been cleared.")
        return {"status": "success", "message": f"All data for user {user_id} has been cleared."}
    except Exception as e:
        logger.error(f"Error during full data deletion for user '{user_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error clearing user data: {e}")
    # --- END MODIFICATION ---

