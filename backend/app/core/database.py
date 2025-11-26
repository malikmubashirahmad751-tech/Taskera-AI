import os
from supabase import create_client, Client
from dotenv import load_dotenv
from app.core.logger import logger

load_dotenv()

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

supabase: Client | None = None

if not supabase_url or not supabase_key:
    logger.warning("Supabase URL and Key not set in .env file. Database features will be disabled.")
else:
    try:
        supabase: Client = create_client(supabase_url, supabase_key)
        logger.info("Supabase client created successfully")
    except Exception as e:
        logger.error(f"Error creating Supabase client: {e}")
        supabase = None