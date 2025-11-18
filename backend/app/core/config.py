import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    
    GOOGLE_CLIENT_ID: str = Field(default="")
    GOOGLE_CLIENT_SECRET: str = Field(default="")
    GOOGLE_REDIRECT_URI: str = Field(default="http://localhost:8000/auth/google/callback")
    
    SUPABASE_URL: str = Field(default="")
    SUPABASE_KEY: str = Field(default="")

    gemini_api_key: str = Field(default="", alias="GOOGLE_API_KEY")
    
    openweathermap_api_key: str = Field(default="", alias="OPENWEATHERMAP_API_KEY")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  
        case_sensitive=False
    )

settings = Settings()