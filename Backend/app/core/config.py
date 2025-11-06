import os
from dotenv import load_dotenv

class Settings:
    """Holds all application settings."""
    def __init__(self):
        load_dotenv()
        self.openai_api_key = self._get_api_key()

    def _get_api_key(self) -> str:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is missing from your .env file")
        os.environ["HTTP_PROXY"] = ""
        os.environ["HTTPS_PROXY"] = ""
        return api_key
    
settings = Settings()