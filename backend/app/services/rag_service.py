import os
import re
import shutil
from typing import List, Optional, Dict

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

def _get_sanitized_collection_name(user_id: str) -> str:
    """Sanitize user_id for ChromaDB collection name"""
    clean = re.sub(r"[^a-zA-Z0-9._-]", "_", user_id)
    
    if not clean:
        clean = "default_user"
    
    if not clean[0].isalnum():
        clean = "u" + clean
    
    if not clean[-1].isalnum():
        clean = clean + "0"
    
    collection_name = f"user_{clean}"
    
    return collection_name[:63]

# FIXED: Use strong references with explicit cleanup instead of WeakValueDictionary
# WeakValueDictionary can cause unexpected GC during active operations
_chroma_cache: Dict[str, Chroma] = {}

def _get_or_create_user_chroma(user_id: str) -> Chroma:
    """
    Get or create Chroma instance for user.
    Uses explicit cache management for predictable behavior.
    """
    if user_id in _chroma_cache:
        return _chroma_cache[user_id]
    
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
        
        _chroma_cache[user_id] = vectordb
        
        logger.info(f"[RAG] Initialized vector store for user: {user_id}")
        return vectordb
        
    except Exception as e:
        logger.error(f"[RAG] Failed to initialize Chroma for {user_id}: {e}")
        raise

async def index_documents(user_id: str, documents: List[Document]):
    """Add documents to user's vector store"""
    if not documents:
        logger.warning(f"[RAG] No documents to index for {user_id}")
        return
    
    try:
        vs = _get_or_create_user_chroma(user_id)
        
        batch_size = 100
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            await vs.aadd_documents(batch)
        
        logger.info(f"[RAG] Indexed {len(documents)} documents for {user_id}")
        
    except Exception as e:
        logger.error(f"[RAG] Indexing failed for {user_id}: {e}")
        raise

async def search_documents(user_id: str, query: str, k: int = 4) -> List[Document]:
    """Perform similarity search on user's vector store"""
    try:
        vs = _get_or_create_user_chroma(user_id)
        
        if hasattr(vs.embedding_function, 'task_type'):
            vs.embedding_function.task_type = "retrieval_query"
            
        docs = await vs.asimilarity_search(query, k=k)
        
        logger.info(f"[RAG] Found {len(docs)} results for user {user_id}")
        return docs
        
    except Exception as e:
        logger.error(f"[RAG] Search failed for {user_id}: {e}")
        return []

def delete_user_vectorstore(user_id: str):
    """Delete user's vector store and cached instance"""
    # FIXED: Proper cleanup of cache entry
    if user_id in _chroma_cache:
        try:
            # Close connection if method exists
            vs = _chroma_cache[user_id]
            if hasattr(vs, '_client') and vs._client:
                vs._client = None
        except Exception as e:
            logger.warning(f"[RAG] Error closing connection for {user_id}: {e}")
        finally:
            del _chroma_cache[user_id]
    
    user_chroma_path = os.path.join(CHROMA_PATH, user_id)
    
    if os.path.exists(user_chroma_path):
        try:
            shutil.rmtree(user_chroma_path, ignore_errors=True)
            logger.info(f"[RAG] Deleted vector store for {user_id}")
            
        except Exception as e:
            logger.error(f"[RAG] Error deleting vector store for {user_id}: {e}")
    else:
        logger.info(f"[RAG] No vector store found for {user_id}")

def get_vectorstore_stats(user_id: str) -> dict:
    """Get statistics about user's vector store"""
    try:
        vs = _get_or_create_user_chroma(user_id)
        
        collection = vs._collection
        count = collection.count()
        
        return {
            "user_id": user_id,
            "document_count": count,
            "collection_name": _get_sanitized_collection_name(user_id),
            "status": "active"
        }
        
    except Exception as e:
        logger.error(f"[RAG] Stats error for {user_id}: {e}")
        return {
            "user_id": user_id,
            "error": str(e),
            "status": "error"
        }

def clear_cache():
    """Clear the entire cache (useful for testing or maintenance)"""
    global _chroma_cache
    for user_id in list(_chroma_cache.keys()):
        try:
            vs = _chroma_cache[user_id]
            if hasattr(vs, '_client') and vs._client:
                vs._client = None
        except Exception:
            pass
    _chroma_cache.clear()
    logger.info("[RAG] Cache cleared")