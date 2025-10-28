import os
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


from app.core.agent import research_query
from app.core.config import settings
from app.services.rag_system import create_rag_tool 
from app.core.logger import logger
from app.core.file_handler import delete_specific_user_file, delete_all_user_files

router = APIRouter()
UPLOAD_PATH = "user_files" 

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
    """
    try:
        if not user_id:
            user_id = str(uuid.uuid4())
            logger.info(f"No user_id provided. Generated new one: {user_id}")

        user_upload_path = os.path.join(UPLOAD_PATH, user_id)
        os.makedirs(user_upload_path, exist_ok=True)
        file_path = os.path.join(user_upload_path, file.filename)

        with open(file_path, "wb") as f:
            f.write(await file.read())
        logger.info(f"File for user '{user_id}' saved to: {file_path}")


        create_rag_tool(api_key=settings.openai_api_key, user_id=user_id)
        logger.info(f"RAG tool re-indexed for user '{user_id}'.")

        return JSONResponse(
            content={
                "message": f"File '{file.filename}' uploaded successfully.",
                "user_id": user_id,
                "note": "File is stored and can be deleted via the API."
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
    return {"status": "success", "message": f"File '{filename}' deleted and index cleared."}


@router.delete(
    "/users/{user_id}/data", 
    summary="Delete all of a user's data",
)
def delete_all_data(user_id: str):
    """Endpoint to delete all data (session, files, index) for a user."""
    delete_all_user_files(user_id)
    return {"status": "success", "message": f"All data for user {user_id} has been cleared."}