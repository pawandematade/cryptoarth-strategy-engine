"""
Strategy Execution Service
Handles activation, pausing, and resuming of strategy executions.

IMPORTANT: Execution must ALWAYS bind to a specific version (strategy_code + version).
Only one ACTIVE execution per strategy_id is allowed.
"""
import logging
from typing import Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from app.models import Strategy, StrategyVersion, StrategyExecution, ExecutionStatus, User
from app.services.user_sync_service import get_or_sync_user

logger = logging.getLogger(__name__)


def pause_strategy_execution(
    db: Session,
    strategy_code: str,
    authorization: str
) -> Dict[str, Any]:
    """
    Pause an active strategy execution.
    
    FLOW (STRICT ORDER):
    1. Sync user from auth backend (FAIL FAST if unavailable)
    2. Fetch strategy by strategy_code
    3. Verify strategy ownership (user_id match)
    4. Fetch current execution for strategy
    5. Validate current status is ACTIVE (or already PAUSED for idempotency)
    6. Update execution status to PAUSED
    7. Set deactivated_at timestamp
    8. Commit transaction
    9. Return success response
    
    IMPORTANT:
    - TEMP strategies are NOT allowed (enforced at API level)
    - Only updates execution status (no version changes)
    - Idempotent: if already paused, returns success
    - Ownership must be verified
    - Use transaction for safety (rollback on error)
    - Fail fast if auth backend unavailable
    
    Args:
        db: Database session
        strategy_code: Strategy code (e.g., STRG-ABCD)
        authorization: Authorization header (Bearer token)
    
    Returns:
        dict: {
            "strategy_code": str,
            "status": str
        }
    
    Raises:
        ValueError: If validation fails, strategy not found, ownership mismatch, or execution not found
        requests.exceptions.RequestException: If auth backend unavailable
    """
    # 1. Sync user from auth backend (FAIL FAST if unavailable)
    user = get_or_sync_user(db, external_user_id=None, authorization=authorization)
    if not user:
        raise ValueError("Failed to sync user from auth backend")
    
    # 2. Fetch strategy by strategy_code
    strategy = db.query(Strategy).filter(Strategy.strategy_code == strategy_code).first()
    if not strategy:
        raise ValueError(f"Strategy not found: strategy_code={strategy_code}")
    
    # 3. Verify strategy ownership (user_id match)
    if strategy.user_id != user.id:
        raise ValueError(f"Strategy ownership mismatch: strategy belongs to different user")
    
    # 4. Fetch current execution for strategy
    execution = db.query(StrategyExecution).filter(
        StrategyExecution.strategy_id == strategy.id
    ).order_by(StrategyExecution.created_at.desc()).first()
    
    if not execution:
        raise ValueError(f"Execution not found for strategy: strategy_code={strategy_code}")
    
    # 5. Validate current status (idempotent: if already paused, return success)
    if execution.status == ExecutionStatus.PAUSED:
        logger.info(
            f"Execution already paused (idempotent): strategy_code={strategy_code}, "
            f"execution_id={execution.id}"
        )
        return {
            "strategy_code": strategy_code,
            "status": ExecutionStatus.PAUSED.value
        }
    
    if execution.status != ExecutionStatus.ACTIVE:
        raise ValueError(
            f"Cannot pause execution with status '{execution.status.value}'. "
            f"Only ACTIVE executions can be paused."
        )
    
    try:
        # 6 & 7. Update execution status to PAUSED and set deactivated_at
        execution.status = ExecutionStatus.PAUSED
        execution.deactivated_at = datetime.now(timezone.utc)
        
        # 8. Commit transaction
        db.commit()
        db.refresh(execution)
        
        logger.info(
            f"Strategy execution paused: strategy_code={strategy_code}, "
            f"strategy_id={strategy.id}, execution_id={execution.id}"
        )
        
        # 9. Return success response
        return {
            "strategy_code": strategy_code,
            "status": ExecutionStatus.PAUSED.value
        }
        
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Database integrity error pausing strategy execution: {e}")
        raise ValueError(f"Failed to pause strategy execution: database constraint violation")
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error pausing strategy execution: {e}", exc_info=True)
        raise ValueError(f"Failed to pause strategy execution: {str(e)}")


