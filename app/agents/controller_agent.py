from __future__ import annotations
import logging
import datetime
from typing import TypedDict, Annotated, Sequence, List

from google.api_core.exceptions import ResourceExhausted

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import BaseMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from app.core.config import settings
from app.core.logger import logger

# Import all tool definitions
from app.agents.knowledge_agent import create_rag_tool 
from app.services.ocr_service import create_ocr_tool 
from app.agents.google_agent import google_calendar_tools 
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

# Initialize LLM
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash-lite-preview-02-05", 
    temperature=0,
    api_key=settings.gemini_api_key,
    max_retries=0  
)

# Flatten calendar tools (handles if google_calendar_tools is list or single)
calendar_tools_list = (
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
    create_rag_tool, 
    create_ocr_tool, 
    *calendar_tools_list 
]

tool_node = ToolNode(ALL_TOOLS)

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], lambda x, y: x + y]
    user_id: str
    user_email: str

def detect_prompt_injection(text: str) -> bool:
    """
    Detect if a given text contains any risky phrases that might be used to inject prompts.
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
    Invokes the LLM with robust error handling for API Limits AND Date Context.
    """
    user_id = state.get("user_id", "unknown")
    user_email = state.get("user_email", "unknown")
    messages = state["messages"]

    # Security Check
    if messages:
        last_msg = messages[-1]
        content = last_msg.content if hasattr(last_msg, 'content') else str(last_msg)
        if isinstance(content, str) and detect_prompt_injection(content):
            logger.warning(f"Prompt injection blocked for user {user_id}")
            return {"messages": [AIMessage(content="I cannot process that request.")]}

    logger.info(f"Agent node executing for user: {user_id}")

    try:
        llm_with_tools = llm.bind_tools(ALL_TOOLS)

        now = datetime.datetime.now()
        current_date = now.strftime("%Y-%m-%d")  
        current_day = now.strftime("%A")         
        current_time = now.strftime("%H:%M")     

        # SYSTEM PROMPT UPDATED FOR 2-STEP CALENDAR FLOW
        system_prompt = f"""You are Taskera AI, a multi-functional, tool-enabled assistant.

CURRENT CONTEXT:
- Today is: {current_day}, {current_date}
- Current time: {current_time}
- User Email: {user_email}
- User Timezone: Assume local time unless specified.

Your purpose is to help the user complete tasks efficiently by using tools intelligently.

1. CALENDAR SCHEDULING PROTOCOL (STRICT)
   To create a Google Calendar event, you MUST follow this 2-step process to ensure accuracy.
   
   PHASE 1: STAGE & VALIDATE
   - Call `google_calendar_stage` with the details (summary, time, attendees).
   - This tool will return a secure "Confirmation Token".
   
   PHASE 2: EXECUTE (Human-in-the-loop)
   - Show the user the details returned by the stage tool.
   - Ask "Do you confirm it to schedule?"
   - If the user says "Yes", "Confirm", "Okay", "Go ahead", "Do it", "Yeah":
     **CALL `google_calendar_commit` IMMEDIATELY using the token from Phase 1.**
   - Do NOT ask for the details again. The token contains them.
   - Do NOT try to use `google_calendar_schedule` (it is deprecated).

2. GENERAL TOOL RULES
   - If a tool can answer the request, YOU MUST USE IT.
   - Only respond conversationally if no tool is suitable.
   - If the user says "tomorrow" or "next Friday", CALCULATE the date based on "Today is {current_date}".

3. TOOL PRIORITY
   - **Google Calendar:** Use `google_calendar_list`, `google_calendar_stage`, `google_calendar_commit`.
   - **Internal Tasks:** Use `schedule_research_task`, `manage_calendar_events` (for non-Google reminders).
   - **RAG/Docs:** Use `local_document_retriever` for uploaded files.
   - **Web/News:** Use `headless_browser_search` or `latest_news_tool` for live info.

4. INTERACTION LOGIC
   - **ACTION OVER TALK:** If the user confirms a pending plan, run the tool immediately.
   - If the user request is unclear, ask clarifying questions.
   - Do not chain multiple tools unless required.

5. TONE & STYLE
   - Clear, concise, professional.
   - Focus on completing the task.
        """

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="messages"),
        ])

        chain = prompt | llm_with_tools
        response = chain.invoke({"messages": messages})

        return {"messages": [response]}

    except ResourceExhausted:
        logger.error(f"Google API Quota Exceeded for user {user_id}")
        return {
            "messages": [
                AIMessage(content="I am currently unavailable because the AI usage limit has been reached. Please try again in a minute.")
            ]
        }
    except Exception as e:
        logger.error(f"Unexpected Agent Error: {e}")
        return {
            "messages": [
                AIMessage(content="An internal error occurred while processing your request. Please check the system logs.")
            ]
        }

def should_continue(state: AgentState) -> str:
    """
    Checks if the last message had any tool calls and returns "tools" if true.
    Otherwise, returns END, indicating that the conversation should end.
    """
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

app = workflow.compile()
logger.info("LangGraph workflow compiled successfully.")