from langchain_openai import ChatOpenAI
from langchain_core.tools import StructuredTool
from app.core.config import settings

llm = ChatOpenAI(api_key=settings.openai_api_key, model="gpt-3.5-turbo", temperature=0)

def translator_tool_function(text: str, target_language: str = "English") -> str:
    """Translates text into the specified target language."""
    try:
        response = llm.invoke([
            ("system", "You are a multilingual translator."),
            ("human", f"Translate this text to {target_language}: {text}")
        ])
       
        if isinstance(response.content, list):
            
            content = ""
            for item in response.content:
                if isinstance(item, str):
                    content += item
                elif isinstance(item, dict) and "content" in item:
                    content += str(item["content"])
            return content.strip()
        return str(response.content).strip()
    except Exception as e:
        return f"Translation error: {e}"

translator_tool = StructuredTool.from_function(
    name="translator_tool",
    func=translator_tool_function,
    description="Translates text into a specified language. Provide 'text' and 'target_language'."
)