def resume_strategy_execution(
    db: Session,
    strategy_code: str,
    authorization: str
) -> Dict[str, Any]:
    """
    Resume a paused strategy execution.
    
    FLOW (STRICT ORDER):
    1. Sync user from auth backend (FAIL FAST if unavailable)
    2. Fetch strategy by strategy_code
    3. Verify strategy ownership (user_id match)
    4. Fetch current execution for strategy
    5. Validate current status is PAUSED (or already ACTIVE for idempotency)
    6. Update execution status to ACTIVE
    7. Set activated_at timestamp
    8. Commit transaction
    9. Return success response
    
    IMPORTANT:
    - TEMP strategies are NOT allowed (enforced at API level)
    - Only updates execution status (no version changes)
    - Idempotent: if already active, returns success
    - Ownership must be verified
    - Use transaction for safety (rollback on error)
    - Fail fast if auth backend unavailable
    
    Args:
        db: Database session
        strategy_code: Strategy code (e.g., STRG-ABCD)
        authorization: Authorization header (Bearer token)
    
    Returns:
        dict: {
            "strategy_code": str,
            "status": str
        }
    
    Raises:
        ValueError: If validation fails, strategy not found, ownership mismatch, or execution not found
        requests.exceptions.RequestException: If auth backend unavailable
    """
    # 1. Sync user from auth backend (FAIL FAST if unavailable)
    user = get_or_sync_user(db, external_user_id=None, authorization=authorization)
    if not user:
        raise ValueError("Failed to sync user from auth backend")
    
    # 2. Fetch strategy by strategy_code
    strategy = db.query(Strategy).filter(Strategy.strategy_code == strategy_code).first()
    if not strategy:
        raise ValueError(f"Strategy not found: strategy_code={strategy_code}")
    
    # 3. Verify strategy ownership (user_id match)
    if strategy.user_id != user.id:
        raise ValueError(f"Strategy ownership mismatch: strategy belongs to different user")
    
    # 4. Fetch current execution for strategy
    execution = db.query(StrategyExecution).filter(
        StrategyExecution.strategy_id == strategy.id
    ).order_by(StrategyExecution.created_at.desc()).first()
    
    if not execution:
        raise ValueError(f"Execution not found for strategy: strategy_code={strategy_code}")
    
    # 5. Validate current status (idempotent: if already active, return success)
    if execution.status == ExecutionStatus.ACTIVE:
        logger.info(
            f"Execution already active (idempotent): strategy_code={strategy_code}, "
            f"execution_id={execution.id}"
        )
        return {
            "strategy_code": strategy_code,
            "status": ExecutionStatus.ACTIVE.value
        }
    
    if execution.status != ExecutionStatus.PAUSED:
        raise ValueError(
            f"Cannot resume execution with status '{execution.status.value}'. "
            f"Only PAUSED executions can be resumed."
        )
    
    try:
        # 6 & 7. Update execution status to ACTIVE and set activated_at
        execution.status = ExecutionStatus.ACTIVE
        execution.activated_at = datetime.now(timezone.utc)
        execution.deactivated_at = None  # Clear deactivated_at when resuming
        
        # 8. Commit transaction
        db.commit()
        db.refresh(execution)
        
        logger.info(
            f"Strategy execution resumed: strategy_code={strategy_code}, "
            f"strategy_id={strategy.id}, execution_id={execution.id}"
        )
        
        # 9. Return success response
        return {
            "strategy_code": strategy_code,
            "status": ExecutionStatus.ACTIVE.value
        }
        
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Database integrity error resuming strategy execution: {e}")
        raise ValueError(f"Failed to resume strategy execution: database constraint violation")
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error resuming strategy execution: {e}", exc_info=True)
        raise ValueError(f"Failed to resume strategy execution: {str(e)}")
