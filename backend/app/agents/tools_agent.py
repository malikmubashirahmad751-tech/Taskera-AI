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
    try:
        return await call_mcp("web_search", {"query": query})
    except Exception as e:
        logger.error(f"[Tool:Search] Error: {e}")
        return f"Search failed: {str(e)}"

@tool
async def wiki_tool(query: str) -> str:
    """
    Fetch information from Wikipedia.
    Best for: historical facts, scientific concepts, biographies.
    """
    try:
        return await call_mcp("wikipedia_search", {"query": query})
    except Exception as e:
        logger.error(f"[Tool:Wiki] Error: {e}")
        return f"Wikipedia search failed: {str(e)}"

@tool
async def weather_tool(location: str) -> str:
    """
    Get current weather for a specific city.
    Example: weather_tool("London") or weather_tool("New York")
    """
    try:
        return await call_mcp("weather_search", {"location": location})
    except Exception as e:
        logger.error(f"[Tool:Weather] Error: {e}")
        return f"Weather lookup failed: {str(e)}"

@tool
async def latest_news_tool(headline: str) -> str:
    """
    Fetch latest news headlines and summaries about a topic.
    Example: latest_news_tool("artificial intelligence")
    """
    try:
        return await call_mcp("latest_news_tool", {"headline": headline})
    except Exception as e:
        logger.error(f"[Tool:News] Error: {e}")
        return f"News fetch failed: {str(e)}"

@tool
async def calculator_tool(expression: str) -> str:
    """
    Evaluate mathematical expressions safely.
    Supports: +, -, *, /, **, sqrt, sin, cos, etc.
    Example: calculator_tool("2 + 2 * 3")
    """
    try:
        return await call_mcp("calculator_tool", {"expression": expression})
    except Exception as e:
        logger.error(f"[Tool:Calc] Error: {e}")
        return f"Calculation error: {str(e)}"

@tool
async def summarize_tool(text: str) -> str:
    """
    Summarize long text into a concise version.
    Useful for condensing articles, documents, or long responses.
    """
    try:
        return await call_mcp("summarize_tool", {"text": text})
    except Exception as e:
        logger.error(f"[Tool:Summarize] Error: {e}")
        return f"Summarization failed: {str(e)}"

@tool
async def translator_tool(text: str, target_language: str = "English") -> str:
    """
    Translate text into the specified target language.
    Example: translator_tool("Hello world", "Spanish")
    """
    try:
        return await call_mcp("translator_tool", {
            "text": text,
            "target_language": target_language
        })
    except Exception as e:
        logger.error(f"[Tool:Translate] Error: {e}")
        return f"Translation failed: {str(e)}"

@tool
async def headless_browser_search(query: str) -> str:
    """
    Use a headless browser to scrape Google search results.
    More powerful than regular search but slower.
    Use when you need more detailed or structured web content.
    """
    try:
        return await call_mcp("headless_browser_search", {"query": query})
    except Exception as e:
        logger.error(f"[Tool:Browser] Error: {e}")
        return f"Browser search failed: {str(e)}"