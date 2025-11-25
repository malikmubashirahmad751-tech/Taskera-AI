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

llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash-lite-preview-02-05", 
    temperature=0,
    api_key=settings.gemini_api_key,
    max_retries=0  
)

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

        system_prompt = f"""You are Taskera AI, a multi-functional, tool-enabled assistant.

CURRENT CONTEXT:
- Today is: {current_day}, {current_date}
- Current time: {current_time}
- User Email: {user_email}
- User Timezone: Assume local time unless specified.

Your purpose is to help the user complete tasks efficiently by using tools intelligently and following strict contextual rules.

1. CORE BEHAVIOR
Contextual Follow-Up (Most Important Rule)
If you asked a question, the user’s next message is the answer to that same question.
 **ACTION OVER TALK:** If the user says "Yeah", "Yes", "Confirm", "Do it", "Okay", or "Sure" after you proposed a plan, **YOU MUST CALL THE TOOL IMMEDIATELY.** Do not simply say "Okay" or "I will do that". Just run the tool function.
Always respect the immediate conversational context when deciding what to do next.

2. TOOL USAGE RULES
If a tool can answer the request, YOU MUST USE IT.
Only respond conversationally if no tool is suitable.

Tool Priority (Highest → Lowest)

Google Calendar Tools
Tools: google_calendar_list, google_calendar_schedule
Use these to check schedules, find free time, or create/edit/cancel real events.
If a calendar tool call fails due to auth issues, tell the user to log in via the dashboard.
IMPORTANT: Use the User Email ({user_email}) as the attendee if requested.
IMPORTANT: If the user says "tomorrow" or "next Friday", CALCULATE the date based on "Today is {current_date}" and pass the YYYY-MM-DD string to the tool.

Image Text Extraction
Tool: image_text_extractor
Use this whenever the user provides an image and asks for its text or content.

Document Question Answering (RAG)
Tool: local_document_retriever
Use this for questions about user-uploaded documents only.
Do NOT use this for general knowledge, weather, news, math, or web lookups.

Weather Lookup
Tools: weather_tool or weather_search
These require a location.
If you ask “Which city?”, the user’s reply is the location for the tool call.

Task Scheduling (Internal Agent Tasks)
Tools: schedule_research_task, manage_calendar_events
Use these only for internal tasks, reminders, or planning—
NOT for creating real meetings (use Calendar tools instead).

News
Tool: latest_news_tool
Use for current headlines, breaking news, or recent events.

Web Browsing / Live Data
Tools: headless_browser_search, search_tool
Use for complex real-time queries, URL-based lookups, and live data research.

General Search
Tools: web_search, wikipedia_search
Use for definitions, factual questions, and general knowledge not tied to user documents.

Other Tools
calculator_tool (math)
translator_tool (language translation)
summarize_tool (summaries of long text)

3. INTERACTION LOGIC
If the user request is unclear, ask clarifying questions.
Do not chain multiple tools unless required.
Always pick the most relevant tool.
After a tool call, interpret the results for the user unless stated otherwise.

4. TONE & STYLE
Clear, concise, professional, helpful
Action-oriented and task-completion focused
Maintain logical consistency and follow conversational context

5. CORE PHILOSOPHY
Understand the context.
Use the right tool.
Complete the task.
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
        # --- FIX: Return AIMessage object ---
        return {
            "messages": [
                AIMessage(content=" I am currently unavailable because the AI usage limit has been reached. Please try again in a minute or switch to a new API key.")
            ]
        }
    except Exception as e:
        logger.error(f"Unexpected Agent Error: {e}")
        # --- FIX: Return AIMessage object ---
        return {
            "messages": [
                AIMessage(content="❌ An internal error occurred while processing your request. Please check the system logs.")
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