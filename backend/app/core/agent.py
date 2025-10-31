import re
from datetime import datetime
from pydantic import SecretStr
import logging

from langchain_openai import ChatOpenAI
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool

from app.core.session_manager import get_user_memory, update_session_on_response
from app.core.config import settings
from app.services.rag_system import create_rag_tool
from app.tools.web_tools import search_tool, wiki_tool
from app.tools.summarize_tool import summarize_tool
from app.tools.news_tool import latest_news_tool
from app.tools.calculator_tool import calculator_tool
from app.tools.translator_tool import translator_tool
from app.tools.weather_tool import weather_tool
from app.tools.image_ocr_tool import image_text_extractor
from app.services.scheduler import add_new_task
from app.services.scheduler import scheduler, start_scheduler, run_research_task, correct_run_date
from app.services.scheduler_service import manage_calendar_events 

logger = logging.getLogger(__name__)

llm = ChatOpenAI(api_key=settings.openai_api_key, model="gpt-3.5-turbo", temperature=0)


@tool
def schedule_research_task(query: str, run_date_iso: str):
    """Schedules a research task for a specific date and time in ISO format."""
    try:
        run_date = datetime.fromisoformat(run_date_iso)
        run_date = correct_run_date(run_date)

        return add_new_task(
            func=run_research_task,
            trigger='date',
            run_date=run_date,
            args=[query]
        )

    except ValueError:
        return "Error: Invalid date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)."
    except Exception as e:
        return f"An unexpected error occurred: {e}"

system_prompt = """You are a multi-functional AI Helping assistant named Devis AI.

**Workflow for Handling User Content:**

1.  **For Document-Based Questions (PDF, TXT, etc.):** Your primary knowledge source for documents is the `local_document_retriever` tool.
    You **MUST** use this tool FIRST for any query that could be answered by user-provided documents.

2.  **For Image-Based Questions (PNG, JPG, etc.):**
    When a user uploads an image, the system automatically extracts the text and saves it to the chat history.
    If the user asks a follow-up question (like "summarize this," "what are the key points," or "translate it"), 
    you **MUST** look at the `chat_history` to find the recently extracted text (it will be in an 'ai' or 'system' message).
    You should then perform the action (e.g., summarize) on that text from the history.
    **DO NOT** use the `image_text_extractor` tool unless the user explicitly asks you to re-analyze an image or you cannot find the text in the history.
    **DO NOT** use `local_document_retriever` for images.

3.  **For General Questions:**
    If the query is not related to uploaded documents or images, use your other tools (like `web_search` or `wikipedia_search`) or answer directly.

**Always use the chat history to understand the full context of the user's query.**
"""

prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt),  
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{input}"), 
    MessagesPlaceholder(variable_name="agent_scratchpad") 
])


def detect_intent(query: str, user_id: str = "") -> str:
    query_lower = query.lower().strip()
    if any(word in query_lower for word in ["hello", "hi", "hey", "how are you?"]):
        return "greeting"
    return "general_question"


def research_query(query: str, user_id: str) -> str:
    logger.info(f"Received query for user '{user_id}': {query}")
    output = "Sorry, an error occurred while processing your request."

    try:
        user_rag_tool = create_rag_tool(api_key=settings.openai_api_key, user_id=user_id)
        
        tools = [
            user_rag_tool, wiki_tool, search_tool, summarize_tool, weather_tool,
            latest_news_tool, calculator_tool, translator_tool,
            schedule_research_task, manage_calendar_events, image_text_extractor
        ]
        
        agent = create_tool_calling_agent(llm=llm, prompt=prompt, tools=tools)
        agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

        memory = get_user_memory(user_id=user_id)
        chat_history = memory.load_memory_variables({}).get("chat_history", [])
        
        intent = detect_intent(query, user_id=user_id)
        
        logger.info("Passing query to the main agent executor.")
        
        response = agent_executor.invoke({
            "input": query,
            "chat_history": chat_history
        })
        output = response.get("output", "Sorry, I couldn't find an answer.")

        memory.save_context({"input": f"intent:{intent}"}, {"output": ""})
        logger.info(f"Saved intent '{intent}' for user '{user_id}' to memory.")

        if "event" in output.lower() or "scheduled" in output.lower():
            current_year = datetime.now().year
            outdated_year_match = re.search(r"20(1[0-9]|2[0-4])", output)
            if outdated_year_match and int(outdated_year_match.group(0)) < current_year:
                output = re.sub(r"20(1[0-9]|2[0-4])", str(current_year), output, 1)
                logger.info(f"🛠 Corrected outdated date in agent response -> {current_year}")


        memory.save_context({"input": query}, {"output": output})
        logger.info(f"Agent response for user '{user_id}': {output}")
        return output

    except Exception as e:
        logger.error(f"Error processing query for user '{user_id}': {e}", exc_info=True)
        return output

    finally:
        logger.info(f"Updating session timer for user '{user_id}'.")
        update_session_on_response(user_id, output)


start_scheduler()