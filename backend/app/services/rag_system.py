import os
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    Docx2txtLoader,
)
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.tools import StructuredTool
from app.core.logger import logger
import shutil


DATA_PATH = "data"  
UPLOAD_PATH = "user_files" 
CHROMA_PATH = "chroma_db"  

def _load_documents_from_directory(directory: str):
    """Load and split all supported document types from a directory."""
    if not os.path.exists(directory):
        return []

    documents = []
    for file_name in os.listdir(directory):
        file_path = os.path.join(directory, file_name)
        ext = os.path.splitext(file_name)[1].lower()

        try:
            loader = None
            if ext == ".pdf":
                loader = PyPDFLoader(file_path)
            elif ext == ".txt":
                loader = TextLoader(file_path)
            elif ext == ".docx":
                loader = Docx2txtLoader(file_path)
          
            elif ext == ".md":
                loader = TextLoader(file_path)
            else:
                logger.info(f"Skipping unsupported file type: {file_name}")
                continue

            docs = loader.load()
            documents.extend(docs)

        except Exception as e:
            logger.warning(f"Failed to load {file_name}: {e}")

    return documents


def create_rag_tool(api_key: str, user_id: str): 
    """
    Initializes a RAG system for a specific user and returns it as a LangChain tool.
    It combines general documents with the user's private, uploaded documents.
    """
    
    user_upload_path = os.path.join(UPLOAD_PATH, user_id)
    user_chroma_path = os.path.join(CHROMA_PATH, user_id)

    
    os.makedirs(DATA_PATH, exist_ok=True)
    os.makedirs(user_upload_path, exist_ok=True)

    embeddings = OpenAIEmbeddings(api_key=api_key, model="text-embedding-3-small")

   
    db = Chroma(persist_directory=user_chroma_path, embedding_function=embeddings)


    data_docs = _load_documents_from_directory(DATA_PATH)
    user_docs = _load_documents_from_directory(user_upload_path) 

    all_docs = data_docs + user_docs
    if all_docs:
        logger.info(f"Loaded {len(all_docs)} documents for user '{user_id}'. Splitting and indexing...")
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
        chunks = text_splitter.split_documents(all_docs)
        db.add_documents(chunks)
        logger.info(f"Documents for user '{user_id}' indexed successfully.")
    else:
        logger.info(f"No documents found to index for user '{user_id}'.")

    retriever = db.as_retriever(search_kwargs={"k": 3})

    def retrieve_info(query: str) -> str:
        """Retrieve relevant text from the user's indexed documents."""
        logger.info(f"Retrieving info for user '{user_id}' with query: {query}")
        results = retriever.get_relevant_documents(query)
        if not results:
            logger.info(f"No relevant results found for user '{user_id}'.")
            return "No relevant information was found in the indexed documents for this query."
        return "\n\n".join([doc.page_content for doc in results])

    return StructuredTool.from_function(
        name="local_document_retriever",
        func=retrieve_info,
        description="Retrieves information from both static and user-uploaded documents (PDF, TXT, DOCX, MD)."
    )

def delete_user_vectorstore(user_id: str):
    """
    Deletes the user's entire ChromaDB vector store directory.
    This prevents stale data after a file has been deleted.
    """
    user_chroma_path = os.path.join(CHROMA_PATH, user_id)
    
    if os.path.exists(user_chroma_path):
        try:
            shutil.rmtree(user_chroma_path)
            logger.info(f"Successfully deleted vector store for user: {user_chroma_path}")
        except Exception as e:
            logger.error(f"Error deleting vector store for user '{user_id}': {e}")
    else:
        logger.info(f"No vector store found for user '{user_id}'. Nothing to delete.")