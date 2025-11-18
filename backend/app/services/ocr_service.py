import logging
import asyncio
from pydantic.v1 import BaseModel, Field
from langchain_core.tools import StructuredTool
from app.mcp_client import call_mcp
from app.core.logger import logger

async def _ocr_proxy(*, user_id: str, file_name: str) -> str:
    logger.info(f"[OCR Proxy] user={user_id}, file={file_name}")
    try:
        return await call_mcp("image_text_extractor", {
            "user_id": user_id,
            "file_name": file_name
        })
    except Exception as e:
        logger.error(f"[OCR Proxy] MCP Error: {e}")
        return f"OCR error: {e}"

class OcrToolArgs(BaseModel):
    file_name: str = Field(description="Filename of the uploaded image.")

def create_ocr_tool(user_id: str) -> StructuredTool:

    async def user_specific(file_name: str) -> str:
        return await _ocr_proxy(user_id=user_id, file_name=file_name)

    return StructuredTool.from_function(
        name="image_text_extractor",
        coroutine=user_specific,
        args_schema=OcrToolArgs,
        description="Extract text from an image file for this user."
    )
