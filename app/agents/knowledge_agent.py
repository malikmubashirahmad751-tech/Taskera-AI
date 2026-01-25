import asyncio
from pydantic.v1 import BaseModel, Field
from langchain_core.tools import StructuredTool
from app.mcp_client import call_mcp
from app.core.logger import logger
from app.core.context import get_current_user_id 

class RagToolArgs(BaseModel):
    """Arguments for RAG retrieval"""
    query: str = Field(
        ...,
        description="The search query to find relevant information in user's documents"
    )

async def _retrieve_info_proxy(query: str) -> str:
    """
    Proxy to MCP server for RAG retrieval.
    Injects the user_id from the current context.
    """
    user_id = get_current_user_id()
    logger.info(f"[RAG Proxy] Request for user={user_id} query='{query}'")
    
    params = {"query": query}
    
    if user_id:
        params["user_id"] = user_id
    
    try:
        result = await call_mcp("local_document_retriever", params)
        return str(result)
        
    except Exception as e:
        logger.error(f"[RAG] Retrieval error: {e}")
        return f"Error retrieving documents: {str(e)}"

def _build_retriever_tool() -> StructuredTool:
    """Build the RAG retriever tool"""
    return StructuredTool.from_function(
        func=None,
        coroutine=_retrieve_info_proxy, 
        name="local_document_retriever",
        description=(
            "Search and retrieve relevant information from the user's uploaded documents. "
            "Use this when the user asks about content from PDFs, Word docs, or text files they uploaded. "
            "The system uses semantic search to find the most relevant passages."
        ),
        args_schema=RagToolArgs
    )

local_document_retriever_tool = _build_retriever_tool()