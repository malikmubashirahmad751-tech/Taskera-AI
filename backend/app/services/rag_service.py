import os
import shutil
import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_community.vectorstores import Chroma
from langchain_community.document_loaders import PyPDFLoader, TextLoader, Docx2txtLoader
from app.core.logger import logger

DATA_PATH = "data"
UPLOAD_PATH = "user_files"
CHROMA_PATH = "chroma_db"

_user_vectorstores = {}

def _load_documents_from_directory(directory: str):
    """Load all supported document types from a directory."""
    if not os.path.exists(directory):
        return []

    documents = []
    for file_name in os.listdir(directory):
        file_path = os.path.join(directory, file_name)

        if os.path.isdir(file_path):
            continue

        ext = os.path.splitext(file_name)[1].lower()
        try:
            if ext == ".pdf":
                loader = PyPDFLoader(file_path)
            elif ext in [".txt", ".md"]:
                loader = TextLoader(file_path)
            elif ext == ".docx":
                loader = Docx2txtLoader(file_path)
            else:
                logger.info(f"Skipping unsupported file type: {file_name}")
                continue

            documents.extend(loader.load())
        except Exception as e:
            logger.warning(f"Failed to load {file_name}: {e}")

    return documents


def _get_or_create_user_chroma(user_id: str, embeddings):
    """Get or create a cached Chroma instance for the user."""
    global _user_vectorstores

    if user_id in _user_vectorstores:
        return _user_vectorstores[user_id]

    user_chroma_path = os.path.join(CHROMA_PATH, user_id)
    os.makedirs(user_chroma_path, exist_ok=True)

    vectordb = Chroma(
        persist_directory=user_chroma_path,
        embedding_function=embeddings,
    )
    _user_vectorstores[user_id] = vectordb
    return vectordb


def delete_user_vectorstore(user_id: str):
    """Safely delete/reset the user's vectorstore and cache."""
    global _user_vectorstores
    user_chroma_path = os.path.join(CHROMA_PATH, user_id)

    if user_id in _user_vectorstores:
        del _user_vectorstores[user_id]

    if os.path.exists(user_chroma_path):
        try:
            client = chromadb.PersistentClient(
                path=user_chroma_path, settings=ChromaSettings(allow_reset=True)
            )
            client.reset()
            shutil.rmtree(user_chroma_path)
            logger.info(f"Successfully reset and deleted vector store for '{user_id}'.")
        except Exception as e:
            logger.error(f"Error deleting vector store for '{user_id}': {e}")
    else:
        logger.info(f"No vector store found for '{user_id}'.")