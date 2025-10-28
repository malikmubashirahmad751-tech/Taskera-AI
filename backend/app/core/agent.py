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
from app.services.scheduler import add_new_task, start_scheduler, run_research_task, correct_run_date
from app.tools.calender_tool import manage_calendar_events 

logger = logging.getLogger(__name__)
llm = ChatOpenAI(api_key=SecretStr(settings.openai_api_key), model="gpt-3.5-turbo", temperature=0)


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


prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a multi-functional AI Helping assistant.
Your primary knowledge source is the `local_document_retriever` tool.
**You MUST use `local_document_retriever` FIRST for any query that could be answered by user-provided documents.**
Only if the local retriever finds no information should you then consider using `wikipedia_search` or `web_search`.
Use the chat history to understand the context of the user's query."""),

    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{query}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
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
            schedule_research_task, manage_calendar_events
        ]
        
        agent = create_tool_calling_agent(llm=llm, prompt=prompt, tools=tools)
        agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

        memory = get_user_memory(user_id=user_id)
        chat_history = memory.load_memory_variables({}).get("chat_history", [])
        
        intent = detect_intent(query, user_id=user_id)
        memory.save_context({"input": f"intent:{intent}"}, {"output": ""})
        logger.info(f"Saved intent '{intent}' for user '{user_id}' to memory.")

        logger.info("Passing query to the main agent executor.")
        response = agent_executor.invoke({
            "query": query,
            "chat_history": chat_history
        })
        output = response.get("output", "Sorry, I couldn't find an answer.")

        if "event" in output.lower() or "scheduled" in output.lower():
            future_year = datetime.now().year
            outdated_year_match = re.search(r"20(1[0-9]|2[0-4]|23)", output)
            if outdated_year_match:
                corrected_date = datetime.now().strftime("%B %d, %Y at %I:%M %p")
                output = re.sub(r"October\s+\d{1,2},\s*20\d{2}", corrected_date, output)
                output = re.sub(r"20(1[0-9]|2[0-4]|23)", str(future_year), output)
                logger.info(f"🛠 Corrected outdated date in agent response → {corrected_date}")


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
