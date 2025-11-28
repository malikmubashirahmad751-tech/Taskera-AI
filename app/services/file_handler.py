import os
import shutil
from pathlib import Path

from app.core.config import get_settings
from app.core.logger import logger

settings = get_settings()

UPLOAD_PATH = settings.UPLOAD_PATH

def delete_specific_user_file(user_id: str, filename: str) -> bool:
    """
    Delete a specific file for a user
    """
    try:
        user_dir = os.path.join(UPLOAD_PATH, user_id)
        file_path = os.path.join(user_dir, filename)
        
        user_dir_abs = os.path.abspath(user_dir)
        file_path_abs = os.path.abspath(file_path)
        upload_path_abs = os.path.abspath(UPLOAD_PATH)
        
        if not file_path_abs.startswith(upload_path_abs):
            logger.warning(f"[Files] Path traversal attempt: {file_path}")
            return False
        
        if not os.path.exists(file_path_abs):
            logger.warning(f"[Files] File not found: {file_path}")
            return False
        
        os.remove(file_path_abs)
        logger.info(f"[Files] Deleted: {file_path}")
        
        if os.path.exists(user_dir_abs) and not os.listdir(user_dir_abs):
            os.rmdir(user_dir_abs)
            logger.info(f"[Files] Removed empty directory: {user_dir}")
        
        return True
        
    except Exception as e:
        logger.error(f"[Files] Delete error for {filename}: {e}")
        return False

def delete_all_user_files(user_id: str):
    """
    Delete all files for a user
    """
    user_dir = os.path.join(UPLOAD_PATH, user_id)
    user_dir_abs = os.path.abspath(user_dir)
    
    if not os.path.exists(user_dir_abs):
        logger.info(f"[Files] No files found for user: {user_id}")
        return
    
    try:
        upload_path_abs = os.path.abspath(UPLOAD_PATH)
        if not user_dir_abs.startswith(upload_path_abs):
            logger.error(f"[Files] Invalid path: {user_dir}")
            return
        
        shutil.rmtree(user_dir_abs, ignore_errors=True)
        logger.info(f"[Files] Deleted all files for user: {user_id}")
        
    except Exception as e:
        logger.error(f"[Files] Error deleting files for {user_id}: {e}")

def get_user_files(user_id: str) -> list:
    """
    List all files for a user
    """
    user_dir = os.path.join(UPLOAD_PATH, user_id)
    
    if not os.path.exists(user_dir):
        return []
    
    try:
        files = []
        for filename in os.listdir(user_dir):
            file_path = os.path.join(user_dir, filename)
            
            if os.path.isfile(file_path):
                size_mb = os.path.getsize(file_path) / (1024 * 1024)
                files.append({
                    "filename": filename,
                    "size_mb": round(size_mb, 2),
                    "path": file_path
                })
        
        return files
        
    except Exception as e:
        logger.error(f"[Files] Error listing files for {user_id}: {e}")
        return []

def get_storage_stats(user_id: str) -> dict:
    """
    Get storage statistics for a user
    """
    try:
        files = get_user_files(user_id)
        total_size_mb = sum(f["size_mb"] for f in files)
        
        return {
            "user_id": user_id,
            "file_count": len(files),
            "total_size_mb": round(total_size_mb, 2),
            "files": files
        }
        
    except Exception as e:
        logger.error(f"[Files] Stats error for {user_id}: {e}")
        return {
            "user_id": user_id,
            "error": str(e)
        }