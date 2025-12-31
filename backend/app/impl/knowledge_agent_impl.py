import os
import glob
from typing import List

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_text_splitters.character import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from langchain_community.document_loaders import (
    PyPDFLoader,
    UnstructuredPDFLoader,
    TextLoader,
    Docx2txtLoader,
    UnstructuredWordDocumentLoader
)

from app.core.config import get_settings
from app.core.logger import logger
from app.core.context import get_current_user_id 
from app.services.rag_service import (
    _get_or_create_user_chroma,
    DATA_PATH,
    UPLOAD_PATH
)

settings = get_settings()

def _load_pdf_smart(file_path: str) -> List[Document]:
    """Smart PDF loading with OCR fallback for scanned documents"""
    try:
        logger.info(f"[RAG] Loading PDF: {os.path.basename(file_path)}")
        loader = PyPDFLoader(file_path)
        docs = loader.load()
        
        full_text = " ".join([d.page_content for d in docs[:3]]).strip()
        has_text = len(full_text) > 100
        
        if not has_text or (("CamScanner" in full_text or "Scanned" in full_text) and len(full_text) < 500):
            logger.warning(f"[RAG] Scanned PDF detected, switching to OCR...")
            try:
                ocr_loader = UnstructuredPDFLoader(
                    file_path,
                    strategy="ocr_only",
                    mode="elements"
                )
                return ocr_loader.load()
            except Exception as ocr_error:
                logger.error(f"[RAG] OCR failed: {ocr_error}")
                return docs
        return docs
    except Exception as e:
        logger.error(f"[RAG] PDF load error for {file_path}: {e}")
        return []

def _smart_load_single_file(file_path: str) -> List[Document]:
    """Load a single file based on extension"""
    ext = file_path.lower()
    if not os.path.exists(file_path):
        return []
    
    try:
        if ext.endswith(".pdf"):
            return _load_pdf_smart(file_path)
        elif ext.endswith((".docx", ".doc")):
            try:
                return Docx2txtLoader(file_path).load()
            except:
                return UnstructuredWordDocumentLoader(file_path).load()
        elif ext.endswith((".txt", ".md")):
            return TextLoader(file_path, encoding="utf-8", autodetect_encoding=True).load()
        return []
    except Exception as e:
        logger.error(f"[RAG] Error loading {file_path}: {e}")
        return []

def _smart_load_directory(directory_path: str) -> List[Document]:
    """Load all supported files from a directory"""
    documents = []
    if not os.path.exists(directory_path):
        return documents
    
    supported_exts = [".pdf", ".doc", ".docx", ".txt", ".md"]
    files = glob.glob(os.path.join(directory_path, "*.*"))
    
    for file_path in files:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in supported_exts:
            docs = _smart_load_single_file(file_path)
            documents.extend(docs)
            logger.info(f"[RAG] Loaded {len(docs)} chunks from {os.path.basename(file_path)}")
    return documents

def create_rag_tool_impl(user_id: str = None) -> str:
    """Create/update RAG index for a user"""
    if not user_id:
        user_id = get_current_user_id()
        
    if not user_id:
        return "Error: No user ID provided for indexing."

    logger.info(f"[RAG] Indexing documents for user: {user_id}")
    
    user_upload_path = os.path.join(UPLOAD_PATH, user_id)
    os.makedirs(DATA_PATH, exist_ok=True)
    os.makedirs(user_upload_path, exist_ok=True)
    
    try:
        db = _get_or_create_user_chroma(user_id)
    except Exception as e:
        return f"Failed to initialize vector database: {str(e)}"
    
    system_docs = _smart_load_directory(DATA_PATH)
    user_docs = _smart_load_directory(user_upload_path)
    all_docs = system_docs + user_docs
    
    if not all_docs:
        return "No documents found to index"
    
    try:
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1500, chunk_overlap=200, length_function=len, separators=["\n\n", "\n", ". ", " ", ""]
        )
        chunks = text_splitter.split_documents(all_docs)
        
        if not chunks:
            return "No content extracted from documents"
        
        batch_size = 100
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            db.add_documents(batch)
        
        return f"Successfully indexed **{len(chunks)} text chunks** from **{len(all_docs)} documents**."
        
    except Exception as e:
        logger.error(f"[RAG] Indexing error: {e}", exc_info=True)
        return f"Failed to index documents: {str(e)}"

def retrieve_info_impl(query: str) -> str:
    """
    Retrieve relevant information from user's documents.
    User ID is fetched from CONTEXT, not passed as an argument.
    """
    user_id = get_current_user_id() 
    if not user_id:
        return "Error: User context missing. Cannot retrieve documents."

    logger.info(f"[RAG] Retrieving for user={user_id}, query='{query}'")
    
    try:
        embeddings = GoogleGenerativeAIEmbeddings(
            model="models/text-embedding-004",
            task_type="retrieval_query",
            google_api_key=settings.GOOGLE_API_KEY
        )
        
        db = _get_or_create_user_chroma(user_id)
        
        retriever = db.as_retriever(
            search_type="similarity",
            search_kwargs={"k": 4}
        )
        
        results = retriever.invoke(query)
        
        if not results:
            return "No relevant information found in your documents."
        
        formatted_results = []
        for i, doc in enumerate(results, 1):
            source = doc.metadata.get('source', 'Unknown')
            filename = os.path.basename(source) if source else 'Unknown'
            formatted_results.append(f"**Source {i}: {filename}**\n{doc.page_content}\n")
        
        return "\n---\n\n".join(formatted_results)
        
    except Exception as e:
        logger.error(f"[RAG] Retrieval error: {e}", exc_info=True)
        return f"Error retrieving information: {str(e)}"