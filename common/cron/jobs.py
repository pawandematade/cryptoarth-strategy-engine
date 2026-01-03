"""
Cron Jobs Definitions
All scheduled jobs defined here
"""
import logging
from apscheduler.triggers.cron import CronTrigger
from common.cron.scheduler import add_job

logger = logging.getLogger(__name__)

def setup_cron_jobs():
    """
    Setup all cron jobs
    Called once at application startup
    """
    # Example: Add your cron jobs here
    # add_job(
    #     func=your_function,
    #     trigger=CronTrigger(hour=0, minute=0),  # Daily at midnight
    #     id="daily_job"
    # )
    
    logger.info("Cron jobs setup complete")

