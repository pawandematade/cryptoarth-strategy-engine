"""
Strategy Execution Service
Handles activation, pausing, and resuming of strategy executions.

IMPORTANT: Execution must ALWAYS bind to a specific version (strategy_code + version).
Only one ACTIVE execution per strategy_id is allowed.

CRITICAL: All strategy activate/deploy operations must also call auth backend API.
"""
import logging
import requests
from typing import Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from app.models import Strategy, StrategyVersion, StrategyExecution, ExecutionStatus, User
from app.services.user_sync_service import get_or_sync_user
from app.config import AUTH_BACKEND_URL

logger = logging.getLogger(__name__)


def deploy_strategy_to_auth_backend(
    strategy_code: str,
    authorization: str,
    is_active: bool = True
) -> bool:
    """
    Deploy/activate strategy in auth backend database via API.
    
    CRITICAL: MUST use AUTH_BACKEND_URL, NEVER STRATEGY_ENGINE_BASE_URL.
    This ensures strategy is activated in production database.
    
    Args:
        strategy_code: Strategy code (e.g., STRG-ABCD)
        authorization: Authorization header (Bearer token)
        is_active: True to activate, False to deactivate
    
    Returns:
        bool: True if successful, False otherwise (logs error but doesn't raise)
    
    Note: This is a non-blocking call - if auth backend is unavailable,
    we log the error but don't fail the local activation.
    """
    try:
        # CRITICAL: Use AUTH_BACKEND_URL for all /auth/ API calls
        # Use deploy endpoint if available, otherwise use activate endpoint
        if is_active:
            url = f"{AUTH_BACKEND_URL}/auth/user/strategies/deploy/"
        else:
            url = f"{AUTH_BACKEND_URL}/auth/user/strategies/undeploy/"
        
        headers = {
            "Authorization": authorization,
            "Content-Type": "application/json"
        }
        
        payload = {
            "strategy_code": strategy_code,
            "is_active": is_active
        }
        
        # DEBUG: Log auth API call
        print(f"AUTH API HIT → {url}")
        logger.info(f"AUTH API HIT → {url} (strategy: {strategy_code}, active: {is_active})")
        
        # Call auth backend to deploy/activate strategy
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=10
        )
        
        if response.status_code in [200, 201]:
            logger.info(f"Strategy {'activated' if is_active else 'deactivated'} in auth backend: {strategy_code}")
            return True
        else:
            logger.warning(f"Auth backend deploy returned {response.status_code}: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        # Log error but don't fail - local activation already succeeded
        logger.error(f"Failed to deploy strategy to auth backend: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error deploying to auth backend: {e}", exc_info=True)
        return False


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
            StrategyExecution.status == ExecutionStatus.active
        ).with_for_update().first()
        
        if existing_active:
            existing_active.status = ExecutionStatus.inactive
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
            execution.status = ExecutionStatus.active
            execution.activated_at = datetime.now(timezone.utc)
            execution.deactivated_at = None
            execution.run_source = 'live'  # MANDATORY: Explicitly set - Live execution
        else:
            # Create new execution record
            # MANDATORY: Explicitly set run_source - DO NOT rely on DB defaults
            execution = StrategyExecution(
                strategy_id=strategy.id,
                strategy_version=version,
                status=ExecutionStatus.active,
                activated_at=datetime.now(timezone.utc),
                deactivated_at=None,
                run_source='live'  # MANDATORY: Explicitly set - Live execution
            )
            
            # VALIDATION: Ensure run_source is set before adding to session
            if not execution.run_source:
                raise ValueError("CRITICAL: execution.run_source must be explicitly set (got None)")
            
            logger.info(f"StrategyExecution run_source={execution.run_source}")
            db.add(execution)
        
        # 9. Commit transaction
        db.commit()
        db.refresh(execution)
        
        logger.info(
            f"Strategy execution activated: strategy_code={strategy_code}, "
            f"strategy_id={strategy.id}, version={version}"
        )
        
        # CRITICAL: Also deploy/activate in auth backend database
        # This ensures strategy is activated in production database
        deploy_strategy_to_auth_backend(strategy_code, authorization, is_active=True)
        
        # 10. Return success response
        return {
            "strategy_code": strategy_code,
            "active_version": version,
            "status": ExecutionStatus.active.value
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
    if execution.status == ExecutionStatus.paused:
        logger.info(
            f"Execution already paused (idempotent): strategy_code={strategy_code}, "
            f"execution_id={execution.id}"
        )
        return {
            "strategy_code": strategy_code,
            "status": ExecutionStatus.paused.value
        }
    
    if execution.status != ExecutionStatus.active:
        raise ValueError(
            f"Cannot pause execution with status '{execution.status.value}'. "
            f"Only ACTIVE executions can be paused."
        )
    
    try:
        # 6 & 7. Update execution status to PAUSED and set deactivated_at
        execution.status = ExecutionStatus.paused
        execution.deactivated_at = datetime.now(timezone.utc)
        
        # 8. Commit transaction
        db.commit()
        db.refresh(execution)
        
        logger.info(
            f"Strategy execution paused: strategy_code={strategy_code}, "
            f"strategy_id={strategy.id}, execution_id={execution.id}"
        )
        
        # CRITICAL: Also pause in auth backend (deploy with is_active=False)
        deploy_strategy_to_auth_backend(strategy_code, authorization, is_active=False)
        
        # 9. Return success response
        return {
            "strategy_code": strategy_code,
            "status": ExecutionStatus.paused.value
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
    if execution.status == ExecutionStatus.active:
        logger.info(
            f"Execution already active (idempotent): strategy_code={strategy_code}, "
            f"execution_id={execution.id}"
        )
        return {
            "strategy_code": strategy_code,
            "status": ExecutionStatus.active.value
        }
    
    if execution.status != ExecutionStatus.paused:
        raise ValueError(
            f"Cannot resume execution with status '{execution.status.value}'. "
            f"Only PAUSED executions can be resumed."
        )
    
    try:
        # 6 & 7. Update execution status to ACTIVE and set activated_at
        execution.status = ExecutionStatus.active
        execution.activated_at = datetime.now(timezone.utc)
        execution.deactivated_at = None  # Clear deactivated_at when resuming
        
        # 8. Commit transaction
        db.commit()
        db.refresh(execution)
        
        logger.info(
            f"Strategy execution resumed: strategy_code={strategy_code}, "
            f"strategy_id={strategy.id}, execution_id={execution.id}"
        )
        
        # CRITICAL: Also resume in auth backend (deploy with is_active=True)
        deploy_strategy_to_auth_backend(strategy_code, authorization, is_active=True)
        
        # 9. Return success response
        return {
            "strategy_code": strategy_code,
            "status": ExecutionStatus.active.value
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
    if execution.status == ExecutionStatus.stopped:
        logger.info(
            f"Execution already stopped (idempotent): strategy_code={strategy_code}, "
            f"execution_id={execution.id}"
        )
        return {
            "strategy_code": strategy_code,
            "status": ExecutionStatus.stopped.value
        }
    
    # STOP is allowed only from ACTIVE or PAUSED states
    if execution.status not in [ExecutionStatus.active, ExecutionStatus.paused]:
        raise ValueError(
            f"Cannot stop execution with status '{execution.status.value}'. "
            f"Only ACTIVE or PAUSED executions can be stopped."
        )
    
    try:
        # Store previous status for logging
        previous_status = execution.status.value
        
        # 6 & 7. Update execution status to STOPPED and set deactivated_at
        execution.status = ExecutionStatus.stopped
        execution.deactivated_at = datetime.now(timezone.utc)
        
        # 8. Commit transaction
        db.commit()
        db.refresh(execution)
        
        logger.info(
            f"Strategy execution stopped (TERMINAL): strategy_code={strategy_code}, "
            f"strategy_id={strategy.id}, execution_id={execution.id}, "
            f"previous_status={previous_status}"
        )
        
        # CRITICAL: Also stop in auth backend (deploy with is_active=False)
        deploy_strategy_to_auth_backend(strategy_code, authorization, is_active=False)
        
        # 9. Return success response
        return {
            "strategy_code": strategy_code,
            "status": ExecutionStatus.stopped.value
        }
        
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Database integrity error stopping strategy execution: {e}")
        raise ValueError(f"Failed to stop strategy execution: database constraint violation")
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error stopping strategy execution: {e}", exc_info=True)
        raise ValueError(f"Failed to stop strategy execution: {str(e)}")
