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
from app.services.ocr_service import image_text_extractor


llm =ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0,
    api_key=settings.gemini_api_key)


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
    image_text_extractor,
    headless_browser_search,
]

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], lambda x, y: x + y]
    user_id: str

def get_full_tool_list(user_id: str) -> List:
    """Return the full list of tools for a specific user, including RAG tool."""
    try:
        user_rag_tool = create_rag_tool(api_key=settings.gemini_api_key, user_id=user_id)
        return [user_rag_tool] + static_tools
    except Exception as e:
        logger.error(f"Failed to create RAG tool for user {user_id}: {e}. Proceeding without it.")
        return static_tools

def agent_node(state: AgentState):
    """Primary node that calls the LLM with the correct tools bound."""
    user_id = state.get("user_id", "unknown")
    messages = state["messages"]

    logger.info(f"Agent node executing for user: {user_id}")

    all_tools = get_full_tool_list(user_id)
    llm_with_tools = llm.bind_tools(all_tools)

    system_prompt = """You are a multi-functional AI assistant named Devis AI.

    **Core Instruction: CONTEXT AWARENESS**
    This is your most important rule. You must pay close attention to the immediate conversational history.
    **If you have just asked a question (e.g., "What city?"), the user's next message is the answer to that question.**
    You MUST use that answer to complete the tool call you were trying to make (e.g., use the city to call `weather_tool`).
    Do not treat the user's answer as a new, separate query for a different tool.

    **Tool Priority & Purpose:**

    1.  **Image Analysis (OCR):** `image_text_extractor`
        * Use this tool when the user provides an image and asks to read text from it.

    2.  **Document/File Queries:** `local_document_retriever` (This is your RAG tool)
        * Use this ONLY for questions about specific documents the user has uploaded.
        * **DO NOT** use this for general knowledge, weather, news, or web searches.

    3.  **Weather:** `weather_tool`
        * Use this to get the current weather. It requires a 'location'.
        * If you ask for a location, the user's next message IS that location. Call this tool again with that location.

    4.  **Scheduling:** `schedule_research_task` or `manage_calendar_events`
        * Use these to create, manage, or check calendar events and scheduled tasks.

    5.  **News:** `latest_news_tool`
        * Use this to get current news headlines.

    6.  **Web Browsing:** `headless_browser_search`
        * Use this for complex queries that require browsing a specific URL or finding live data online.

    7.  **General Search:** `search_tool` or `wiki_tool`
        * Use these for general knowledge, facts, and definitions that are *not* in the user's documents.

    8.  **Other Tools:**
        * `calculator_tool`: For math calculations.
        * `translator_tool`: For translating text.
        * `summarize_tool`: For summarizing long text.
    """

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="messages"),
    ])

    agent_chain = prompt | llm_with_tools
    response = agent_chain.invoke({"messages": messages})

    return {"messages": [response]}

def should_continue(state: AgentState) -> str:
    """Decides whether to call tools or end."""
    if not state["messages"]:
        return "agent"
    last_message = state["messages"][-1]
    if getattr(last_message, "tool_calls", None):
        return "execute_tools"
    return END

def execute_tools_node(state: AgentState):
    """Executes the tools dynamically based on the user ID in state."""
    user_id = state.get("user_id", "unknown")
    tools = get_full_tool_list(user_id)

    tool_node = ToolNode(tools)
    return tool_node.invoke(state)

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