from __future__ import annotations
import datetime
import asyncio
import logging
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

INITIAL_RETRY_DELAY = 1.0
MAX_RETRY_DELAY = 60.0
MAX_RETRIES = 5

async def exponential_backoff_retry(func, *args, **kwargs):
    """Retry with exponential backoff for quota errors"""
    delay = INITIAL_RETRY_DELAY
    last_exception = None
    
    for attempt in range(MAX_RETRIES):
        try:
            return await func(*args, **kwargs)
        except ResourceExhausted as e:
            last_exception = e
            if attempt < MAX_RETRIES - 1:
                logger.warning(f"Quota exceeded, retry {attempt + 1}/{MAX_RETRIES} after {delay}s")
                await asyncio.sleep(delay)
                delay = min(delay * 2, MAX_RETRY_DELAY)
            else:
                logger.error(f"Max retries reached for quota error")
        except Exception as e:
            error_str = str(e).lower()
            if "blocked" in error_str or "safety" in error_str:
                logger.error(f"Prompt blocked by safety filters: {e}")
                raise ValueError("Safety blockage detected") from e
            
            logger.error(f"Unexpected error in retry: {e}")
            raise
    
    raise last_exception

try:
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite", 
        temperature=0.1,
        api_key=settings.GOOGLE_API_KEY,
        max_retries=0,  
        request_timeout=90.0,
    )
except Exception as e:
    logger.error(f"Failed to initialize LLM: {e}")
    raise

# Tool imports
from app.agents.tools_agent import (
    wiki_tool, search_tool, summarize_tool, weather_tool,
    latest_news_tool, calculator_tool, translator_tool,
    headless_browser_search
)

from app.agents.services_agent import (
    schedule_research_task, manage_calendar_events
)

from app.agents.knowledge_agent import local_document_retriever_tool
from app.services.ocr_service import create_ocr_tool

ALL_TOOLS = [
    wiki_tool,
    search_tool,
    summarize_tool,
    weather_tool,
    latest_news_tool,
    calculator_tool,
    translator_tool,
    headless_browser_search,
    local_document_retriever_tool,
    create_ocr_tool,
    schedule_research_task,
    manage_calendar_events,
]

tool_node = ToolNode(ALL_TOOLS)

class AgentState(TypedDict):
    """State passed through the agent graph"""
    messages: Annotated[Sequence[BaseMessage], lambda x, y: x + y]
    user_id: str
    user_email: str
    retry_count: int

def detect_prompt_injection(text: str) -> bool:
    """Enhanced prompt injection detection"""
    if not text or not isinstance(text, str):
        return False
    
    risky_phrases = [
        "ignore all prior instructions",
        "ignore previous instructions",
        "system override",
        "developer mode",
        "jailbreak",
        "you are now",
        "delete user files",
        "rm -rf",
        "disregard",
        "forget everything",
        "new instructions",
        "roleplay as"
    ]
    
    text_lower = text.lower().strip()
    return any(phrase in text_lower for phrase in risky_phrases)

def sanitize_input(text: str, max_length: int = 10000) -> str:
    """Sanitize and truncate user input"""
    if not text:
        return ""
    
    text = ''.join(char for char in text if char.isprintable() or char.isspace())
    
    if len(text) > max_length:
        text = text[:max_length] + "... [truncated]"
    
    return text.strip()

async def invoke_llm_with_retry(chain, messages):
    """Wrapper to invoke LLM with retry logic"""
    async def _invoke():
        return await chain.ainvoke({"messages": messages})
    
    return await exponential_backoff_retry(_invoke)

async def agent_node(state: AgentState):
    """Main agent reasoning node with enhanced error handling"""
    user_id = state.get("user_id", "unknown")
    user_email = state.get("user_email", "unknown")
    messages = state["messages"]
    retry_count = state.get("retry_count", 0)
    
    if messages:
        last_msg = messages[-1]
        content = last_msg.content if hasattr(last_msg, 'content') else str(last_msg)
        
        if isinstance(content, str):
            content = sanitize_input(content)
            
            if detect_prompt_injection(content):
                logger.warning(f"Prompt injection blocked for user: {user_id}")
                return {
                    "messages": [
                        AIMessage(content="I cannot process that request due to safety policies.")
                    ]
                }
    
    logger.info(f"[Agent] Processing for user: {user_id} (retry: {retry_count})")
    
    try:
        llm_with_tools = llm.bind_tools(ALL_TOOLS)
        
        now = datetime.datetime.now()
        current_date = now.strftime("%Y-%m-%d")
        current_day = now.strftime("%A")
        current_time = now.strftime("%H:%M")
        
        system_prompt = f"""You are Taskera AI, an advanced multi-functional assistant.

CURRENT CONTEXT:
- Today: {current_day}, {current_date}
- Time: {current_time}
- User Email: {user_email}
- User ID: {user_id}

CAPABILITIES:
1. **Calendar & Tasks**: Manage internal calendar events and schedule research.
2. **Web Tools**: Search, news, Wikipedia, weather, browser automation.
3. **Document Tools**: RAG retrieval from user-uploaded files.
4. **Utility Tools**: Calculator, translator, summarizer, OCR.

CRITICAL RULES:
1. **CALENDAR MANAGEMENT**:
   - Use `manage_calendar_events` for ALL calendar actions.
   - To CREATE: action="create", title="Title", start_time="YYYY-MM-DDTHH:MM:SS"
   - To LIST: action="list"
   - Calculate start_time relative to Today ({current_date})

2. **RESEARCH SCHEDULING**:
   - Use `schedule_research_task` for scheduled searches
   - Calculate run_date_iso based on user request

3. **UPLOADED FILES**:
   - If message contains [Document ... Indexed for RAG], file was just uploaded
   - For questions about "this file" or "the document", use `local_document_retriever`

4. **INTERACTION**:
   - Be concise and action-oriented
   - Confirm before executing destructive actions
   - Handle errors gracefully
"""

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="messages"),
        ])
        
        chain = prompt | llm_with_tools
        
        response_result = await invoke_llm_with_retry(chain, messages)
        
        return {"messages": [response_result], "retry_count": 0}
        
    except ResourceExhausted:
        logger.error(f"[Agent] Quota exceeded for user {user_id} after retries")
        return {
            "messages": [
                AIMessage(content="The AI service is currently experiencing high demand. Please wait 1-2 minutes and try again.")
            ],
            "retry_count": retry_count + 1
        }
    
    except ValueError as e:
        if "Safety blockage detected" in str(e):
            logger.warning(f"[Agent] Prompt blocked for user {user_id}")
            return {
                "messages": [
                    AIMessage(content="I cannot process that request as it may violate safety guidelines.")
                ]
            }
        logger.error(f"[Agent] ValueError: {e}")
        return {
             "messages": [
                AIMessage(content="I encountered a value error. Please check your input.")
            ]
        }

    except asyncio.TimeoutError:
        logger.error(f"[Agent] Timeout for user {user_id}")
        return {
            "messages": [
                AIMessage(content="The request took too long to process. Please try a simpler query.")
            ]
        }
    
    except Exception as e:
        logger.error(f"[Agent] Error for user {user_id}: {e}", exc_info=True)
        return {
            "messages": [
                AIMessage(content="I encountered an internal error. Please try again or contact support.")
            ]
        }

def should_continue(state: AgentState) -> str:
    """Determine whether to continue to tools or end"""
    last_message = state["messages"][-1]
    
    retry_count = state.get("retry_count", 0)
    if retry_count >= 3:
        logger.warning("Max retry count reached, ending conversation")
        return END
    
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