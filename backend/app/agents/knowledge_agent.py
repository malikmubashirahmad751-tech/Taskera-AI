import asyncio
from pydantic.v1 import BaseModel, Field
from langchain_core.tools import StructuredTool
from app.mcp_client import call_mcp
from app.core.logger import logger

async def retrieve_info(query: str, *, user_id: str) -> str:
    """
    Retrieves relevant information from user-uploaded documents.

    Args:
        query (str): The query to search for in the documents.
        user_id (str): The ID of the user to retrieve documents for.

    Returns:
        str: The relevant text from the user's documents, or an error message if the retrieval fails.
    """
    logger.info(f"[RAG Proxy] user={user_id}, query={query}")
    try:
        return await call_mcp("local_document_retriever", {
            "query": query,
            "user_id": user_id
        })
    except Exception as e:
        logger.error(f"[RAG Proxy] MCP Error: {e}")
        return f"RAG error: {e}"

class RagToolArgs(BaseModel):
    query: str = Field(description="Query to search in user documents.")

def create_rag_tool(user_id: str) -> StructuredTool:

    """
    Creates a StructuredTool that retrieves information from user-uploaded documents.

    This tool takes a single argument, `query`, which is the query to search for in the user's documents.
    The tool returns a string containing the relevant text from the user's documents.

    :param user_id: The ID of the user to create the tool for.
    :return: A StructuredTool that retrieves information from user-uploaded documents for the given user.
    """
    async def user_specific(query: str) -> str:
        return await retrieve_info(query=query, user_id=user_id)

    return StructuredTool.from_function(
        name="local_document_retriever",
        coroutine=user_specific,
        args_schema=RagToolArgs,
        description="Retrieve information from user-uploaded documents."
    )
