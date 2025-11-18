import asyncio
from typing import Literal, Optional
from pydantic.v1 import BaseModel, Field
from langchain_core.tools import StructuredTool
from app.core.logger import logger
from app.mcp_client import call_mcp

class ScheduleTaskArgs(BaseModel):
    query: str = Field(description="The research query to schedule.")
    run_date_iso: str = Field(description="ISO datetime when task should run.")

async def _schedule_research_task_proxy(query: str, run_date_iso: str) -> str:
    logger.info("[Scheduler Proxy] Calling MCP for 'schedule_research_task'")
    return await call_mcp("schedule_research_task", {
        "query": query,
        "run_date_iso": run_date_iso
    })

schedule_research_task = StructuredTool.from_function(
    name="schedule_research_task",
    coroutine=_schedule_research_task_proxy,
    args_schema=ScheduleTaskArgs,
    description="Schedules a research task at a specific ISO datetime."
)



Action = Literal["create", "list", "update", "delete"]

class ManageEventsArgs(BaseModel):
    action: Action = Field(description="create, list, update, delete.")
    name: Optional[str] = "Unnamed Event"
    date_expression: Optional[str] = None
    description: Optional[str] = None
    job_id: Optional[str] = None

async def _manage_calendar_events_proxy(
    action: Action,
    name: Optional[str] = "Unnamed Event",
    date_expression: Optional[str] = None,
    description: Optional[str] = None,
    job_id: Optional[str] = None
) -> str:

    logger.info(f"[Scheduler Proxy] Calling MCP for 'manage_calendar_events' action={action}")
    return await call_mcp("manage_calendar_events", {
        "action": action,
        "name": name,
        "date_expression": date_expression,
        "description": description,
        "job_id": job_id
    })

manage_calendar_events = StructuredTool.from_function(
    name="manage_calendar_events",
    coroutine=_manage_calendar_events_proxy,
    args_schema=ManageEventsArgs,
    description="Create, update, delete or list calendar events."
)
