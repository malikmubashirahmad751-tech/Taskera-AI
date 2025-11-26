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

from app.core.config import settings
from app.core.logger import logger
from app.services.rag_service import (
    _get_or_create_user_chroma,
    DATA_PATH,
    UPLOAD_PATH
)

def _load_pdf_smart(file_path: str) -> List[Document]:
    """
    Handles PDFs. Detects if they are 'scanned' (images only) and switches to OCR.
    """
    try:
        logger.info(f"[RAG-Load] Attempting fast load for PDF: {os.path.basename(file_path)}")
        loader = PyPDFLoader(file_path)
        docs = loader.load()

        full_text = " ".join([d.page_content for d in docs[:3]]).strip()
        
        
        
        is_suspicious = len(full_text) < 200 or ("CamScanner" in full_text and len(full_text) < 1000)

        if not is_suspicious:
            logger.info(f"[RAG-Load] Valid text detected ({len(full_text)} chars). Skipping OCR.")
            return docs
        
        logger.warning(f"[RAG-Load] Low quality text detected (Chars: {len(full_text)}). Switching to OCR...")
        
        try:
            ocr_loader = UnstructuredPDFLoader(
                file_path,
                strategy="ocr_only",  
                languages=["eng"],
                mode="elements"
            )
            return ocr_loader.load()
        except Exception as ocr_error:
            logger.error(f"[RAG-Load] OCR failed. Returning original text. Error: {ocr_error}")
            return docs

    except Exception as e:
        logger.error(f"[RAG-Load] Failed to load PDF {os.path.basename(file_path)}: {e}")
        return []


def _smart_load_single_file(file_path: str) -> List[Document]:
    """
    Dispatches the file to the correct loader based on extension.
    """
    ext = file_path.lower()
    if not os.path.exists(file_path):
        return []

    try:
        if ext.endswith(".pdf"):
            return _load_pdf_smart(file_path)
            
        elif ext.endswith(".docx") or ext.endswith(".doc"):
            logger.info(f"[RAG-Load] Loading Word Doc: {os.path.basename(file_path)}")
            try:
                return Docx2txtLoader(file_path).load()
            except:
                return UnstructuredWordDocumentLoader(file_path).load()
                
        elif ext.endswith(".txt") or ext.endswith(".md"):
            logger.info(f"[RAG-Load] Loading Text file: {os.path.basename(file_path)}")
            return TextLoader(file_path, encoding="utf-8", autodetect_encoding=True).load()
            
        else:
            logger.warning(f"[RAG-Load] Unsupported file extension: {file_path}")
            return []
            
    except Exception as e:
        logger.error(f"[RAG-Load] General error loading {file_path}: {e}")
        return []

def _smart_load_directory(directory_path: str) -> List[Document]:
    """Iterates through a directory and applies smart loading."""
    documents = []
    if not os.path.exists(directory_path):
        return documents

    files = glob.glob(os.path.join(directory_path, "*.*"))
    
    for file_path in files:
        if file_path.lower().endswith((".pdf", ".doc", ".docx", ".txt", ".md")):
            docs = _smart_load_single_file(file_path)
            documents.extend(docs)
        
    return documents

def create_rag_tool_impl(user_id: str) -> str:
    """
    Creates/updates the RAG retriever for the user.
    """
    logger.info(f"[MCP-RAG] Indexing RAG for user '{user_id}'.")
    user_upload_path = os.path.join(UPLOAD_PATH, user_id)
    
    os.makedirs(DATA_PATH, exist_ok=True)
    os.makedirs(user_upload_path, exist_ok=True)

    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/text-embedding-004", 
        task_type="retrieval_document",
        google_api_key=settings.gemini_api_key
    )

    db = _get_or_create_user_chroma(user_id, embeddings)
    
    system_docs = _smart_load_directory(DATA_PATH)
    user_docs = _smart_load_directory(user_upload_path)
    all_docs = system_docs + user_docs

    if all_docs:
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
        chunks = text_splitter.split_documents(all_docs)
        
        db.add_documents(chunks) 
        
        logger.info(f"[MCP-RAG] Indexed {len(chunks)} chunks for user '{user_id}'.")
        return f"Successfully indexed {len(chunks)} chunks from {len(all_docs)} documents."
    else:
        logger.info(f"[MCP-RAG] No documents found to index for user '{user_id}'.")
        return "No documents found to index."

def retrieve_info_impl(query: str, user_id: str) -> str:
    """
    Retrieve text relevant to the user query.
    """
    logger.info(f"[MCP-RAG] Retrieving info for user '{user_id}' with query: '{query}'")
    
    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/text-embedding-004", 
        task_type="retrieval_document",
        google_api_key=settings.gemini_api_key
    )
    
    db = _get_or_create_user_chroma(user_id, embeddings)
    retriever = db.as_retriever(search_kwargs={"k": 3})

    try:
        if hasattr(retriever, "invoke"):
            results = retriever.invoke(query)
        else:
            results = retriever.get_relevant_documents(query)
            
    except Exception as e:
        logger.error(f"[MCP-RAG] Error retrieving info for '{user_id}': {e}", exc_info=True)
        return f"Error performing search: {str(e)}"

    if not results:
        return "No relevant information found in your uploaded or system documents."

    return "\n\n".join([doc.page_content for doc in results])