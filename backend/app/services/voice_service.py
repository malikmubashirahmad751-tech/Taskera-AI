import os
import uuid
import asyncio
from typing import Optional
from app.core.logger import logger
from app.core.config import get_settings

settings = get_settings()

TEMP_AUDIO_DIR = "/tmp/taskera_audio" if os.name != 'nt' else "temp_audio"
os.makedirs(TEMP_AUDIO_DIR, exist_ok=True)

class VoiceService:
    def __init__(self):
        self.model: Optional[any] = None
        self._model_loading = False
        self._model_lock = asyncio.Lock()
    
    async def _ensure_model_loaded(self):
        """Lazy load model on first use with concurrency lock"""
        if self.model is not None:
            return
        
        async with self._model_lock:
            if self.model is not None:
                return
            
            self._model_loading = True
            try:
                logger.info("Loading Voice Model (Faster-Whisper CPU)...")
                loop = asyncio.get_running_loop()
                self.model = await loop.run_in_executor(None, self._load_model_sync)
                logger.info("Voice Model Loaded Successfully")
            except Exception as e:
                logger.error(f"Failed to load Voice Model: {e}")
                self.model = None
                raise RuntimeError(f"Transcription model failed to load: {e}")
            finally:
                self._model_loading = False
    
    def _load_model_sync(self):
        """Synchronous initialization of the whisper model"""
        try:
            from faster_whisper import WhisperModel
            return WhisperModel("base", device="cpu", compute_type="int8")
        except ImportError:
            raise RuntimeError("faster-whisper not installed. Run: pip install faster-whisper")

    async def transcribe(self, file_path: str) -> str:
        """Transcribes audio file to text locally"""
        await self._ensure_model_loaded()
        
        try:
            loop = asyncio.get_running_loop()
            text = await loop.run_in_executor(None, self._transcribe_sync, file_path)
            return text.strip()
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise

    def _transcribe_sync(self, file_path: str) -> str:
        """Synchronous transcription execution"""
        segments, info = self.model.transcribe(file_path, beam_size=5)
        return " ".join([segment.text for segment in segments])

    async def text_to_speech(self, text: str) -> str:
        """Generates audio from text using Edge-TTS with gTTS fallback"""
        filename = f"tts_{uuid.uuid4().hex}.mp3"
        output_path = os.path.join(TEMP_AUDIO_DIR, filename)

        try:
            import edge_tts
            communicate = edge_tts.Communicate(text, "en-US-AndrewNeural")
            await communicate.save(output_path)
            return output_path
        except Exception as e:
            logger.warning(f"Edge-TTS failed (likely 403 Forbidden). Switching to fallback: {e}")
            return await self._generate_gtts_fallback(text, output_path)

    async def _generate_gtts_fallback(self, text: str, output_path: str) -> str:
        """Fallback generator using Google TTS running in an executor"""
        try:
            from gtts import gTTS
            loop = asyncio.get_running_loop()
            
            await loop.run_in_executor(
                None, 
                lambda: gTTS(text=text, lang='en').save(output_path)
            )
            return output_path
        except ImportError:
            logger.error("gTTS not installed.")
            raise RuntimeError("Fallback TTS missing. Run: poetry add gTTS")
        except Exception as e:
            logger.error(f"All TTS providers failed: {e}")
            raise RuntimeError("Voice generation failed completely.")

    def cleanup_file(self, file_path: str):
        """Safely removes temporary files"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            logger.warning(f"Failed to cleanup {file_path}: {e}")

voice_service = VoiceService()