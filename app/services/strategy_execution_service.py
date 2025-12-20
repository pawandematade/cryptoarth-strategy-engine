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


def activate_strategy_execution(
    db: Session,
    strategy_code: str,
    version: int,
    authorization: str
) -> Dict[str, Any]:
    """
    Activate a specific version of a strategy for execution.
    
    FLOW (STRICT ORDER):
    1. Sync user from auth backend (FAIL FAST if unavailable)
    2. Fetch strategy by strategy_code
    3. Verify strategy ownership (user_id match)
    4. Verify requested version exists in strategy_versions
    5. Start DB transaction with row-level locking
    6. Lock strategy row and existing executions (SELECT FOR UPDATE)
    7. Deactivate existing active execution (if any)
    8. Insert or update strategy_executions row:
       - strategy_id
       - strategy_version
       - status = ACTIVE
       - activated_at = now (UTC)
       - deactivated_at = NULL
    9. Commit transaction
    10. Return success response
    
    IMPORTANT:
    - TEMP strategies are NOT allowed (enforced at API level)
    - Execution must ALWAYS bind to a specific version
    - Only one ACTIVE execution per strategy_id (enforced by DB constraint + row locking)
    - Old active version must be deactivated before new activation
    - Ownership must be verified
    - Use transaction with row-level locking for safety (prevents race conditions)
    - Fail fast if auth backend unavailable
    
    Args:
        db: Database session
        strategy_code: Strategy code (e.g., STRG-ABCD)
        version: Version number to activate
        authorization: Authorization header (Bearer token)
    
    Returns:
        dict: {
            "strategy_code": str,
            "active_version": int,
            "status": str
        }
    
    Raises:
        ValueError: If validation fails, strategy not found, ownership mismatch, or version not found
        requests.exceptions.RequestException: If auth backend unavailable
        IntegrityError: If unique constraint violation occurs (handled and re-raised as ValueError)
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
    
    # 4. Verify requested version exists in strategy_versions
    strategy_version = db.query(StrategyVersion).filter(
        StrategyVersion.strategy_id == strategy.id,
        StrategyVersion.version == version
    ).first()
    
    if not strategy_version:
        raise ValueError(
            f"Strategy version not found: strategy_code={strategy_code}, version={version}"
        )
    
    try:
        # 5 & 6. Start DB transaction with row-level locking
        # Lock the strategy row to prevent concurrent modifications
        locked_strategy = db.query(Strategy).filter(
            Strategy.id == strategy.id
        ).with_for_update().first()
        
        if not locked_strategy:
            raise ValueError(f"Strategy not found after locking: strategy_code={strategy_code}")
        
        # 7. Lock and query existing active execution (if any)
        existing_active = db.query(StrategyExecution).filter(
            StrategyExecution.strategy_id == strategy.id,
            StrategyExecution.status == ExecutionStatus.ACTIVE
        ).with_for_update().first()
        
        if existing_active:
            existing_active.status = ExecutionStatus.INACTIVE
            existing_active.deactivated_at = datetime.now(timezone.utc)
            logger.info(
                f"Deactivated existing execution: strategy_code={strategy_code}, "
                f"previous_version={existing_active.strategy_version}"
            )
        
        # 8. Insert or update strategy_executions row
        execution = db.query(StrategyExecution).filter(
            StrategyExecution.strategy_id == strategy.id,
            StrategyExecution.strategy_version == version
        ).first()
        
        if execution:
            # Update existing execution record
            execution.status = ExecutionStatus.ACTIVE
            execution.activated_at = datetime.now(timezone.utc)
            execution.deactivated_at = None
        else:
            # Create new execution record
            execution = StrategyExecution(
                strategy_id=strategy.id,
                strategy_version=version,
                status=ExecutionStatus.ACTIVE,
                activated_at=datetime.now(timezone.utc),
                deactivated_at=None
            )
            db.add(execution)
        
        # 9. Commit transaction
        db.commit()
        db.refresh(execution)
        
        logger.info(
            f"Strategy execution activated: strategy_code={strategy_code}, "
            f"strategy_id={strategy.id}, version={version}"
        )
        
        # 10. Return success response
        return {
            "strategy_code": strategy_code,
            "active_version": version,
            "status": ExecutionStatus.ACTIVE.value
        }
        
    except IntegrityError as e:
        db.rollback()
        error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
        if 'unique_active_strategy' in error_msg.lower() or 'duplicate entry' in error_msg.lower():
            logger.warning(
                f"Unique constraint violation (concurrent activation prevented): "
                f"strategy_code={strategy_code}, version={version}."
            )
            raise ValueError(
                f"Another activation request for this strategy is in progress. "
                f"Please wait a moment and try again."
            )
        logger.error(f"Database integrity error activating strategy execution: {e}")
        raise ValueError(f"Failed to activate strategy execution: database constraint violation")
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error activating strategy execution: {e}", exc_info=True)
        raise ValueError(f"Failed to activate strategy execution: {str(e)}")


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


def stop_strategy_execution(
    db: Session,
    strategy_code: str,
    authorization: str
) -> Dict[str, Any]:
    """
    Stop a strategy execution permanently (TERMINAL state).
    
    FLOW (STRICT ORDER):
    1. Sync user from auth backend (FAIL FAST if unavailable)
    2. Fetch strategy by strategy_code
    3. Verify strategy ownership (user_id match)
    4. Fetch current execution for strategy
    5. Validate current status is ACTIVE or PAUSED (or already STOPPED for idempotency)
    6. Update execution status to STOPPED
    7. Set deactivated_at timestamp
    8. Commit transaction
    9. Return success response
    
    IMPORTANT:
    - TEMP strategies are NOT allowed (enforced at API level)
    - Only updates execution status (no version changes)
    - STOP is TERMINAL: stopped executions can NEVER be resumed
    - Idempotent: if already stopped, returns success
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
    
    # 5. Validate current status (idempotent: if already stopped, return success)
    if execution.status == ExecutionStatus.STOPPED:
        logger.info(
            f"Execution already stopped (idempotent): strategy_code={strategy_code}, "
            f"execution_id={execution.id}"
        )
        return {
            "strategy_code": strategy_code,
            "status": ExecutionStatus.STOPPED.value
        }
    
    # STOP is allowed only from ACTIVE or PAUSED states
    if execution.status not in [ExecutionStatus.ACTIVE, ExecutionStatus.PAUSED]:
        raise ValueError(
            f"Cannot stop execution with status '{execution.status.value}'. "
            f"Only ACTIVE or PAUSED executions can be stopped."
        )
    
    try:
        # Store previous status for logging
        previous_status = execution.status.value
        
        # 6 & 7. Update execution status to STOPPED and set deactivated_at
        execution.status = ExecutionStatus.STOPPED
        execution.deactivated_at = datetime.now(timezone.utc)
        
        # 8. Commit transaction
        db.commit()
        db.refresh(execution)
        
        logger.info(
            f"Strategy execution stopped (TERMINAL): strategy_code={strategy_code}, "
            f"strategy_id={strategy.id}, execution_id={execution.id}, "
            f"previous_status={previous_status}"
        )
        
        # 9. Return success response
        return {
            "strategy_code": strategy_code,
            "status": ExecutionStatus.STOPPED.value
        }
        
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Database integrity error stopping strategy execution: {e}")
        raise ValueError(f"Failed to stop strategy execution: database constraint violation")
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error stopping strategy execution: {e}", exc_info=True)
        raise ValueError(f"Failed to stop strategy execution: {str(e)}")
