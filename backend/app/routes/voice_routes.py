from fastapi import APIRouter, UploadFile, File, HTTPException, Body, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from app.services.voice_service import voice_service, TEMP_AUDIO_DIR
from app.core.logger import logger  
import shutil
import os
import uuid

router = APIRouter()

@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """Receives audio file -> Returns transcribed text"""
    file_ext = file.filename.split('.')[-1] if '.' in file.filename else "webm"
    temp_path = os.path.join(TEMP_AUDIO_DIR, f"up_{uuid.uuid4().hex}.{file_ext}")
    
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        text = await voice_service.transcribe(temp_path)
        
        return JSONResponse({"text": text})
        
    except Exception as e:
        logger.error(f"Transcription Endpoint Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        voice_service.cleanup_file(temp_path)

@router.post("/tts")
async def text_to_speech_endpoint(background_tasks: BackgroundTasks, item: dict = Body(...)):
    """Receives text -> Returns generated audio file"""
    text = item.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="No text provided")
        
    try:
        safe_text = text[:1000]
        
        output_path = await voice_service.text_to_speech(safe_text)
        
        background_tasks.add_task(voice_service.cleanup_file, output_path)
        
        return FileResponse(
            output_path, 
            media_type="audio/mpeg", 
            filename="response.mp3"
        )
    except Exception as e:
        logger.error(f"TTS Endpoint Error: {e}")
        raise HTTPException(
            status_code=503, 
            detail="Voice synthesis service is temporarily unavailable. Please try again later."
        )