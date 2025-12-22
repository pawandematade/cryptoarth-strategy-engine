"""
Strategy Execution Scheduler
Auto scheduler worker that processes running executions.

CRITICAL RULES:
- Runs every 1 minute
- One execution processed at a time
- Lock by execution_id
- Same candle → only one signal
- No nested loops
- No recursive calls
- Exception isolation (one strategy fail ≠ system fail)
"""
import logging
import time
from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.database import SessionLocal
from app.models import StrategyExecution, ExecutionStatus, ExecutionMode
from app.services.signal_service import process_strategy_signal

logger = logging.getLogger(__name__)

# Execution lock (in-memory, single process)
# For multi-process, use Redis or DB-based locking
_execution_locks: set[int] = set()


def get_running_executions(db: Session) -> List[StrategyExecution]:
    """
    Get all running executions.
    
    Args:
        db: Database session
    
    Returns:
        List[StrategyExecution]: List of running executions
    """
    return db.query(StrategyExecution).filter(
        StrategyExecution.status == ExecutionStatus.running
    ).all()


def process_execution(execution: StrategyExecution) -> bool:
    """
    Process a single execution.
    
    CRITICAL: One execution at a time, locked by execution_id.
    
    Args:
        execution: Strategy execution to process
    
    Returns:
        bool: True if processed successfully, False otherwise
    """
    # Check lock
    if execution.id in _execution_locks:
        logger.debug(f"Execution {execution.id} is locked, skipping")
        return False
    
    # Acquire lock
    _execution_locks.add(execution.id)
    
    try:
        db = SessionLocal()
        try:
            # Refresh execution from DB
            db_execution = db.query(StrategyExecution).filter(
                StrategyExecution.id == execution.id
            ).first()
            
            if not db_execution:
                logger.warning(f"Execution {execution.id} not found in DB")
                return False
            
            # Check if still running
            status_val = db_execution.status.value if hasattr(db_execution.status, 'value') else str(db_execution.status)
            if status_val != "running":
                logger.debug(f"Execution {execution.id} is not running (status: {status_val}), skipping")
                return False
            
            # TODO: Get strategy signal from strategy logic
            # For now, this is a placeholder
            # In production, this would:
            # 1. Load strategy payload
            # 2. Evaluate conditions
            # 3. Generate signal (BUY/SELL/EXIT)
            # 4. Get current price
            # 5. Call process_strategy_signal()
            
            # Placeholder: Skip actual signal processing for now
            # This will be implemented when strategy evaluation logic is ready
            logger.debug(f"Processing execution {execution.id} (placeholder)")
            
            return True
            
        finally:
            db.close()
            
    except Exception as e:
        # CRITICAL: Exception isolation - one strategy fail ≠ system fail
        logger.error(f"Error processing execution {execution.id}: {e}", exc_info=True)
        return False
        
    finally:
        # Release lock
        _execution_locks.discard(execution.id)


def scheduler_worker() -> None:
    """
    Scheduler worker that runs every 1 minute.
    
    CRITICAL: Processes one execution at a time.
    """
    logger.info("Scheduler worker started")
    
    db = SessionLocal()
    try:
        # Get all running executions
        executions = get_running_executions(db)
        logger.info(f"Found {len(executions)} running execution(s)")
        
        # Process one by one (FIFO)
        for execution in executions:
            try:
                process_execution(execution)
            except Exception as e:
                # CRITICAL: Exception isolation
                logger.error(f"Error in scheduler processing execution {execution.id}: {e}", exc_info=True)
                continue
        
    except Exception as e:
        logger.error(f"Error in scheduler worker: {e}", exc_info=True)
    finally:
        db.close()


def run_scheduler_loop(interval_seconds: int = 60) -> None:
    """
    Run scheduler in a loop.
    
    Args:
        interval_seconds: Interval between scheduler runs (default: 60 seconds = 1 minute)
    """
    logger.info(f"Scheduler started with interval: {interval_seconds} seconds")
    
    while True:
        try:
            scheduler_worker()
        except Exception as e:
            logger.error(f"Error in scheduler loop: {e}", exc_info=True)
        
        # Wait for next interval
        time.sleep(interval_seconds)

