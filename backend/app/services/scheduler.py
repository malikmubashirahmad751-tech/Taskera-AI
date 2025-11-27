import os
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor

from app.core.logger import logger
from app.core.database import supabase

executors = {
    'default': ThreadPoolExecutor(max_workers=3)
}

scheduler = BackgroundScheduler(
    executors=executors,
    job_defaults={
        'coalesce': False,
        'max_instances': 1
    }
)

def run_research_task(query: str):
    """
    Execute a scheduled research task
    """
    logger.info(f"[Scheduler] Running research task: '{query}'")
    
    try:
        from app.impl.tools_agent_impl import duckduckgo_search_wrapper
        
        result = duckduckgo_search_wrapper(query)
        logger.info(f"[Scheduler] Task completed: {query}\nResult: {result[:200]}...")
        
        return result
        
    except Exception as e:
        logger.error(f"[Scheduler] Task failed for '{query}': {e}", exc_info=True)
        return None

def correct_run_date(run_date: datetime) -> datetime:
    """
    Ensure run_date is in the future
    If in the past, schedule for next day at 10:00 AM
    """
    now = datetime.now()
    
    if run_date < now:
        logger.warning(f"[Scheduler] Date {run_date} is in the past, adjusting...")
        run_date = now + timedelta(days=1)
        run_date = run_date.replace(hour=10, minute=0, second=0, microsecond=0)
    
    return run_date

def add_new_task(
    func,
    trigger: str,
    run_date: datetime,
    args: list = None,
    job_id: str = None
) -> dict:
    """
    Add a new scheduled task
    """
    args = args or []
    
    try:
        run_date = correct_run_date(run_date)
        
        job = scheduler.add_job(
            func,
            trigger=trigger,
            run_date=run_date,
            args=args,
            id=job_id,
            replace_existing=True
        )
        
        logger.info(
            f"[Scheduler] Added task '{func.__name__}' for {run_date} (ID: {job.id})"
        )
        
        return {
            "status": "success",
            "job_id": job.id,
            "run_date": run_date.isoformat()
        }
        
    except Exception as e:
        logger.error(f"[Scheduler] Failed to add task: {e}", exc_info=True)
        return {"error": str(e)}

def remove_task(job_id: str) -> bool:
    """
    Remove a scheduled task
    """
    try:
        scheduler.remove_job(job_id)
        logger.info(f"[Scheduler] Removed task: {job_id}")
        return True
        
    except KeyError:
        logger.warning(f"[Scheduler] Task not found: {job_id}")
        return False
        
    except Exception as e:
        logger.error(f"[Scheduler] Error removing task {job_id}: {e}")
        return False

def list_scheduled_tasks() -> list:
    """
    List all scheduled tasks
    """
    try:
        jobs = scheduler.get_jobs()
        
        task_list = []
        for job in jobs:
            task_list.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            })
        
        return task_list
        
    except Exception as e:
        logger.error(f"[Scheduler] Error listing tasks: {e}")
        return []

def start_scheduler():
    """
    Start the background scheduler
    """
    if scheduler.running:
        logger.info("[Scheduler] Already running")
        return
    
    try:
        scheduler.start()
        logger.info("[Scheduler] Started successfully")
        
        jobs = scheduler.get_jobs()
        if jobs:
            logger.info(f"[Scheduler] Loaded {len(jobs)} existing jobs")
        
    except Exception as e:
        logger.error(f"[Scheduler] Failed to start: {e}", exc_info=True)

def shutdown_scheduler():
    """
    Gracefully stop the scheduler
    """
    if not scheduler.running:
        logger.info("[Scheduler] Not running")
        return
    
    try:
        scheduler.shutdown(wait=True)
        logger.info("[Scheduler] Shut down successfully")
        
    except Exception as e:
        logger.error(f"[Scheduler] Shutdown error: {e}")

def get_scheduler_stats() -> dict:
    """
    Get scheduler statistics
    """
    return {
        "running": scheduler.running,
        "jobs_count": len(scheduler.get_jobs()),
        "jobs": [
            {
                "id": job.id,
                "next_run": job.next_run_time.isoformat() 
                    if job.next_run_time else None
            }
            for job in scheduler.get_jobs()
        ]
    }