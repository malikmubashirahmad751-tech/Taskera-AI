from typing import List
from langchain_core.tools import BaseTool, tool
from app.mcp_client import call_mcp
from app.core.logger import logger
from app.core.context import get_current_user_id


@tool
async def search_tool(query: str) -> str:
    """Perform real-time web search using DuckDuckGo."""
    return await call_mcp("web_search", {"query": query})

@tool
async def wiki_tool(query: str) -> str:
    """Fetch information from Wikipedia."""
    return await call_mcp("wikipedia_search", {"query": query})

@tool
async def weather_tool(location: str) -> str:
    """Get current weather for a specific city."""
    return await call_mcp("weather_search", {"location": location})

@tool
async def latest_news_tool(topic: str, time_filter: str = "w") -> str:
    """Fetch latest news headlines. time_filter: 'd'=24h, 'w'=week, 'm'=month."""
    return await call_mcp("latest_news_tool", {"headline": topic, "time_filter": time_filter})

@tool
async def calculator_tool(expression: str) -> str:
    """Evaluate mathematical expressions safely."""
    return await call_mcp("calculator_tool", {"expression": expression})

@tool
async def summarize_tool(text: str) -> str:
    """Summarize long text into a concise version."""
    return await call_mcp("summarize_tool", {"text": text})

@tool
async def translator_tool(text: str, target_language: str = "English") -> str:
    """Translate text into the specified target language."""
    return await call_mcp("translator_tool", {"text": text, "target_language": target_language})

@tool
async def headless_browser_search(query: str) -> str:
    """Use a headless browser to scrape Google search results."""
    return await call_mcp("headless_browser_search", {"query": query})

@tool
async def local_document_retriever_tool(query: str) -> str:
    """Search in user's uploaded documents/PDFs."""
    user_id = get_current_user_id()
    if not user_id:
        return "Error: No user context found."
    return await call_mcp("local_document_retriever", {"query": query, "user_id": user_id})

@tool
async def ocr_tool(file_name: str) -> str:
    """Extract text from an uploaded image file using OCR."""
    user_id = get_current_user_id()
    if not user_id:
        return "Error: No user context found."
    return await call_mcp("image_text_extractor", {"file_name": file_name, "user_id": user_id})

@tool
async def schedule_research_task(query: str, run_date_iso: str) -> str:
    """Schedule a background research task. Format: YYYY-MM-DDTHH:MM:SS"""
    user_id = get_current_user_id()
    if not user_id:
        return "Error: No user context found."
    return await call_mcp("schedule_research_task", {
        "query": query, 
        "run_date_iso": run_date_iso, 
        "user_id": user_id
    })

@tool
async def manage_calendar_events(
    action: str, 
    title: str = "", 
    start_time: str = "", 
    description: str = "",
    event_id: str = ""
) -> str:
    """Manage calendar events. Actions: 'create', 'list', 'update', 'delete'"""
    user_id = get_current_user_id()
    if not user_id:
        return "Error: No user context found."
    return await call_mcp("manage_calendar_events", {
        "action": action,
        "title": title,
        "start_time": start_time,
        "description": description,
        "event_id": event_id,
        "user_id": user_id
    })

def get_all_tools(user_id: str = None) -> List[BaseTool]:
    """
    Returns all available tools.
    Note: user_id parameter is kept for compatibility but context is used instead.
    """
    return [
        search_tool,
        wiki_tool,
        weather_tool,
        latest_news_tool,
        calculator_tool,
        summarize_tool,
        translator_tool,
        headless_browser_search,
        local_document_retriever_tool,
        ocr_tool,
        schedule_research_task,
        manage_calendar_events,
    ]