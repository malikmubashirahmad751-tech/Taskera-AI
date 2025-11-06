# app/services/ocr_service.py
import pytesseract
from PIL import Image
from langchain_core.tools import tool
import os
import logging

logger = logging.getLogger(__name__)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
UPLOAD_DIRECTORY = os.path.join(BASE_DIR, "user_files")

os.makedirs(UPLOAD_DIRECTORY, exist_ok=True)

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

@tool
def image_text_extractor(user_id: str, file_name: str) -> str:
    """
    Extracts text from an image file located in a user-specific directory.
    
    The 'user_id' is the user's folder (e.g., 'string' from the logs).
    The 'file_name' argument must be the simple, secure filename
    (e.g., 'Screenshot 2025-10-27 030603.png') provided by the upload API.
    
    This tool is used *after* an image is uploaded and the user
    specifically asks to read the text.
    """
    logger.info(f"Attempting to extract text for user '{user_id}' from file '{file_name}'")
    try:
        user_specific_dir = os.path.join(UPLOAD_DIRECTORY, user_id)
        
        full_path = os.path.join(user_specific_dir, os.path.basename(file_name))
        logger.debug(f"Resolved full path: {full_path}")

        if not os.path.abspath(full_path).startswith(os.path.abspath(UPLOAD_DIRECTORY)):
            logger.warning(f"Security Warning: Attempted file access outside permitted directory. User: '{user_id}', Path: '{full_path}'")
            return "Error: File access forbidden."

        if not os.path.exists(full_path):
            logger.warning(f"File not found for user '{user_id}' at path: '{full_path}'")
            return f"Error: File not found at '{full_path}'. The tool might be looking in the wrong user folder or the file doesn't exist."

        logger.debug(f"Opening image file: {full_path}")
        img = Image.open(full_path)
        extracted_text = pytesseract.image_to_string(img)
        
        if not extracted_text.strip():
            logger.info(f"No readable text found in image '{file_name}' for user '{user_id}'.")
            return f"No readable text was found in the image '{file_name}'."
        
        logger.info(f"Successfully extracted text from '{file_name}' for user '{user_id}'.")
        return f"Extracted text from '{file_name}':\n\n{extracted_text.strip()}"

    except pytesseract.TesseractNotFoundError as e:
        logger.error(f"Tesseract OCR engine not found. Ensure it's installed and in PATH. Error: {e}", exc_info=True)
        return "Error: Tesseract OCR engine not found on the server. Please contact the administrator."
    except Exception as e:
        logger.error(f"Unexpected error processing image '{file_name}' for user '{user_id}'. Error: {e}", exc_info=True)
        return f"An unexpected error occurred while processing image: {str(e)}"