import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate

# Internal project imports
# Ensure these modules exist in your app.core structure
from app.core.database import supabase
from app.core.logger import logger
from app.core.config import get_settings

settings = get_settings()

class HistoryService:
    """
    Service class to handle all conversation history operations including:
    - Thread creation/updates
    - Title generation via LLM
    - Renaming threads
    - Fetching and deleting history
    """

    @staticmethod
    async def _generate_title(query: str, answer: str) -> str:
        """
        Generate a concise, relevant title for the chat thread using an LLM.
        Falls back to the query text if the API key is missing or generation fails.
        """
        if not settings.GOOGLE_API_KEY:
            # Fallback if no API key is configured
            return (query[:30] + "...") if len(query) > 30 else (query or "New Chat")

        try:
            # Using a fast, lightweight model for title generation
            llm = ChatGoogleGenerativeAI(
                model="gemini-2.0-flash",  # Robust production default
                api_key=settings.GOOGLE_API_KEY,
                temperature=0.1,
                max_retries=1,
                request_timeout=5.0
            )
            
            prompt = ChatPromptTemplate.from_template(
                "Generate a short, specific title (3 to 6 words) for this conversation based on the user's request.\n"
                "Do NOT use quotes. Do NOT start with 'Title:'.\n\n"
                "User Request: {query}\n"
                "Title:"
            )
            
            # Truncate query to avoid excessive token usage for title generation
            safe_query = (query or "")[:500]
            
            chain = prompt | llm
            result = await chain.ainvoke({"query": safe_query})
            
            title = result.content.strip()
            # Cleanup common LLM artifacts
            title = title.replace('"', '').replace("Title:", "").replace("**", "").strip()
            
            if not title:
                return "New Conversation"
                
            return title
            
        except Exception as e:
            logger.warning(f"Title generation failed: {e}. Falling back to default.")
            if query:
                return " ".join(query.split()[:5]) + "..."
            return "New Chat"

    @staticmethod
    async def create_or_update_thread(
        user_id: str,
        thread_id: str,
        query: Optional[str] = None,
        answer: Optional[str] = None
    ) -> None:
        """
        Creates a new thread record or updates the 'updated_at' timestamp of an existing one.
        Generates a title only on creation.
        """
        if not supabase:
            logger.warning("Supabase client not initialized; skipping thread persistence.")
            return

        try:
            now = datetime.now(timezone.utc).isoformat()
            
            # Check if thread exists
            response = await asyncio.to_thread(
                lambda: supabase.table("conversations")
                .select("thread_id")
                .eq("thread_id", thread_id)
                .execute()
            )
            
            exists = bool(response.data)
            
            if exists:
                # Update timestamp only
                await asyncio.to_thread(
                    lambda: supabase.table("conversations")
                    .update({"updated_at": now})
                    .eq("thread_id", thread_id)
                    .execute()
                )
            else:
                # Generate title and insert new record
                title = await HistoryService._generate_title(query or "New Chat", answer or "")
                logger.info(f"Creating new thread: {thread_id} with title: '{title}'")
                
                await asyncio.to_thread(
                    lambda: supabase.table("conversations").insert({
                        "thread_id": thread_id,
                        "user_id": user_id,
                        "title": title,
                        "created_at": now,
                        "updated_at": now
                    }).execute()
                )
                
        except Exception as e:
            logger.error(f"Thread metadata error for {thread_id}: {e}")

    @staticmethod
    async def rename_thread(thread_id: str, user_id: str, new_title: str) -> None:
        """
        Rename a specific thread. 
        """
        if not supabase: 
            return
            
        try:
            now = datetime.now(timezone.utc).isoformat()
            
            await asyncio.to_thread(
                lambda: supabase.table("conversations")
                .update({
                    "title": new_title,
                    "updated_at": now
                })
                .eq("thread_id", thread_id)
                .eq("user_id", user_id)
                .execute()
            )
            logger.info(f"Renamed thread {thread_id} to '{new_title}'")
            
        except Exception as e:
            logger.error(f"Rename thread error: {e}")
            raise e

    @staticmethod
    async def get_user_threads(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Fetch the list of conversations for a user, ordered by most recently updated.
        """
        if not supabase: 
            return []
            
        try:
            response = await asyncio.to_thread(
                lambda: supabase.table("conversations")
                .select("*")
                .eq("user_id", user_id)
                .order("updated_at", desc=True)
                .limit(limit)
                .execute()
            )
            return response.data or []
        except Exception as e:
            logger.error(f"Fetch threads error: {e}")
            return []

    @staticmethod
    async def get_thread_messages(app_state: Any, thread_id: str) -> List[Dict[str, str]]:
        """
        Fetch messages from the LangGraph state (checkpoint).
        """
        if not hasattr(app_state, "agent_graph"): 
            logger.warning("Agent graph not found in app_state")
            return []
            
        try:
            config = {"configurable": {"thread_id": thread_id}}
            # Use aget_state for async retrieval from checkpointer
            snapshot = await app_state.agent_graph.aget_state(config)
            
            if not snapshot.values: 
                return []

            messages = []
            # Parse LangChain messages into simple dicts for frontend
            for msg in snapshot.values.get("messages", []):
                if msg.type in ("human", "ai"):
                    messages.append({
                        "role": "user" if msg.type == "human" else "ai",
                        "content": msg.content
                    })
            return messages
        except Exception as e:
            logger.error(f"Message fetch error for thread {thread_id}: {e}")
            return []

    @staticmethod
    async def delete_thread(thread_id: str, user_id: str) -> None:
        """
        Delete a thread's metadata from Supabase.
        Note: This does not clear LangGraph checkpoints unless configured separately.
        """
        if not supabase: 
            return
            
        try:
            await asyncio.to_thread(
                lambda: supabase.table("conversations")
                .delete()
                .eq("thread_id", thread_id)
                .eq("user_id", user_id)
                .execute()
            )
            logger.info(f"Deleted thread {thread_id}")
        except Exception as e:
            logger.error(f"Delete thread error: {e}")