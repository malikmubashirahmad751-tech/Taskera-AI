import asyncio
from pydantic.v1 import BaseModel, Field
from langchain_core.tools import StructuredTool
from app.mcp_client import call_mcp
from app.core.logger import logger

class OcrToolArgs(BaseModel):
    """Arguments for OCR text extraction"""
    file_name: str = Field(
        ...,
        description="Name of the uploaded image file to extract text from"
    )

async def _ocr_proxy(*, user_id: str, file_name: str) -> str:
    """
    Proxy function for OCR via MCP
    """
    logger.info(f"[OCR] Extracting text for user={user_id}, file={file_name}")
    
    try:
        result = await call_mcp("image_text_extractor", {
            "user_id": user_id,
            "file_name": file_name
        })
        return str(result)
        
    except Exception as e:
        logger.error(f"[OCR] Error: {e}")
        return f"OCR extraction failed: {str(e)}"

def create_ocr_tool(user_id: str) -> StructuredTool:
    """
    Create a user-specific OCR tool.
    This is called during agent initialization to bind the user_id.
    """
    async def user_specific_ocr(file_name: str) -> str:
        return await _ocr_proxy(user_id=user_id, file_name=file_name)
    
    return StructuredTool.from_function(
        name="image_text_extractor",
        coroutine=user_specific_ocr,
        args_schema=OcrToolArgs,
        description=(
            "Extract text from an uploaded image file using OCR (Optical Character Recognition). "
            "Supports: PNG, JPG, JPEG formats. "
            "Use this when the user uploads an image containing text (screenshots, documents, signs, etc.)"
        )
    )