"""
Cron Service - Central Cron Execution Manager

CRITICAL: Every cron execution MUST follow the lifecycle contract:
1. Before start → status = RUNNING, last_run_at = now()
2. On success → status = SUCCESS, last_success_at = now(), error_message = null
3. On failure → status = FAILED, error_message = full error string

No cron may run without visibility.
No silent failures allowed.
"""
import logging
from typing import Callable, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.database import SessionLocal
from app.models import CronMaster, CronStatus, CronTriggeredBy, CronExecutionLog

logger = logging.getLogger(__name__)

# Maximum runtime threshold (1 hour) - crons running longer are considered stuck
MAX_RUNTIME_SECONDS = 3600  # 1 hour


def get_or_create_cron_record(
    db: Session,
    cron_name: str,
    cron_type: str,
    symbol: Optional[str] = None
) -> CronMaster:
    """
    Get or create a cron_master record.
    
    Args:
        db: Database session
        cron_name: Unique cron identifier (e.g., "DAILY_BACKTEST_BTCUSD")
        cron_type: Cron type (e.g., "BACKTEST")
        symbol: Optional symbol if cron is symbol-specific
    
    Returns:
        CronMaster record
    """
    cron = db.query(CronMaster).filter(CronMaster.cron_name == cron_name).first()
    
    if not cron:
        cron = CronMaster(
            cron_name=cron_name,
            cron_type=cron_type,
            symbol=symbol,
            status=CronStatus.SUCCESS,
            triggered_by=CronTriggeredBy.SYSTEM
        )
        db.add(cron)
        db.flush()
        logger.info(f"✅ Created cron_master record: {cron_name}")
    
    return cron


def check_cron_running(db: Session, cron_name: str) -> bool:
    """
    Check if a cron is currently running (prevents parallel execution).
    
    CRITICAL: Also checks for stale RUNNING crons and auto-recovers them.
    If a cron has been RUNNING beyond MAX_RUNTIME_SECONDS (1 hour),
    it is automatically marked as FAILED with recovery message.
    
    Args:
        db: Database session
        cron_name: Cron name to check
    
    Returns:
        True if cron is running (and not stale), False otherwise
    """
    cron = db.query(CronMaster).filter(
        and_(
            CronMaster.cron_name == cron_name,
            CronMaster.status == CronStatus.RUNNING
        )
    ).first()
    
    if not cron:
        return False
    
    # Check if cron is stale (running beyond threshold)
    if cron.last_run_at:
        runtime_seconds = (datetime.now(timezone.utc) - cron.last_run_at).total_seconds()
        
        if runtime_seconds > MAX_RUNTIME_SECONDS:
            # Auto-recover stale cron
            logger.warning(
                f"⚠️ Stale RUNNING cron detected: {cron_name} "
                f"(running for {runtime_seconds:.0f} seconds, threshold: {MAX_RUNTIME_SECONDS}s)"
            )
            
            cron.status = CronStatus.FAILED
            cron.error_message = "Cron stuck — auto recovered"
            
            db.commit()
            db.refresh(cron)
            
            logger.info(f"✅ Auto-recovered stale cron {cron_name} (marked as FAILED)")
            return False  # No longer running after recovery
    
    return True  # Cron is running and not stale


def mark_cron_running(
    db: Session,
    cron_name: str,
    cron_type: str,
    symbol: Optional[str] = None,
    triggered_by: CronTriggeredBy = CronTriggeredBy.SYSTEM
) -> CronMaster:
    """
    Mark cron as RUNNING before execution starts.
    
    CRITICAL: This MUST be called before any cron logic runs.
    
    Args:
        db: Database session
        cron_name: Unique cron identifier
        cron_type: Cron type
        symbol: Optional symbol
        triggered_by: Who triggered the cron (SYSTEM or ADMIN)
    
    Returns:
        Updated CronMaster record
    
    Raises:
        ValueError: If cron is already running (parallel execution prevention)
    """
    # Check if already running
    if check_cron_running(db, cron_name):
        raise ValueError(f"Cron {cron_name} is already running. Cannot start parallel execution.")
    
    # Get or create cron record
    cron = get_or_create_cron_record(db, cron_name, cron_type, symbol)
    
    # Update to RUNNING state
    cron.status = CronStatus.RUNNING
    cron.last_run_at = datetime.now(timezone.utc)
    cron.triggered_by = triggered_by
    cron.error_message = None  # Clear previous error
    
    db.commit()
    db.refresh(cron)
    
    logger.info(f"🔄 Cron {cron_name} marked as RUNNING (triggered_by={triggered_by.value})")
    return cron


def mark_cron_success(
    db: Session,
    cron_name: str,
    error_message: Optional[str] = None
) -> CronMaster:
    """
    Mark cron as SUCCESS after execution completes successfully.
    
    CRITICAL: This MUST be called after successful cron execution.
    
    Args:
        db: Database session
        cron_name: Cron name
        error_message: Optional error message (should be None for success)
    
    Returns:
        Updated CronMaster record
    """
    cron = db.query(CronMaster).filter(CronMaster.cron_name == cron_name).first()
    
    if not cron:
        logger.error(f"❌ Cannot mark success - cron {cron_name} not found")
        return None
    
    cron.status = CronStatus.SUCCESS
    cron.last_success_at = datetime.now(timezone.utc)
    cron.error_message = None  # Clear error message on success
    
    db.commit()
    db.refresh(cron)
    
    logger.info(f"✅ Cron {cron_name} marked as SUCCESS")
    return cron


