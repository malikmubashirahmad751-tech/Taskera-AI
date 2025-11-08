import os
import asyncio
import random
from langchain_core.tools import StructuredTool, tool
from langchain_google_genai import ChatGoogleGenerativeAI
from app.core.config import settings
from app.core.logger import logger
from playwright.async_api import async_playwright
from langchain_community.tools import DuckDuckGoSearchRun, WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper, OpenWeatherMapAPIWrapper



llm = ChatGoogleGenerativeAI(
    api_key=settings.gemini_api_key,
    model="gemini-2.0-flash-exp",
    temperature=0
)



search = DuckDuckGoSearchRun()
wiki = WikipediaQueryRun(api_wrapper=WikipediaAPIWrapper(wiki_client=None))


def duckduckgo_search_wrapper(query: str) -> str:
    """Performs a live web search using DuckDuckGo."""
    try:
        return search.run(query)
    except Exception as e:
        logger.error(f"DuckDuckGo search failed: {e}")
        return f"Search failed: {str(e)}"


def wikipedia_query_wrapper(query: str) -> str:
    """Fetches a Wikipedia summary for a given query."""
    try:
        return wiki.run(query)
    except Exception as e:
        logger.error(f"Wikipedia search failed: {e}")
        return f"Wikipedia search failed: {str(e)}"


search_tool = StructuredTool.from_function(
    name="web_search",
    func=duckduckgo_search_wrapper,
    description="Performs a real-time web search using DuckDuckGo. Use for simple, general queries."
)

wiki_tool = StructuredTool.from_function(
    name="wikipedia_search",
    func=wikipedia_query_wrapper,
    description="Fetches live data from Wikipedia based on the query. Good for facts and definitions."
)



openweathermap_api_key = os.getenv("OPENWEATHERMAP_API_KEY")
if openweathermap_api_key:
    weather_wrapper = OpenWeatherMapAPIWrapper(openweathermap_api_key=openweathermap_api_key)
else:
    logger.warning("OPENWEATHERMAP_API_KEY not found in environment variables")
    weather_wrapper = None


def weather_search(location: str) -> str:
    """
    Get the current weather for a specific city.
    This tool REQUIRES a 'location' string.
    """
    if not weather_wrapper:
        return "Weather service is not configured. Please set OPENWEATHERMAP_API_KEY in .env file."
    
    if not location or location.strip().lower() in ["", "current", "none"]:
        return "Error: A valid city name is required. Please provide a city name."

    try:
        logger.info(f"Fetching weather for: {location}")
        return weather_wrapper.run(location)
    except Exception as e:
        logger.error(f"Weather tool failed for '{location}': {e}")
        return f"Sorry, I couldn't fetch the weather for '{location}'. Please check the city name and try again."


weather_tool = StructuredTool.from_function(
    func=weather_search,
    name="weather_search",
    description=(
        "Get current weather for a given city. This tool REQUIRES a 'location' string. "
        "If the user does not provide a location, you MUST ask them for one first, "
        "and then call this tool again with the location they provide."
    )
)



@tool
async def headless_browser_search(query: str) -> str:
    """
    Uses a headless browser (Playwright) to perform a Google search and
    extract meaningful text content from the results.
    """
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

                content = await page.evaluate(
                    "() => document.body.innerText.slice(0, 8000)"
                )
                if content:
                    logger.info(f"Successfully scraped content (size: {len(content)})")
                    collected_texts.append(
                        f"--- Search results for '{query}' ---\n{content.strip()}\n"
                    )
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
    """
    Fetches the latest news headlines and summaries about a topic
    using web search.
    """
    try:
        logger.info(f"Fetching news for: {headline}")
        query = f"latest news about {headline}"
        
        result = duckduckgo_search_wrapper(query)
        return result

    except Exception as e:
        logger.error(f"News tool failed for '{headline}': {e}")
        return f"Error fetching news: {e}"


latest_news_tool = StructuredTool.from_function(
    name="latest_news_tool",
    func=latest_news_tool_function,
    description="Fetches the latest news headlines and summaries about a topic."
)



def calculator_tool_function(expression: str) -> str:
    """Evaluates basic mathematical expressions safely."""
    try:
        allowed = "0123456789+-*/(). "
        if not all(c in allowed for c in expression):
            return "Invalid characters in expression."
        result = eval(expression, {"__builtins__": {}}, {})
        return f"The result of '{expression}' is {result}"
    except Exception as e:
        return f"Error evaluating expression: {e}"


calculator_tool = StructuredTool.from_function(
    name="calculator_tool",
    func=calculator_tool_function,
    description="Performs basic arithmetic calculations like addition, subtraction, multiplication, and division."
)


def summarize_text(text: str) -> str:
    """Summarize a given text input."""
    try:
        response = llm.invoke([
            ("system", "You are a helpful summarization assistant."),
            ("human", f"Summarize the following text:\n\n{text}")
        ])
        return response.content if hasattr(response, 'content') else str(response)
    except Exception as e:
        logger.error(f"Summarization failed: {e}")
        return f"Error summarizing text: {e}"


summarize_tool = StructuredTool.from_function(
    name="summarize_tool",
    func=summarize_text,
    description="Summarizes any given text or query into a concise summary."
)



def translator_tool_function(text: str, target_language: str = "English") -> str:
    """Translates text into the specified target language."""
    try:
        response = llm.invoke([
            ("system", "You are a multilingual translator."),
            ("human", f"Translate this text to {target_language}: {text}")
        ])
        return response.content if hasattr(response, 'content') else str(response)
    except Exception as e:
        logger.error(f"Translation failed: {e}")
        return f"Translation error: {e}"


translator_tool = StructuredTool.from_function(
    name="translator_tool",
    func=translator_tool_function,
    description="Translates text into a specified language. Provide 'text' and 'target_language'."
)