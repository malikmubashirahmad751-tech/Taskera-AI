from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from app.core.config import settings

llm = ChatOpenAI(api_key=settings.openai_api_key, model="gpt-3.5-turbo", temperature=0)

def summarize_text(text: str) -> str:
    """Summarize a given text input."""
    response = llm.invoke([
        ("system", "You are a helpful summarization assistant."),
        ("human", f"Summarize the following text:\n\n{text}")
    ])

    summary = response[0]['content'] if isinstance(response, list) and 'content' in response[0] else str(response)
    return summary.strip()

summarize_tool = StructuredTool.from_function(
    name="summarize_tool",
    func=summarize_text,
    description="Summarizes any given text or query into a concise summary."
)
