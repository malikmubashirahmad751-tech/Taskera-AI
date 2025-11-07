import os
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_text_splitters.character import RecursiveCharacterTextSplitter
from langchain_core.tools import StructuredTool
from app.core.logger import logger
from app.services.rag_service import (
    _get_or_create_user_chroma,
    _load_documents_from_directory,
    DATA_PATH,
    UPLOAD_PATH
)

def create_rag_tool(api_key: str, user_id: str):
    """Creates a RAG retriever tool for the user."""
    user_upload_path = os.path.join(UPLOAD_PATH, user_id)
    os.makedirs(DATA_PATH, exist_ok=True)
    os.makedirs(user_upload_path, exist_ok=True)

    embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")

    db = _get_or_create_user_chroma(user_id, embeddings)

   
    if not db.get().get("ids"):  
        all_docs = _load_documents_from_directory(DATA_PATH) + _load_documents_from_directory(user_upload_path)
        if all_docs:
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
            chunks = text_splitter.split_documents(all_docs)
            db.add_documents(chunks)
            logger.info(f"Indexed {len(chunks)} chunks for user '{user_id}'.")
        else:
            logger.info(f"No documents found to index for user '{user_id}'.")
    else:
        logger.info(f"Reusing cached vector store for user '{user_id}'.")

    retriever = db.as_retriever(search_kwargs={"k": 3})

    def retrieve_info(query: str) -> str:
        """Retrieve text relevant to the user query."""
        try:
            results = retriever.invoke(query)
        except AttributeError: 
            results = retriever.get_relevant_documents(query)
        except Exception as e:
            logger.error(f"Error retrieving info for '{user_id}': {e}")
            return f"Error: {e}"

        if not results:
            return "No relevant information found in your uploaded or system documents."

        return "\n\n".join([doc.page_content for doc in results])

    return StructuredTool.from_function(
        name="local_document_retriever",
        func=retrieve_info,
        description="Retrieves information from user-uploaded documents (PDF, TXT, DOCX) and system files."
    )