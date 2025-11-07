import os
import asyncio
from langchain_core.tools import StructuredTool, tool
from langchain_google_genai import ChatGoogleGenerativeAI
from app.core.config import settings
from playwright.async_api import async_playwright
from langchain_community.tools import DuckDuckGoSearchRun, WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper, OpenWeatherMapAPIWrapper

llm = ChatGoogleGenerativeAI(api_key=settings.gemini_api_key, model="gemini-2.5-flash", temperature=0)

search = DuckDuckGoSearchRun()
wiki = WikipediaQueryRun(api_wrapper=WikipediaAPIWrapper(wiki_client=None))

def duckduckgo_search_wrapper(query: str) -> str:
    """Performs a live web search using DuckDuckGo."""
    return search.run(query)

def wikipedia_query_wrapper(query: str) -> str:
    """Fetches a Wikipedia summary for a given query."""
    return wiki.run(query)

search_tool = StructuredTool.from_function(
    name="web_search",
    func=duckduckgo_search_wrapper,
    description="Performs a real-time web search using DuckDuckGo."
)
wiki_tool = StructuredTool.from_function(
    name="wikipedia_search",
    func=wikipedia_query_wrapper,
    description="Fetches live data from Wikipedia based on the query."
)



openweathermap_api_key = os.getenv("OPENWEATHERMAP_API_KEY")
weather_wrapper = OpenWeatherMapAPIWrapper(openweathermap_api_key=openweathermap_api_key)

def weather_search(location: str = "") -> str:
    """
    Get the current weather for a city.
    If no city or an invalid placeholder like 'current' is provided, ask the user for it.
    """
    if not location or location.strip().lower() in ["", "current", "none"]:
        return "Can you provide a valid city name to check the weather (e.g., 'Karachi' or 'London, UK')."
    try:
        return weather_wrapper.run(location)
    except Exception as e:
        return f"Sorry, I couldn’t fetch the weather for '{location}'. Please check the city name and try again."

weather_tool = StructuredTool.from_function(
    func=weather_search,
    name="weather_search",
    description="Get current weather for a given city and country code, e.g., 'London, UK'. If city not provided, it asks for one."
)



def latest_news_tool_function(headline: str) -> str:
    """Fetches the latest news."""
    try:
        query = f"latest news about {headline}"
        return search(query)
    except Exception as e:
        return f"Error fetching news: {e}"

latest_news_tool = StructuredTool.from_function(
    name="latest_news_tool",
    func=latest_news_tool_function,
    description="Fetches the latest news."
)



def calculator_tool_function(expression: str) -> str:
    """Evaluates basic mathematical expressions safely."""
    try:
        allowed = "0123456789+-*/(). "
        if not all(c in allowed for c in expression):
            return "Invalid characters in expression."
        result = eval(expression)
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
    response = llm.invoke([
        ("system", "You are a helpful summarization assistant."),
        ("human", f"Summarize the following text:\n\n{text}")
    ])
    try:
        return response.content
    except Exception:
        return str(response)

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
        try:
            return response.content
        except Exception:
            return str(response)
    except Exception as e:
        return f"Translation error: {e}"

translator_tool = StructuredTool.from_function(
    name="translator_tool",
    func=translator_tool_function,
    description="Translates text into a specified language. Provide 'text' and 'target_language'."
)




PREDEFINED_SOURCES = {
    "general": [
        "https://en.wikipedia.org/wiki/",
        "https://www.britannica.com/",
        "https://medium.com/search?q=",
        "https://www.google.com/search?q=",
    ],
    "tech": [
        "https://stackoverflow.com/search?q=",
        "https://github.com/search?q=",
        "https://developer.mozilla.org/en-US/search?q=",
    ],
    "ai": [
        "https://huggingface.co/models",
        "https://paperswithcode.com/search?q=",
        "https://arxiv.org/search/?query=",
    ],
    "news": [
        "https://news.google.com/search?q=",
        "https://www.bbc.com/search?q=",
        "https://www.cnn.com/search?q=",
    ],
}

@tool
async def headless_browser_search(query: str) -> str:
    """
    Uses a headless browser (Playwright) to fetch data from predefined URLs
    and extract meaningful text related to the query.
    """
    async def run_playwright():
        try:
            async with async_playwright() as p:
                browser = await p.firefox.launch(headless=True)
                context = await browser.new_context()
                page = await context.new_page()

                collected_texts = []
                search_url = f"https://www.google.com/search?q={query}"

                try:
                    await page.goto(search_url, timeout=20000)
                    await asyncio.sleep(2) 

                    content = await page.evaluate("""
                        () => {
                            const body = document.body.innerText;
                            return body.slice(0, 3000); // limit size
                        }
                    """)
                    if content:
                        collected_texts.append(f"--- Source: {search_url} ---\n{content.strip()}\n")

                except Exception as e:
                    collected_texts.append(f"[Error accessing {search_url}: {e}]")

                await browser.close()

                if not collected_texts:
                    return "No relevant content found."
                return "\n\n".join(collected_texts)

        except Exception as e:
            return f"Error running Playwright: {e}"

    return await run_playwright()