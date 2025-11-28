import os
import random
import numexpr
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.tools import DuckDuckGoSearchRun, WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper, OpenWeatherMapAPIWrapper
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

from app.core.config import get_settings
from app.core.logger import logger

settings = get_settings()

llm = ChatGoogleGenerativeAI(
    api_key=settings.GOOGLE_API_KEY,
    model="gemini-2.0-flash-lite",
    temperature=0,
    max_retries=1,
    request_timeout=30.0
)

search = DuckDuckGoSearchRun()
wiki = WikipediaQueryRun(api_wrapper=WikipediaAPIWrapper(wiki_client=None))

weather_wrapper = None
if settings.OPENWEATHERMAP_API_KEY:
    try:
        weather_wrapper = OpenWeatherMapAPIWrapper(
            openweathermap_api_key=settings.OPENWEATHERMAP_API_KEY
        )
    except Exception as e:
        logger.warning(f"Weather API initialization failed: {e}")
else:
    logger.info("Weather API key not configured")

def duckduckgo_search_wrapper(query: str) -> str:
    """
    Perform web search using DuckDuckGo
    """
    try:
        logger.info(f"[Search] Query: {query}")
        result = search.run(query)
        return result if result else "No results found"
        
    except Exception as e:
        logger.error(f"[Search] Error: {e}")
        return f"Search failed: {str(e)}"

def wikipedia_query_wrapper(query: str) -> str:
    """
    Fetch Wikipedia summary
    """
    try:
        logger.info(f"[Wiki] Query: {query}")
        result = wiki.run(query)
        return result if result else "No Wikipedia article found"
        
    except Exception as e:
        logger.error(f"[Wiki] Error: {e}")
        return f"Wikipedia search failed: {str(e)}"

def weather_search(location: str) -> str:
    """
    Get current weather for a location
    """
    if not weather_wrapper:
        return (
            "Weather service not available. "
            "Please configure OPENWEATHERMAP_API_KEY in your environment."
        )
    
    clean_location = location.strip()
    if not clean_location or clean_location.lower() in ["", "current", "none", "null"]:
        return "Please provide a valid city name"
    
    try:
        logger.info(f"[Weather] Location: {location}")
        result = weather_wrapper.run(location)
        return result if result else f"Weather data not available for '{location}'"
        
    except Exception as e:
        logger.error(f"[Weather] Error for '{location}': {e}")
        return f"Could not fetch weather for '{location}'"

async def headless_browser_search(query: str) -> str:
    """
    Use Playwright to scrape Google search results
    """
    try:
        async with async_playwright() as p:
            browser = await p.firefox.launch(headless=True)
            
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={'width': 1920, 'height': 1080}
            )
            
            page = await context.new_page()
            search_url = f"https://www.google.com/search?q={query}"
            
            logger.info(f"[Browser] Navigating to: {search_url}")
            
            try:
                await page.goto(
                    search_url,
                    timeout=20000,
                    wait_until="domcontentloaded"
                )
                
                await page.wait_for_timeout(random.randint(1500, 3000))
                
                content = await page.evaluate(
                    "() => document.body.innerText.slice(0, 8000)"
                )
                
                await browser.close()
                
                if content and len(content.strip()) > 50:
                    logger.info(f"[Browser] Scraped {len(content)} characters")
                    return f"**Search Results for '{query}':**\n\n{content.strip()}"
                else:
                    logger.warning("[Browser] Scraped content too short or empty")
                    return "No meaningful content found"
                    
            except PlaywrightTimeout:
                await browser.close()
                logger.error(f"[Browser] Timeout for query: {query}")
                return f"Browser search timed out for '{query}'"
                
    except Exception as e:
        logger.error(f"[Browser] Error: {e}")
        return f"Browser search failed: {str(e)}"

def latest_news_tool_function(headline: str) -> str:
    """
    Fetch latest news about a topic
    """
    try:
        logger.info(f"[News] Query: {headline}")
        query = f"latest news {headline}"
        result = duckduckgo_search_wrapper(query)
        return result
        
    except Exception as e:
        logger.error(f"[News] Error: {e}")
        return f"Failed to fetch news: {str(e)}"

def calculator_tool_function(expression: str) -> str:
    """
    Safely evaluate mathematical expressions using NumExpr
    """
    try:
        if not expression or not expression.strip():
            return "Error: Empty expression"
        
        expression = expression.strip()
        
        result = numexpr.evaluate(expression).item()
        
        logger.info(f"[Calc] {expression} = {result}")
        return f"The result of '{expression}' is **{result}**"
        
    except Exception as e:
        logger.warning(f"[Calc] Error on '{expression}': {e}")
        return (
            "Could not evaluate expression. "
            "Please ensure it contains only numbers and basic operations (+, -, *, /, **, sqrt, etc.)"
        )

def summarize_text(text: str) -> str:
    """
    Summarize text using LLM
    """
    if not text or len(text.strip()) < 50:
        return "Text too short to summarize"
    
    try:
        logger.info(f"[Summarize] Processing {len(text)} characters")
        
        response = llm.invoke([
            ("system", "You are a helpful assistant that creates concise, accurate summaries."),
            ("human", f"Summarize the following text in 3-5 sentences:\n\n{text}")
        ])
        
        summary = response.content if hasattr(response, 'content') else str(response)
        return summary if summary else "Failed to generate summary"
        
    except Exception as e:
        logger.error(f"[Summarize] Error: {e}")
        return f"Summarization failed: {str(e)}"

def translator_tool_function(text: str, target_language: str = "English") -> str:
    """
    Translate text to target language using LLM
    """
    if not text or not text.strip():
        return "Error: Empty text"
    
    try:
        logger.info(f"[Translate] To {target_language}: {text[:50]}...")
        
        response = llm.invoke([
            ("system", f"You are a professional translator. Translate text to {target_language}."),
            ("human", f"Translate this to {target_language}:\n\n{text}")
        ])
        
        translation = response.content if hasattr(response, 'content') else str(response)
        return translation if translation else "Translation failed"
        
    except Exception as e:
        logger.error(f"[Translate] Error: {e}")
        return f"Translation failed: {str(e)}"