import os
from pathlib import Path

try:
    import pytesseract
    from PIL import Image
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

from app.core.config import get_settings
from app.core.logger import logger

settings = get_settings()

if TESSERACT_AVAILABLE:
    try:
        if os.name == 'nt':
            tesseract_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
            if os.path.exists(tesseract_path):
                pytesseract.pytesseract.tesseract_cmd = tesseract_path
        
        pytesseract.get_tesseract_version()
        logger.info("Tesseract OCR available")
        
    except Exception as e:
        logger.warning(f"Tesseract verification failed: {e}")
        TESSERACT_AVAILABLE = False

UPLOAD_DIRECTORY = settings.UPLOAD_PATH

def image_text_extractor_impl(user_id: str, file_name: str) -> str:
    """
    Extract text from an image file using OCR
    """
    if not TESSERACT_AVAILABLE:
        return (
            "OCR service unavailable. "
            "Please install Tesseract OCR (https://github.com/tesseract-ocr/tesseract)"
        )
    
    logger.info(f"[OCR] Extracting text from '{file_name}' for user '{user_id}'")
    
    try:
        user_dir = os.path.join(UPLOAD_DIRECTORY, user_id)
        file_path = os.path.join(user_dir, file_name)
        
        file_path_abs = os.path.abspath(file_path)
        upload_dir_abs = os.path.abspath(UPLOAD_DIRECTORY)
        
        if not file_path_abs.startswith(upload_dir_abs):
            logger.warning(f"[OCR] Path traversal attempt: {file_path}")
            return "Error: Invalid file path"
        
        if not os.path.exists(file_path_abs):
            logger.warning(f"[OCR] File not found: {file_path}")
            return f"File not found: {file_name}"
        
        valid_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff']
        file_ext = Path(file_name).suffix.lower()
        
        if file_ext not in valid_extensions:
            return f"Invalid image format. Supported: {', '.join(valid_extensions)}"
        
        img = Image.open(file_path_abs)
        
        extracted_text = pytesseract.image_to_string(img, lang='eng')
        
        if not extracted_text.strip():
            logger.info(f"[OCR] No text found in '{file_name}'")
            return f"No readable text found in the image '{file_name}'"
        
        logger.info(f"[OCR] Successfully extracted text from '{file_name}' ({len(extracted_text)} chars)")
        
        return f"**Extracted text from '{file_name}':**\n\n{extracted_text.strip()}"
        
    except pytesseract.TesseractNotFoundError:
        logger.error("[OCR] Tesseract not found")
        return "OCR engine not found. Please install Tesseract OCR."
        
    except Exception as e:
        logger.error(f"[OCR] Error processing '{file_name}': {e}", exc_info=True)
        return f"Error processing image: {str(e)}"