import os
import shutil
from app.core.logger import logger

UPLOAD_PATH = "user_files"

def delete_specific_user_file(user_id: str, filename: str) -> bool:
    """
    Deletes a specific file for a user and cleans up the directory if it becomes empty.
    Returns True on success, False on failure (e.g., file not found).
    """
    try:
        user_dir = os.path.join(UPLOAD_PATH, user_id)
        file_path = os.path.join(user_dir, filename)

        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Successfully deleted file: {file_path}")
            
          
            if os.path.exists(user_dir) and not os.listdir(user_dir):
                os.rmdir(user_dir)
                logger.info(f"Cleaned up empty user directory: {user_dir}")
            return True
        else:
            logger.warning(f"File for deletion was not found: {file_path}")
            return False
            
    except Exception as e:
        logger.error(f"Error during deletion of '{filename}' for user '{user_id}': {e}")
        return False

def delete_all_user_files(user_id: str):
    """
    Deletes the entire directory containing all of a user's uploaded files.
    """
    user_dir = os.path.join(UPLOAD_PATH, user_id)
    
    if os.path.exists(user_dir):
        try:
            shutil.rmtree(user_dir)
            logger.info(f"Successfully deleted all files and directory for user: {user_dir}")
        except Exception as e:
            logger.error(f"Error deleting directory '{user_dir}' for user '{user_id}': {e}")
    else:
        logger.info(f"No file directory found for user '{user_id}'. Nothing to delete.")