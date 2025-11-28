import asyncio
from pydantic.v1 import BaseModel, Field
from langchain_core.tools import StructuredTool
from app.mcp_client import call_mcp
from app.core.logger import logger

class RagToolArgs(BaseModel):
    """Arguments for RAG retrieval"""
    query: str = Field(
        ...,
        description="The search query to find relevant information in user's documents"
    )
    user_id: str = Field(
        ...,
        description="User ID (required for retrieving user-specific documents)"
    )

async def retrieve_info_impl(query: str, user_id: str) -> str:
    """
    Retrieve information from user's uploaded documents using RAG.
    This delegates to the MCP server for actual execution.
    """
    logger.info(f"[RAG] Retrieving for user={user_id}, query='{query}'")
    
    try:
        result = await call_mcp("local_document_retriever", {
            "query": query,
            "user_id": user_id
        })
        return str(result)
        
    except Exception as e:
        logger.error(f"[RAG] Retrieval error: {e}")
        return f"Error retrieving documents: {str(e)}"

def _build_retriever_tool() -> StructuredTool:
    """Build the RAG retriever tool"""
    return StructuredTool.from_function(
        func=None,
        coroutine=retrieve_info_impl,
        name="local_document_retriever",
        description=(
            "Search and retrieve relevant information from the user's uploaded documents. "
            "Use this when the user asks about content from PDFs, Word docs, or text files they uploaded. "
            "The system uses semantic search to find the most relevant passages."
        ),
        args_schema=RagToolArgs
    )


local_document_retriever_tool = _build_retriever_tool()