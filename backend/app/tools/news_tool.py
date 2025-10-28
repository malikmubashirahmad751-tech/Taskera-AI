from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.tools import StructuredTool

search = DuckDuckGoSearchRun()

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
