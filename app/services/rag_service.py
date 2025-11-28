import os
import re
import shutil
import chromadb
from typing import List

from langchain_google_genai import GoogleGenerativeAIEmbeddings

try:
    from langchain_chroma import Chroma
except ImportError:
    from langchain_community.vectorstores import Chroma

from langchain_core.documents import Document

from app.core.config import get_settings
from app.core.logger import logger

settings = get_settings()

DATA_PATH = settings.DATA_PATH
UPLOAD_PATH = settings.UPLOAD_PATH
CHROMA_PATH = settings.CHROMA_PATH

_user_vectorstores = {}

def _get_sanitized_collection_name(user_id: str) -> str:
    """
    Sanitize user_id for ChromaDB collection name
    Requirements:
    - 3-63 characters
    - Alphanumeric, underscores, dots, dashes only
    - Must start and end with alphanumeric
    """
    clean = re.sub(r"[^a-zA-Z0-9._-]", "_", user_id)
    
    if not clean:
        clean = "default_user"
    
    if not clean[0].isalnum():
        clean = "u" + clean
    
    if not clean[-1].isalnum():
        clean = clean + "0"
    
    collection_name = f"user_{clean}"
    
    return collection_name[:63]

def _get_or_create_user_chroma(user_id: str) -> Chroma:
    """
    Get or create cached Chroma instance for user
    """
    global _user_vectorstores
    
    if user_id in _user_vectorstores:
        return _user_vectorstores[user_id]
    
    collection_name = _get_sanitized_collection_name(user_id)
    user_chroma_path = os.path.join(CHROMA_PATH, user_id)
    
    os.makedirs(user_chroma_path, exist_ok=True)
    
    try:
        embeddings = GoogleGenerativeAIEmbeddings(
            model="models/text-embedding-004",
            google_api_key=settings.GOOGLE_API_KEY,
            task_type="retrieval_document"
        )
        
        vectordb = Chroma(
            persist_directory=user_chroma_path,
            embedding_function=embeddings,
            collection_name=collection_name
        )
        
        _user_vectorstores[user_id] = vectordb
        
        logger.info(f"[RAG] Initialized vector store for user: {user_id}")
        return vectordb
        
    except Exception as e:
        logger.error(f"[RAG] Failed to initialize Chroma for {user_id}: {e}")
        raise

async def index_documents(user_id: str, documents: List[Document]):
    """
    Add documents to user's vector store
    """
    if not documents:
        logger.warning(f"[RAG] No documents to index for {user_id}")
        return
    
    try:
        vs = _get_or_create_user_chroma(user_id)
        
        vs.add_documents(documents)
        
        logger.info(f"[RAG] Indexed {len(documents)} documents for {user_id}")
        
    except Exception as e:
        logger.error(f"[RAG] Indexing failed for {user_id}: {e}")
        raise

def search_documents(user_id: str, query: str, k: int = 4) -> List[Document]:
    """
    Perform similarity search on user's vector store
    """
    try:
        vs = _get_or_create_user_chroma(user_id)
        docs = vs.similarity_search(query, k=k)
        
        logger.info(f"[RAG] Found {len(docs)} results for user {user_id}")
        return docs
        
    except Exception as e:
        logger.error(f"[RAG] Search failed for {user_id}: {e}")
        return []

def delete_user_vectorstore(user_id: str):
    """
    Delete user's vector store and cached instance
    """
    global _user_vectorstores
    
    collection_name = _get_sanitized_collection_name(user_id)
    user_chroma_path = os.path.join(CHROMA_PATH, user_id)
    
    if user_id in _user_vectorstores:
        try:
            del _user_vectorstores[user_id]
        except:
            pass
    
    if os.path.exists(user_chroma_path):
        try:
            try:
                client = chromadb.PersistentClient(path=user_chroma_path)
                client.delete_collection(collection_name)
            except Exception as e:
                logger.debug(f"[RAG] Collection delete attempt: {e}")
            
            shutil.rmtree(user_chroma_path, ignore_errors=True)
            
            logger.info(f"[RAG] Deleted vector store for {user_id}")
            
        except Exception as e:
            logger.error(f"[RAG] Error deleting vector store for {user_id}: {e}")
    else:
        logger.info(f"[RAG] No vector store found for {user_id}")

def get_vectorstore_stats(user_id: str) -> dict:
    """
    Get statistics about user's vector store
    """
    try:
        vs = _get_or_create_user_chroma(user_id)
        
        collection = vs._collection
        count = collection.count()
        
        return {
            "user_id": user_id,
            "document_count": count,
            "collection_name": _get_sanitized_collection_name(user_id)
        }
        
    except Exception as e:
        logger.error(f"[RAG] Stats error for {user_id}: {e}")
        return {
            "user_id": user_id,
            "error": str(e)
        }