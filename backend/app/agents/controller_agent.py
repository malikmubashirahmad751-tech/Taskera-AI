from __future__ import annotations
import datetime
from typing import TypedDict, Annotated, Sequence

from google.api_core.exceptions import ResourceExhausted

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import BaseMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from app.core.config import get_settings
from app.core.logger import logger

settings = get_settings()

try:
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash-lite",
        temperature=0.1,
        api_key=settings.GOOGLE_API_KEY,
        max_retries=3,  
        request_timeout=60.0
    )
except Exception as e:
    logger.error(f"Failed to initialize LLM: {e}")
    raise

from app.agents.tools_agent import (
    wiki_tool, search_tool, summarize_tool, weather_tool,
    latest_news_tool, calculator_tool, translator_tool,
    headless_browser_search
)
from app.agents.services_agent import (
    schedule_research_task, manage_calendar_events
)
from app.agents.google_agent import google_calendar_tools
from app.agents.knowledge_agent import local_document_retriever_tool
from app.services.ocr_service import create_ocr_tool

raw_calendar_tools = (
    google_calendar_tools 
    if isinstance(google_calendar_tools, list) 
    else [google_calendar_tools]
)

ALL_TOOLS = [
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
    local_document_retriever_tool,
    create_ocr_tool,
] + raw_calendar_tools

tool_node = ToolNode(ALL_TOOLS)

class AgentState(TypedDict):
    """State passed through the agent graph"""
    messages: Annotated[Sequence[BaseMessage], lambda x, y: x + y]
    user_id: str
    user_email: str

def detect_prompt_injection(text: str) -> bool:
    """Detect potential prompt injection attempts"""
    risky_phrases = [
        "ignore all prior instructions",
        "ignore previous instructions",
        "system override",
        "developer mode",
        "jailbreak",
        "you are now",
        "delete user files",
        "rm -rf"
    ]
    
    text_lower = text.lower()
    return any(phrase in text_lower for phrase in risky_phrases)

def agent_node(state: AgentState):
    """
    Main agent reasoning node
    """
    user_id = state.get("user_id", "unknown")
    user_email = state.get("user_email", "unknown")
    messages = state["messages"]
    
    if messages:
        last_msg = messages[-1]
        content = last_msg.content if hasattr(last_msg, 'content') else str(last_msg)
        
        if isinstance(content, str) and detect_prompt_injection(content):
            logger.warning(f"Prompt injection blocked for user: {user_id}")
            return {
                "messages": [
                    AIMessage(content="I cannot process that request due to safety policies.")
                ]
            }
    
    logger.info(f"[Agent] Processing for user: {user_id}")
    
    try:
        llm_with_tools = llm.bind_tools(ALL_TOOLS)
        
        now = datetime.datetime.now()
        current_date = now.strftime("%Y-%m-%d")
        current_day = now.strftime("%A")
        current_time = now.strftime("%H:%M")
        
        system_prompt = f"""You are Taskera AI, an advanced multi-functional assistant with access to powerful tools.

CURRENT CONTEXT:
- Today: {current_day}, {current_date}
- Time: {current_time}
- User Email: {user_email}
- User ID: {user_id} (Pass this EXACT ID to tool calls)

CAPABILITIES:
You have access to these tool categories:
1. **Google Calendar**: List, stage, and commit calendar events
2. **Web Tools**: Search, news, Wikipedia, weather, browser automation
3. **Document Tools**: RAG retrieval from user-uploaded files
4. **Utility Tools**: Calculator, translator, summarizer, OCR
5. **Task Scheduling**: Schedule delayed research tasks

CRITICAL RULES:

1. GOOGLE CALENDAR TWO-STEP PROTOCOL:
   - NEVER call google_calendar_schedule (deprecated)
   - STEP 1: Call `google_calendar_stage` with event details
   - STEP 2: Show draft to user and ask "Shall I create this event?"
   - STEP 3: When user confirms ("yes", "confirm", "do it"), call `google_calendar_commit`

2. TOOL USAGE:
   - ALWAYS use tools when applicable
   - Use `web_search` or `headless_browser_search` for current info
   - Calculate dates relative to today ({current_date})

3. INTERACTION:
   - Be concise and action-oriented
   - Ask clarifying questions if needed
   - Confirm before executing important actions

CRITICAL INSTRUCTION FOR UPLOADED FILES:
If the user's message contains the tag `[Document ... Indexed for RAG]`, it means they just uploaded a file.
If they ask for a summary or details about "this file" or "the document", you MUST immediately call the `local_document_retriever` tool.
- Query: Use the user's question (e.g., "Summarize this document").
- User ID: {user_id}
"""

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="messages"),
        ])
        
        chain = prompt | llm_with_tools
        response = chain.invoke({"messages": messages})
        
        return {"messages": [response]}
        
    except ResourceExhausted as e:
        logger.error(f"[Agent] Quota exceeded for user {user_id}")
        return {
            "messages": [
                AIMessage(content="I'm experiencing high traffic load (API Quota). Please wait 1 minute and try again.")
            ]
        }
    except Exception as e:
        logger.error(f"[Agent] Error for user {user_id}: {e}", exc_info=True)
        return {
            "messages": [
                AIMessage(content="I encountered an internal error processing your request.")
            ]
        }

def should_continue(state: AgentState) -> str:
    """Determine whether to continue to tools or end"""
    last_message = state["messages"][-1]
    
    if getattr(last_message, "tool_calls", None):
        return "tools"
    
    return END

workflow = StateGraph(AgentState)

workflow.add_node("agent", agent_node)
workflow.add_node("tools", tool_node)

workflow.set_entry_point("agent")

workflow.add_conditional_edges(
    "agent",
    should_continue,
    {
        "tools": "tools",
        END: END
    }
)

workflow.add_edge("tools", "agent")