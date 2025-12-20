"""
Strategy Execution Service
Handles activation of strategy versions for execution.

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
    # get_or_sync_user will call auth backend API and sync user to local DB
    # This will raise exception if auth backend is unavailable
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
        # This ensures only one transaction can modify executions for this strategy at a time
        locked_strategy = db.query(Strategy).filter(
            Strategy.id == strategy.id
        ).with_for_update().first()
        
        if not locked_strategy:
            raise ValueError(f"Strategy not found after locking: strategy_code={strategy_code}")
        
        # 7. Lock and query existing active execution (if any)
        # SELECT FOR UPDATE locks the rows, preventing concurrent access
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
        # Check if execution record already exists for this strategy_id + version
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
        # The unique constraint will catch any race condition that somehow bypassed the lock
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
        # Check if it's a unique constraint violation
        error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
        if 'unique_active_strategy' in error_msg.lower() or 'duplicate entry' in error_msg.lower():
            logger.warning(
                f"Unique constraint violation (concurrent activation prevented): "
                f"strategy_code={strategy_code}, version={version}. "
                f"This should be rare with row locking, but constraint caught it."
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
