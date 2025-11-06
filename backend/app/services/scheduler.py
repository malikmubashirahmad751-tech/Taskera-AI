import os
from datetime import datetime, timedelta
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from supabase import create_client, Client
from dotenv import load_dotenv
from app.core.session_manager import clear_expired_sessions

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()


load_dotenv()

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

if not supabase_url or not supabase_key:
    raise ValueError("Supabase URL and Key must be set in your .env file")

try:
    supabase: Client = create_client(supabase_url, supabase_key)
except Exception as e:
    print(f"Error creating Supabase client: {e}")

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

def run_research_task(query: str):
    """Run a scheduled research task safely."""
    from app.core.agent import research_query
    logger.info(f"Running scheduled task for query: '{query}'")
    try:
        result = research_query(query, user_id="scheduled_task")
        logger.info(f"Scheduled Task Result at {datetime.now()}:\n{result}")
    except Exception as e:
        logger.error(f"Task for query '{query}' failed: {e}")


def correct_run_date(run_date: datetime) -> datetime:
    """
    Ensure the run_date is always in the *future* relative to the current system time.
    """
    now = datetime.now()

    if run_date.year < now.year:
        run_date = run_date.replace(year=now.year)

    if run_date < now:
        try:
            run_date = run_date.replace(year=now.year + 1)
        except ValueError:
            run_date = now + timedelta(days=1)

    if run_date < now:
        run_date = now + timedelta(days=1)
        run_date = run_date.replace(hour=10, minute=0, second=0, microsecond=0)

    return run_date


def add_new_task(func, trigger: str, run_date: datetime, args: list = None, job_id: str = None):
    """
    Add a new task to the scheduler. 
    This function no longer handles Supabase logic.
    """
    args = args or []
    try:
        run_date = correct_run_date(run_date)

        job = scheduler.add_job(
            func,
            trigger,
            run_date=run_date,
            args=args,
            id=job_id if job_id else None,
        )

        logger.info(f"Task '{func.__name__}' scheduled for {run_date} (job_id={job.id})")

    except Exception as e:
        logger.error(f" Failed to add new task: {e}", exc_info=True)

def remove_task(job_id: str):
    """Removes a job from the scheduler by its ID."""
    try:
        scheduler.remove_job(job_id)
        logger.info(f" Task with ID '{job_id}' removed from scheduler.")
    except KeyError:
        logger.warning(f" Failed to remove task with ID '{job_id}': Job not found.")
    except Exception as e:
        logger.error(f" Error removing task '{job_id}': {e}")

def start_scheduler():
    """Start the background scheduler and add recurring jobs."""
    if not scheduler.running:
        scheduler.add_job(
            func=clear_expired_sessions,
            trigger='interval',
            minutes=30,
            id='clear_expired_sessions_job'
        )
        scheduler.start()
        logger.info(" Scheduler started successfully with recurring jobs.")

def shutdown_scheduler():
    """Gracefully stop scheduler (call this on app shutdown)."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info(" Scheduler stopped cleanly.")
    else:
        logger.info("Scheduler was not running.")