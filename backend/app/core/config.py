import os
from typing import Optional
from pydantic import Field, validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Production-ready configuration with validation"""
    
    GOOGLE_CLIENT_ID: str = Field(..., min_length=1)
    GOOGLE_CLIENT_SECRET: str = Field(..., min_length=1)
    
    # UPDATED: Defaulting to your Production URL. 
    # Your local .env should override this to "http://localhost:7860/auth/google/callback" for testing.
    GOOGLE_REDIRECT_URI: str = Field(
        default="https://mubashir751-taskera-ai-backend.hf.space/auth/google/callback"
    )
    
    SUPABASE_URL: str = Field(..., min_length=1)
    SUPABASE_KEY: str = Field(..., min_length=1)
    
    GOOGLE_API_KEY: str = Field(..., min_length=1, alias="GOOGLE_API_KEY")
    OPENWEATHERMAP_API_KEY: Optional[str] = Field(default=None)
    
    CSRF_SESSION_SECRET: str = Field(..., min_length=32)
    CSRF_TOKEN_SECRET: str = Field(..., min_length=32)
    JWT_SECRET_KEY: str = Field(..., min_length=32)
    
    SERVER_HOST: str = Field(default="0.0.0.0")
    SERVER_PORT: int = Field(default=7860)
    DEBUG: bool = Field(default=False)
    
    
    FRONTEND_URL: str = Field(default="https://taskera-ai.vercel.app")
    MCP_SERVER_URL: str = Field(default="https://mubashir751-taskera-ai-backend.hf.space/mcp")
    
    CORS_ORIGINS: list[str] = Field(
        default=[
            "http://localhost:5500", 
            "http://127.0.0.1:5500", 
            "https://taskera-ai.vercel.app"
        ]
    )
    
    RATE_LIMIT_PER_MINUTE: int = Field(default=60)
    GUEST_REQUEST_LIMIT: int = Field(default=10)
    
    MAX_UPLOAD_SIZE_MB: int = Field(default=10)
    MAX_FILES_PER_USER: int = Field(default=50)
    ALLOWED_EXTENSIONS: list[str] = Field(
        default=[".pdf", ".docx", ".doc", ".txt", ".md", ".png", ".jpg", ".jpeg"]
    )
    
    UPLOAD_PATH: str = Field(default="user_files")
    DATA_PATH: str = Field(default="data")
    CHROMA_PATH: str = Field(default="chroma_db")
    LOG_PATH: str = Field(default="logs")
    
    @validator("GOOGLE_API_KEY", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET")
    def validate_required_keys(cls, v):
        if not v or v.strip() == "":
            raise ValueError("Required API key cannot be empty")
        return v
    
    @validator("CSRF_SESSION_SECRET", "CSRF_TOKEN_SECRET", "JWT_SECRET_KEY")
    def validate_secret_length(cls, v):
        if len(v) < 32:
            raise ValueError("Secret must be at least 32 characters long")
        return v
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True
    )

_settings: Optional[Settings] = None

def get_settings() -> Settings:
    """Get or create settings singleton"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

settings = get_settings()