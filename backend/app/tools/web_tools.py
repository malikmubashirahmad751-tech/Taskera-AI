from langchain_community.tools import DuckDuckGoSearchRun, WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper
from langchain_core.tools import StructuredTool


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
