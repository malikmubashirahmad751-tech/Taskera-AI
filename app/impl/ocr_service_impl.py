import pytesseract
from PIL import Image
import os
import logging

logger = logging.getLogger(__name__)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
UPLOAD_DIRECTORY = os.path.join(BASE_DIR, "user_files")
os.makedirs(UPLOAD_DIRECTORY, exist_ok=True)

try:
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    pytesseract.get_tesseract_version()
    logger.info("Tesseract OCR engine found at default Windows path.")
except Exception:
    logger.info("Tesseract not found at 'C:\\Program Files\\Tesseract-OCR\\tesseract.exe'. Assuming it's in system PATH.")



def image_text_extractor_impl(user_id: str, file_name: str) -> str:
    """
    (IMPL) Extracts text from an image file.
    This is called by the MCP server.
    """
    logger.info(f"[MCP-OCR] Attempting to extract text for user '{user_id}' from file '{file_name}'")
    try:
        user_specific_dir = os.path.join(UPLOAD_DIRECTORY, user_id)
        full_path = os.path.join(user_specific_dir, os.path.basename(file_name))
        
        if not os.path.abspath(full_path).startswith(os.path.abspath(UPLOAD_DIRECTORY)):
            logger.warning(f"Security Warning: Attempted file access outside permitted directory. User: '{user_id}', Path: '{full_path}'")
            return "Error: File access forbidden."

        if not os.path.exists(full_path):
            logger.warning(f"File not found for user '{user_id}' at path: '{full_path}'")
            return f"Error: File not found at '{full_path}'."

        img = Image.open(full_path)
        extracted_text = pytesseract.image_to_string(img)
        
        if not extracted_text.strip():
            logger.info(f"No readable text found in image '{file_name}' for user '{user_id}'.")
            return f"No readable text was found in the image '{file_name}'."
        
        logger.info(f"Successfully extracted text from '{file_name}' for user '{user_id}'.")
        return f"Extracted text from '{file_name}':\n\n{extracted_text.strip()}"

    except pytesseract.TesseractNotFoundError:
        logger.error("Tesseract OCR engine not found. Ensure it's installed and in your system PATH.", exc_info=True)
        return "Error: Tesseract OCR engine not found on the server."
    except Exception as e:
        logger.error(f"Unexpected error processing image '{file_name}' for user '{user_id}'. Error: {e}", exc_info=True)
        return f"An unexpected error occurred: {str(e)}"