import asyncio
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.core.database import supabase
from app.core.logger import logger
from app.impl.tools_agent_impl import duckduckgo_search_wrapper

scheduler = AsyncIOScheduler()

async def process_research_tasks():
    """
    Polls Supabase for 'pending' research events that are due.
    Executes search and updates description with results.
    """
    if not supabase:
        logger.debug("[Scheduler] Supabase not available, skipping task processing")
        return

    try:
        now_utc = datetime.now(timezone.utc)
        now_iso = now_utc.isoformat()
        
        logger.debug(f"[Scheduler] Checking for tasks due before {now_iso}")
        
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: supabase.table("events")
            .select("*")
            .eq("status", "pending")
            .lte("start_time", now_iso)
            .ilike("title", "Research Task:%")
            .order("start_time", desc=False)
            .limit(10)
            .execute()
        )

        tasks = response.data if response.data else []
        
        if not tasks:
            logger.debug("[Scheduler] No due research tasks found")
            return

        logger.info(f"[Scheduler] Found {len(tasks)} due research tasks to process")

        for task in tasks:
            task_id = task.get('id')
            task_title = task.get('title', '')
            user_id = task.get('user_id', 'unknown')
            
            query = task_title.replace("Research Task:", "").strip()
            
            if not query:
                logger.warning(f"[Scheduler] Task {task_id} has empty query, skipping")
                try:
                    await loop.run_in_executor(
                        None,
                        lambda: supabase.table("events").update({
                            "status": "failed",
                            "description": "Failed: Empty research query"
                        }).eq("id", task_id).execute()
                    )
                except Exception as e:
                    logger.error(f"[Scheduler] Failed to update task {task_id}: {e}")
                continue
            
            logger.info(f"[Scheduler] Processing task {task_id} for user {user_id}: '{query}'")
            
            try:
                search_result = await loop.run_in_executor(
                    None,
                    duckduckgo_search_wrapper,
                    query
                )
                
                if search_result and len(search_result) > 0:
                    summary = search_result[:2000]  
                    if len(search_result) > 2000:
                        summary += "\n\n[Results truncated for brevity]"
                    
                    status_message = "Research completed successfully"
                else:
                    summary = "No results found for this query"
                    status_message = "Research completed but no results found"
                
                existing_desc = task.get('description', '')
                timestamp = now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')
                
                new_description = f"""{existing_desc}

---
**Research Results** (Executed: {timestamp})

{summary}

---
Status: {status_message}
"""
                
                update_response = await loop.run_in_executor(
                    None,
                    lambda: supabase.table("events").update({
                        "description": new_description,
                        "status": "completed"
                    }).eq("id", task_id).execute()
                )
                
                if update_response.data:
                    logger.info(f"[Scheduler] Task {task_id} completed successfully")
                else:
                    logger.warning(f"[Scheduler] Task {task_id} update returned no data")
                
            except Exception as task_error:
                logger.error(f"[Scheduler] Task {task_id} failed with error: {task_error}", exc_info=True)
                
                try:
                    error_message = str(task_error)[:500]  
                    await loop.run_in_executor(
                        None,
                        lambda: supabase.table("events").update({
                            "status": "failed",
                            "description": f"Failed: {error_message}\n\nOriginal description:\n{task.get('description', '')}"
                        }).eq("id", task_id).execute()
                    )
                    
                    logger.info(f"[Scheduler] Marked task {task_id} as failed")
                    
                except Exception as update_error:
                    logger.error(f"[Scheduler] Failed to update task status for {task_id}: {update_error}")

    except ConnectionResetError as conn_error:
        logger.warning(f"[Scheduler] Connection reset by remote host. Will retry next cycle. Error: {conn_error}")
        
    except Exception as loop_error:
        logger.error(f"[Scheduler] Critical error in task processing loop: {loop_error}", exc_info=True)

async def cleanup_old_completed_tasks():
    """
    Periodically clean up old completed/failed tasks to prevent database bloat
    """
    if not supabase:
        return
    
    try:
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: supabase.table("events")
            .delete()
            .in_("status", ["completed", "failed"])
            .lt("start_time", cutoff_date)
            .execute()
        )
        
        if response.data:
            logger.info(f"[Scheduler] Cleaned up {len(response.data)} old tasks")
            
    except Exception as e:
        logger.error(f"[Scheduler] Cleanup error: {e}")

def start_scheduler():
    """Start the background scheduler"""
    if scheduler.running:
        logger.warning("[Scheduler] Already running")
        return
    
    try:
        scheduler.add_job(
            process_research_tasks,
            trigger=IntervalTrigger(seconds=60),
            id="process_research_tasks",
            name="Process Due Research Tasks",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=30
        )
        
        scheduler.add_job(
            cleanup_old_completed_tasks,
            trigger=IntervalTrigger(hours=24),
            id="cleanup_old_tasks",
            name="Cleanup Old Tasks",
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )
        
        scheduler.start()
        logger.info("Background Scheduler Started (Checking every 60s)")
        
    except Exception as e:
        logger.error(f"[Scheduler] Failed to start: {e}", exc_info=True)
        raise

def shutdown_scheduler():
    """Gracefully shutdown the scheduler"""
    if scheduler.running:
        try:
            scheduler.shutdown(wait=True)
            logger.info("Scheduler shut down gracefully")
        except Exception as e:
            logger.error(f"[Scheduler] Shutdown error: {e}")
    else:
        logger.info("[Scheduler] Not running, nothing to shut down")