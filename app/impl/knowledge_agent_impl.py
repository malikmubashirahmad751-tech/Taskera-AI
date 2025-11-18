import os
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_text_splitters.character import RecursiveCharacterTextSplitter
from app.core.config import settings
from app.core.logger import logger
from app.services.rag_service import (
    _get_or_create_user_chroma,
    _load_documents_from_directory,
    DATA_PATH,
    UPLOAD_PATH
)

def create_rag_tool_impl(user_id: str) -> str:
    """
    Creates/updates the RAG retriever for the user.
    This is now an explicit MCP method.
    """
    logger.info(f"[MCP-RAG] Indexing RAG for user '{user_id}'.")
    user_upload_path = os.path.join(UPLOAD_PATH, user_id)
    os.makedirs(DATA_PATH, exist_ok=True)
    os.makedirs(user_upload_path, exist_ok=True)

    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/embedding-001",
        google_api_key=settings.gemini_api_key
    )

    db = _get_or_create_user_chroma(user_id, embeddings)
    
    all_docs = _load_documents_from_directory(DATA_PATH) + _load_documents_from_directory(user_upload_path)
    if all_docs:
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
        chunks = text_splitter.split_documents(all_docs)
        db.add_documents(chunks, overwrite=True) 
        logger.info(f"[MCP-RAG] Indexed {len(chunks)} chunks for user '{user_id}'.")
        return f"Successfully indexed {len(chunks)} chunks from {len(all_docs)} documents."
    else:
        logger.info(f"[MCP-RAG] No documents found to index for user '{user_id}'.")
        return "No documents found to index."

def retrieve_info_impl(query: str, user_id: str) -> str:
    """
    Retrieve text relevant to the user query.
    This is the *implementation* of the RAG tool.
    """
    logger.info(f"[MCP-RAG] Retrieving info for user '{user_id}' with query: '{query}'")
    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/embedding-001",
        google_api_key=settings.gemini_api_key
    )
    db = _get_or_create_user_chroma(user_id, embeddings)
    retriever = db.as_retriever(search_kwargs={"k": 3})

    try:
        results = retriever.invoke(query)
    except AttributeError: 
        results = retriever.get_relevant_documents(query)
    except Exception as e:
        logger.error(f"[MCP-RAG] Error retrieving info for '{user_id}': {e}")
        return f"Error: {e}"

    if not results:
        return "No relevant information found in your uploaded or system documents."

    return "\n\n".join([doc.page_content for doc in results])