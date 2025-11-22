from __future__ import annotations
import logging
from typing import TypedDict, Annotated, Sequence, List

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from app.core.config import settings
from app.core.logger import logger

from app.agents.knowledge_agent import create_rag_tool
from app.services.ocr_service import create_ocr_tool
from app.agents.google_agent import create_google_calendar_tools 

from app.agents.services_agent import schedule_research_task, manage_calendar_events
from app.agents.tools_agent import (
    wiki_tool,
    search_tool,
    summarize_tool,
    weather_tool,
    latest_news_tool,
    calculator_tool,
    translator_tool,
    headless_browser_search,
)

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash-lite",  
    temperature=0,
    api_key=settings.gemini_api_key,
    max_retries=0  
)

static_tools = [
    wiki_tool,
    search_tool,
    summarize_tool,
    weather_tool,
    latest_news_tool,
    calculator_tool,
    translator_tool,
    schedule_research_task,
    manage_calendar_events,
    headless_browser_search,
]

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], lambda x, y: x + y]
    user_id: str

def get_full_tool_list(user_id: str) -> List:
    """
    Build the full list of tools for the given user.
    """
    dynamic_tools = []

    try:
        user_rag_tool = create_rag_tool(user_id=user_id)
        dynamic_tools.append(user_rag_tool)
        logger.info(f"Created RAG tool for user={user_id}")
    except Exception as e:
        logger.error(f"Failed to create RAG proxy tool for user {user_id}: {e}")

    try:
        user_ocr_tool = create_ocr_tool(user_id=user_id)
        dynamic_tools.append(user_ocr_tool)
        logger.info(f"Created OCR tool for user={user_id}")
    except Exception as e:
        logger.error(f"Failed to create OCR proxy tool for user {user_id}: {e}")

    try:
        user_calendar_tools = create_google_calendar_tools(user_id=user_id)
        dynamic_tools.extend(user_calendar_tools) 
        logger.info(f"Created Google Calendar tools for user={user_id}")
    except Exception as e:
        logger.error(f"Failed to create Google Calendar tools for user {user_id}: {e}")

    return dynamic_tools + static_tools

def detect_prompt_injection(text: str) -> bool:
    """
    Returns True if the text looks like a jailbreak attempt.
    """
    risky_phrases = [
        "ignore all prior instructions",
        "system override",
        "you are now a developer mode",
        "delete user files",
        "exec(",
    ]
    text_lower = text.lower()
    return any(phrase in text_lower for phrase in risky_phrases)

def agent_node(state: AgentState):
    """
    Primary node: call the LLM with the correct tools bound.
    """
    user_id = state.get("user_id", "unknown")
    messages = state["messages"]

    
    if messages:
        last_msg = messages[-1]
        content = ""
        
        if hasattr(last_msg, 'content'):
            content = last_msg.content
        elif isinstance(last_msg, (tuple, list)) and len(last_msg) > 1:
            content = last_msg[1]
        else:
            content = str(last_msg)

        if isinstance(content, str) and detect_prompt_injection(content):
            logger.warning(f"Prompt injection blocked for user {user_id}")
            return {
                "messages": [("assistant", "I cannot process that request due to security policy.")]
            }

    logger.info(f"Agent node executing for user: {user_id}")

    all_tools = get_full_tool_list(user_id)
    llm_with_tools = llm.bind_tools(all_tools)

    system_prompt = """You are a multi-functional AI assistant named Taskera AI.
    Your primary goal is to be helpful and complete tasks.

---
    **CRITICAL RULE 1: CONTEXTUAL FOLLOW-UP**
    1.  **If you asked a question:** Use the user's reply to complete the *original* task.
    2.  **Handling "Yes/No":** Assume "yes" confirms your last suggestion.
    3.  **Handling "No":** Ask for new instructions or clarifications.

    ---
    **CRITICAL RULE 2: TOOL vs. CHAT**
    -   **If a tool can answer the question, USE THE TOOL.**
    -   Only provide general chat if no tool applies.
    -   If the request is vague, ASK CLARIFYING QUESTIONS.

    ---
    **Tool Priority & Purpose:**

    1.  **Google Calendar (REAL): `google_calendar_list`, `google_calendar_schedule`**
        * **Check Schedule:** Use `google_calendar_list` to find free slots or see what's up next.
        * **Book Meetings:** Use `google_calendar_schedule` to create actual events on the user's calendar.
        * *Auth Error:* If these tools fail with an auth error, tell the user to log in via the dashboard.

    2.  **Image Analysis (OCR): `image_text_extractor`**
        * Use this if the user uploaded an image.

    3.  **Document/File Queries (RAG): `local_document_retriever`**
        * Use this to answer questions about user-uploaded documents.

    4.  **Math/Computation: `wolfram_alpha_query`**
        * Use this for math, science, and unit conversions.

    5.  **Weather: `weather_tool`**
        * Use this for weather forecasts.

    6.  **Internal Scheduling: `schedule_research_task`**
        * Use this for *internal* agent tasks (like "search for this topic tomorrow"), NOT for meetings.

    7.  **Web Search: `search_tool`, `headless_browser_search`**
        * Use for real-time information.

    8.  **Other:** `calculator_tool`, `translator_tool`, `summarize_tool`, `latest_news_tool`
    """

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="messages"),
    ])

    agent_chain = prompt | llm_with_tools

    response = agent_chain.invoke({"messages": messages})

    return {"messages": [response]}

def should_continue(state: AgentState) -> str:
    if not state["messages"]:
        return "agent"
    last_message = state["messages"][-1]
    if getattr(last_message, "tool_calls", None):
        return "execute_tools"
    return END

async def execute_tools_node(state: AgentState):
    """
    Executes the tools dynamically based on the user ID in state.
    """
    user_id = state.get("user_id", "unknown")
    tools = get_full_tool_list(user_id) 

    tool_node = ToolNode(tools)
    return await tool_node.ainvoke(state)

workflow = StateGraph(AgentState)
workflow.add_node("agent", agent_node)
workflow.add_node("execute_tools", execute_tools_node)
workflow.set_entry_point("agent")

workflow.add_conditional_edges(
    "agent",
    should_continue,
    {"execute_tools": "execute_tools", END: END}
)
workflow.add_edge("execute_tools", "agent")

app = workflow.compile()
logger.info("LangGraph workflow compiled successfully.")