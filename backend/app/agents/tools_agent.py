import asyncio
from langchain_core.tools import tool
from app.mcp_client import call_mcp
from app.core.logger import logger

@tool
async def search_tool(query: str) -> str:
    """
    Perform real-time web search using DuckDuckGo.
    Use this to find current information, news, or general knowledge.
    """
    return await call_mcp("web_search", {"query": query})

@tool
async def wiki_tool(query: str) -> str:
    """
    Fetch information from Wikipedia.
    """
    return await call_mcp("wikipedia_search", {"query": query})

@tool
async def weather_tool(location: str) -> str:
    """
    Get current weather for a specific city.
    """
    return await call_mcp("weather_search", {"location": location})

# --- FIXED: Added time_filter parameter ---
@tool
async def latest_news_tool(topic: str, time_filter: str = "w") -> str:
    """
    Fetch latest news headlines about a topic.
    
    Args:
        topic: The subject to search for (e.g. "Stock Market", "Iran").
        time_filter: Time range. Use 'd' for past 24 hours (yesterday/today), 
                     'w' for past week, 'm' for past month. Default is 'w'.
    """
    return await call_mcp("latest_news_tool", {"headline": topic, "time_filter": time_filter})
# ------------------------------------------

@tool
async def calculator_tool(expression: str) -> str:
    """
    Evaluate mathematical expressions safely.
    """
    return await call_mcp("calculator_tool", {"expression": expression})

@tool
async def summarize_tool(text: str) -> str:
    """
    Summarize long text into a concise version.
    """
    return await call_mcp("summarize_tool", {"text": text})

@tool
async def translator_tool(text: str, target_language: str = "English") -> str:
    """
    Translate text into the specified target language.
    """
    return await call_mcp("translator_tool", {
        "text": text,
        "target_language": target_language
    })

@tool
async def headless_browser_search(query: str) -> str:
    """
    Use a headless browser to scrape Google search results.
    """
    return await call_mcp("headless_browser_search", {"query": query})