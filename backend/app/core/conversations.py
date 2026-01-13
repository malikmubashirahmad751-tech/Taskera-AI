import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate

from app.core.database import supabase
from app.core.logger import logger
from app.core.config import get_settings

settings = get_settings()

class HistoryService:
    @staticmethod
    async def _generate_title(query: str, answer: str) -> str:
        """Generate concise title using LLM"""
        if not settings.GOOGLE_API_KEY:
            return (query[:30] + "...") if len(query) > 30 else (query or "New Chat")

        try:
            llm = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash-lite",
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
            
            safe_query = (query or "")[:500]
            
            chain = prompt | llm
            result = await chain.ainvoke({"query": safe_query})
            
            title = result.content.strip()
            
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
    ):
        """Create or update thread metadata"""
        if not supabase:
            return

        try:
            now = datetime.now(timezone.utc).isoformat()
            
            response = await asyncio.to_thread(
                lambda: supabase.table("conversations")
                .select("thread_id")
                .eq("thread_id", thread_id)
                .execute()
            )
            
            exists = bool(response.data)
            
            if exists:
                await asyncio.to_thread(
                    lambda: supabase.table("conversations")
                    .update({"updated_at": now})
                    .eq("thread_id", thread_id)
                    .execute()
                )
            else:
                
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
    async def get_user_threads(user_id: str, limit: int = 50) -> List[Dict]:
        """Fetch user's conversation list"""
        if not supabase: return []
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
    async def get_thread_messages(app_state, thread_id: str) -> List[Dict]:
        """Fetch messages from LangGraph state"""
        if not hasattr(app_state, "agent_graph"): return []
        try:
            config = {"configurable": {"thread_id": thread_id}}
            snapshot = await app_state.agent_graph.aget_state(config)
            
            if not snapshot.values: return []

            messages = []
            for msg in snapshot.values.get("messages", []):
                if msg.type in ("human", "ai"):
                    messages.append({
                        "role": "user" if msg.type == "human" else "ai",
                        "content": msg.content
                    })
            return messages
        except Exception as e:
            logger.error(f"Message fetch error: {e}")
            return []

    @staticmethod
    async def delete_thread(thread_id: str, user_id: str):
        """Delete thread metadata"""
        if not supabase: return
        try:
            await asyncio.to_thread(
                lambda: supabase.table("conversations")
                .delete()
                .eq("thread_id", thread_id)
                .eq("user_id", user_id)
                .execute()
            )
        except Exception as e:
            logger.error(f"Delete thread error: {e}")