import os
import random
import logging
import numexpr  
from langchain_google_genai import ChatGoogleGenerativeAI
from app.core.config import settings
from playwright.async_api import async_playwright
from langchain_community.tools import DuckDuckGoSearchRun, WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper, OpenWeatherMapAPIWrapper

logger = logging.getLogger("Taskera AI")

llm = ChatGoogleGenerativeAI(
    api_key=settings.gemini_api_key,
    model="gemini-2.0-flash-lite-preview-02-05",
    temperature=0,
    max_retries=0  
)

search = DuckDuckGoSearchRun()
wiki = WikipediaQueryRun(api_wrapper=WikipediaAPIWrapper(wiki_client=None))

def duckduckgo_search_wrapper(query: str) -> str:
    """(IMPL) Performs a live web search using DuckDuckGo."""
    try:
        return search.run(query)
    except Exception as e:
        logger.error(f"DuckDuckGo search failed: {e}")
        return f"Search failed: {str(e)}"

def wikipedia_query_wrapper(query: str) -> str:
    """(IMPL) Fetches a Wikipedia summary for a given query."""
    try:
        return wiki.run(query)
    except Exception as e:
        logger.error(f"Wikipedia search failed: {e}")
        return f"Wikipedia search failed: {str(e)}"

openweathermap_api_key = os.getenv("OPENWEATHERMAP_API_KEY")
weather_wrapper = None
if openweathermap_api_key:
    weather_wrapper = OpenWeatherMapAPIWrapper(openweathermap_api_key=openweathermap_api_key)
else:
    logger.warning("OPENWEATHERMAP_API_KEY not found in environment variables")

def weather_search(location: str) -> str:
    """(IMPL) Get the current weather for a specific city."""
    if not weather_wrapper:
        return "Weather service is not configured. Please set OPENWEATHERMAP_API_KEY in .env file."
    
    clean_location = location.strip().lower()
    if not clean_location or clean_location in ["", "current", "none", "null"]:
        return "Error: A valid city name is required. Please provide a city name."
    
    try:
        logger.info(f"Fetching weather for: {location}")
        return weather_wrapper.run(location)
    except Exception as e:
        logger.error(f"Weather tool failed for '{location}': {e}")
        return f"Sorry, I couldn't fetch the weather for '{location}'."

async def headless_browser_search(query: str) -> str:
    """(IMPL) Uses a headless browser (Playwright) to perform a Google search."""
    try:
        async with async_playwright() as p:
            browser = await p.firefox.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/91.0.4472.124 Safari/537.36"
                )
            )
            page = await context.new_page()
            
            search_url = f"https://www.google.com/search?q={query}"
            collected_texts = []
            logger.info(f"Browsing to: {search_url}")
            
            try:
                await page.goto(search_url, timeout=20000, wait_until="domcontentloaded")
                await page.wait_for_timeout(random.randint(1500, 3500)) 
                
                content = await page.evaluate("() => document.body.innerText.slice(0, 8000)")
                
                if content:
                    logger.info(f"Successfully scraped content (size: {len(content)})")
                    collected_texts.append(f"--- Search results for '{query}' ---\n{content.strip()}\n")
                else:
                    logger.warning("Scraped content was empty.")
                    
            except Exception as e:
                logger.error(f"Error accessing {search_url}: {e}")
                collected_texts.append(f"[Error accessing {search_url}: {e}]")
            
            await browser.close()
            return "\n\n".join(collected_texts) if collected_texts else "No relevant content found."
            
    except Exception as e:
        logger.error(f"Error running Playwright: {e}")
        return f"Error running Playwright: {e}"

def latest_news_tool_function(headline: str) -> str:
    """(IMPL) Fetches the latest news headlines and summaries."""
    try:
        logger.info(f"Fetching news for: {headline}")
        query = f"latest news about {headline}"
        return duckduckgo_search_wrapper(query)
    except Exception as e:
        logger.error(f"News tool failed for '{headline}': {e}")
        return f"Error fetching news: {e}"

def calculator_tool_function(expression: str) -> str:
    """(IMPL) Evaluates basic mathematical expressions safely using NumExpr."""
    try:
        if not expression:
            return "Error: Empty expression."   
        result = numexpr.evaluate(expression).item()
        return f"The result of '{expression}' is {result}"
    except Exception as e:
        logger.warning(f"Calculator error on input '{expression}': {e}")
        return "Error evaluating expression. Please ensure it contains only numbers and basic math operations."

def summarize_text(text: str) -> str:
    """(IMPL) Summarize a given text input."""
    try:
        response = llm.invoke([
            ("system", "You are a helpful summarization assistant."),
            ("human", f"Summarize the following text:\n\n{text}")
        ])
        return response.content if hasattr(response, 'content') else str(response)
    except Exception as e:
        logger.error(f"Summarization failed: {e}")
        return f"Error summarizing text: {e}"

def translator_tool_function(text: str, target_language: str = "English") -> str:
    """(IMPL) Translates text into the specified target language."""
    try:
        response = llm.invoke([
            ("system", "You are a multilingual translator."),
            ("human", f"Translate this text to {target_language}: {text}")
        ])
        return response.content if hasattr(response, 'content') else str(response)
    except Exception as e:
        logger.error(f"Translation failed: {e}")
        return f"Translation error: {e}"