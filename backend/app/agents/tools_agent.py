import asyncio
from langchain_core.tools import tool
from app.mcp_client import call_mcp

@tool
async def search_tool(query: str) -> str:
    """(PROXY) Performs a real-time web search using DuckDuckGo."""
    return await call_mcp("web_search", {"query": query})

@tool
async def wiki_tool(query: str) -> str:
    """(PROXY) Fetches live data from Wikipedia based on the query."""
    return await call_mcp("wikipedia_search", {"query": query})

@tool
async def weather_tool(location: str) -> str:
    """(PROXY) Get current weather for a given city."""
    return await call_mcp("weather_search", {"location": location})

@tool
async def latest_news_tool(headline: str) -> str:
    """(PROXY) Fetches the latest news headlines and summaries."""
    return await call_mcp("latest_news_tool", {"headline": headline})

@tool
async def calculator_tool(expression: str) -> str:
    """(PROXY) Performs basic arithmetic calculations."""
    return await call_mcp("calculator_tool", {"expression": expression})

@tool
async def summarize_tool(text: str) -> str:
    """(PROXY) Summarizes any given text or query."""
    return await call_mcp("summarize_tool", {"text": text})

@tool
async def translator_tool(text: str, target_language: str = "English") -> str:
    """(PROXY) Translates text into a specified language."""
    return await call_mcp("translator_tool", {
        "text": text,
        "target_language": target_language
    })

@tool
async def headless_browser_search(query: str) -> str:
    """(PROXY) Uses a headless browser for complex Google searches."""
    return await call_mcp("headless_browser_search", {"query": query})
