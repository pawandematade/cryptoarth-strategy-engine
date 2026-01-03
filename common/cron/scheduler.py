"""
Cron Scheduler - Single Entry Point
Centralized scheduler for all cron jobs
"""
import logging
from typing import List, Callable
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler = None

def get_scheduler() -> BackgroundScheduler:
    """Get or create scheduler instance (single instance)"""
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler()
        logger.info("Cron scheduler initialized")
    return _scheduler

def start_scheduler():
    """Start the scheduler"""
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info("Cron scheduler started")

def stop_scheduler():
    """Stop the scheduler"""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown()
        logger.info("Cron scheduler stopped")

def add_job(func: Callable, trigger: CronTrigger, id: str, **kwargs):
    """Add a cron job to the scheduler"""
    scheduler = get_scheduler()
    scheduler.add_job(func, trigger=trigger, id=id, **kwargs)
    logger.info(f"Cron job added: {id}")

