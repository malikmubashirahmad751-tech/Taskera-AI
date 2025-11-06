import os
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from supabase import create_client, Client
from dotenv import load_dotenv
from app.core.memory_manager import clear_expired_sessions
from app.core.logger import logger

from app.agents.tools_agent import search_tool 

scheduler = BackgroundScheduler()

load_dotenv()

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

if not supabase_url or not supabase_key:
    raise ValueError("Supabase URL and Key must be set in your .env file")

try:
    supabase: Client = create_client(supabase_url, supabase_key)
except Exception as e:
    logger.error(f"Error creating Supabase client: {e}")
    supabase = None

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "logs")
os.makedirs(LOG_DIR, exist_ok=True)


def run_research_task(query: str):
    """
    Run a scheduled research task.
    This now calls the search_tool directly to avoid circular imports.
    """
    logger.info(f"[Scheduler] Running scheduled research task: '{query}'")
    try:
        
        result = search_tool.invoke(query)
        logger.info(f"[Scheduler] Task completed successfully:\n{result}")
        
        
    except Exception as e:
        logger.error(f"[Scheduler] Task for query '{query}' failed: {e}", exc_info=True)


def correct_run_date(run_date: datetime) -> datetime:
    """
    Ensure run_date is always in the *future* relative to now.
    If given date is in the past, shift it to next available day at 10:00 AM.
    """
    now = datetime.now()
    if run_date < now:
        run_date = now + timedelta(days=1)
        run_date = run_date.replace(hour=10, minute=0, second=0, microsecond=0)
    return run_date


def add_new_task(func, trigger: str, run_date: datetime, args: list = None, job_id: str = None):
    """Add a new task to APScheduler."""
    args = args or []
    try:
        run_date = correct_run_date(run_date)
        job = scheduler.add_job(
            func,
            trigger,
            run_date=run_date,
            args=args,
            id=job_id if job_id else None,
            replace_existing=True
        )
        logger.info(f"[Scheduler] Task '{func.__name__}' scheduled for {run_date} (job_id={job.id})")
        return job
    except Exception as e:
        logger.error(f"[Scheduler] Failed to add task '{func.__name__}': {e}", exc_info=True)
        return None


def remove_task(job_id: str):
    """Remove a task from the scheduler by its ID."""
    try:
        scheduler.remove_job(job_id)
        logger.info(f"[Scheduler] Task '{job_id}' removed from scheduler.")
    except KeyError:
        logger.warning(f"[Scheduler] Task '{job_id}' not found.")
    except Exception as e:
        logger.error(f"[Scheduler] Error removing task '{job_id}': {e}", exc_info=True)


def start_scheduler():
    """Start the background scheduler and recurring jobs safely."""
    if scheduler.running:
        logger.info("[Scheduler] Scheduler already running.")
        return

    try:
        scheduler.add_job(
            func=clear_expired_sessions,
            trigger='interval',
            minutes=30,
            id='clear_expired_sessions_job',
            replace_existing=True
        )
        scheduler.start()
        logger.info("[Scheduler] Started successfully with recurring cleanup job.")
    except Exception as e:
        logger.error(f"[Scheduler] Failed to start: {e}", exc_info=True)


def shutdown_scheduler():
    """Gracefully stop the scheduler (on app shutdown)."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Stopped cleanly.")
    else:
        logger.info("[Scheduler] Scheduler was not running.")