def mark_cron_failed(
    db: Session,
    cron_name: str,
    error_message: str
) -> CronMaster:
    """
    Mark cron as FAILED after execution fails.
    
    CRITICAL: This MUST be called after failed cron execution.
    No silent failures allowed.
    
    Args:
        db: Database session
        cron_name: Cron name
        error_message: Full error message string
    
    Returns:
        Updated CronMaster record
    """
    cron = db.query(CronMaster).filter(CronMaster.cron_name == cron_name).first()
    
    if not cron:
        logger.error(f"❌ Cannot mark failed - cron {cron_name} not found")
        return None
    
    cron.status = CronStatus.FAILED
    cron.error_message = str(error_message)[:10000]  # Limit error message length
    
    db.commit()
    db.refresh(cron)
    
    logger.error(f"❌ Cron {cron_name} marked as FAILED: {error_message}")
    return cron


def log_execution(
    db: Session,
    cron_name: str,
    triggered_by: CronTriggeredBy,
    started_at: datetime,
    finished_at: Optional[datetime],
    status: CronStatus,
    error_message: Optional[str] = None
) -> CronExecutionLog:
    """
    Log cron execution to execution history.
    
    CRITICAL: Every cron execution MUST be logged here.
    This provides complete execution history.
    
    Args:
        db: Database session
        cron_name: Cron name
        triggered_by: Who triggered the cron
        started_at: Execution start timestamp
        finished_at: Execution finish timestamp (None if still running)
        status: Final status (RUNNING, SUCCESS, FAILED)
        error_message: Error message if failed
    
    Returns:
        Created CronExecutionLog record
    """
    execution_log = CronExecutionLog(
        cron_name=cron_name,
        triggered_by=triggered_by,
        started_at=started_at,
        finished_at=finished_at,
        status=status,
        error_message=error_message[:10000] if error_message else None  # Limit error message length
    )
    
    db.add(execution_log)
    db.flush()
    
    logger.debug(f"📝 Logged execution: {cron_name} - {status.value}")
    return execution_log


def execute_cron(
    cron_name: str,
    cron_type: str,
    cron_function: Callable[[], Any],
    symbol: Optional[str] = None,
    triggered_by: CronTriggeredBy = CronTriggeredBy.SYSTEM
) -> Dict[str, Any]:
    """
    Execute a cron job following the lifecycle contract.
    
    CRITICAL CONTRACT:
    1. Before start → status = RUNNING, last_run_at = now()
    2. On success → status = SUCCESS, last_success_at = now(), error_message = null
    3. On failure → status = FAILED, error_message = full error string
    
    CRITICAL: Every execution is logged to cron_execution_log for history.
    
    Args:
        cron_name: Unique cron identifier
        cron_type: Cron type (e.g., "BACKTEST")
        cron_function: Function to execute (must be callable with no args)
        symbol: Optional symbol
        triggered_by: Who triggered the cron (SYSTEM or ADMIN)
    
    Returns:
        Dict with success status and result/error
    """
    db = SessionLocal()
    started_at = datetime.now(timezone.utc)
    execution_log = None
    
    try:
        # STEP 1: Mark as RUNNING (prevents parallel execution)
        try:
            mark_cron_running(db, cron_name, cron_type, symbol, triggered_by)
        except ValueError as e:
            # Cron is already running
            logger.warning(f"⚠️ {str(e)}")
            
            # Log execution attempt (failed due to already running)
            log_execution(
                db,
                cron_name,
                triggered_by,
                started_at,
                datetime.now(timezone.utc),
                CronStatus.FAILED,
                str(e)
            )
            db.commit()
            
            return {
                "success": False,
                "error": str(e),
                "status": "ALREADY_RUNNING"
            }
        
        # Log execution start (status = RUNNING)
        execution_log = log_execution(
            db,
            cron_name,
            triggered_by,
            started_at,
            None,  # Not finished yet
            CronStatus.RUNNING,
            None
        )
        db.commit()
        
        # STEP 2: Execute cron function
        try:
            result = cron_function()
            finished_at = datetime.now(timezone.utc)
            
            # STEP 3: Mark as SUCCESS
            mark_cron_success(db, cron_name)
            
            # Update execution log with success
            if execution_log:
                execution_log.finished_at = finished_at
                execution_log.status = CronStatus.SUCCESS
                execution_log.error_message = None
                db.commit()
            
            return {
                "success": True,
                "result": result,
                "status": "SUCCESS"
            }
            
        except Exception as e:
            # STEP 3 (FAILURE): Mark as FAILED
            finished_at = datetime.now(timezone.utc)
            error_msg = str(e)
            mark_cron_failed(db, cron_name, error_msg)
            
            # Update execution log with failure
            if execution_log:
                execution_log.finished_at = finished_at
                execution_log.status = CronStatus.FAILED
                execution_log.error_message = error_msg[:10000]  # Limit error message length
                db.commit()
            
            return {
                "success": False,
                "error": error_msg,
                "status": "FAILED"
            }
    
    except Exception as e:
        # Critical error in cron service itself
        finished_at = datetime.now(timezone.utc)
        logger.error(f"❌ Critical error in cron service for {cron_name}: {e}", exc_info=True)
        
        # Try to mark as failed
        try:
            mark_cron_failed(db, cron_name, f"Critical cron service error: {str(e)}")
            
            # Update execution log if it exists
            if execution_log:
                execution_log.finished_at = finished_at
                execution_log.status = CronStatus.FAILED
                execution_log.error_message = f"Critical cron service error: {str(e)}"[:10000]
                db.commit()
        except:
            pass
        
        return {
            "success": False,
            "error": f"Critical cron service error: {str(e)}",
            "status": "CRITICAL_ERROR"
        }
    
    finally:
        db.close()

