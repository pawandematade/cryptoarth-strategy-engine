"""
Strategy Run API Routes
Handles strategy execution creation and management.
"""
from fastapi import APIRouter, HTTPException, Header, Depends, Body
from pydantic import BaseModel
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import logging

from app.database import get_db
from app.models import Strategy, StrategyVersion, StrategyExecution, ExecutionMode, ExecutionStatus
from app.services.user_sync_service import get_or_sync_user

logger = logging.getLogger(__name__)

router = APIRouter()


class StrategyRunRequest(BaseModel):
    """Request model for creating strategy run"""
    strategy_id: int
    execution_mode: str  # "template", "paper", or "live"
    strategy_config: Optional[Dict[str, Any]] = None  # Capital, leverage, etc. for paper mode


class StrategyRunResponse(BaseModel):
    """Response model for strategy run"""
    success: bool
    execution_id: int
    strategy_id: int
    strategy_code: str
    execution_mode: str
    status: str
    message: str


@router.post("/strategy-runs/live", response_model=StrategyRunResponse)
def create_strategy_run(
    request: StrategyRunRequest = Body(...),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db)
):
    """
    Create a strategy run (execution).
    
    CRITICAL: Creates execution row immediately.
    History tab depends ONLY on this insert.
    
    Args:
        request: Strategy run request
        authorization: Authorization header (Bearer token)
        db: Database session
    
    Returns:
        StrategyRunResponse with execution details
    """
    try:
        # Authenticate user
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization header required")
        
        user = get_or_sync_user(db, external_user_id=None, authorization=authorization)
        if not user:
            raise HTTPException(status_code=401, detail="Failed to authenticate user")
        
        # Validate strategy exists and is active
        strategy = db.query(Strategy).filter(
            Strategy.id == request.strategy_id,
            Strategy.user_id == user.id
        ).first()
        
        if not strategy:
            raise HTTPException(
                status_code=404,
                detail=f"Strategy with ID {request.strategy_id} not found or access denied"
            )
        
        # Check if strategy is active
        # Handle both Enum and string status values
        status_str = strategy.status.value if hasattr(strategy.status, 'value') else str(strategy.status)
        status_str_lower = status_str.lower() if status_str else ""
        
        # Debug log to see actual status value
        logger.info(f"Strategy status check: strategy_id={strategy.id}, name={strategy.name}, status={status_str}, status_lower={status_str_lower}, status_type={type(strategy.status)}")
        
        if status_str_lower != "active":
            # If strategy is draft, automatically activate it (for backward compatibility)
            if status_str_lower == "draft":
                logger.info(f"Auto-activating draft strategy: strategy_id={strategy.id}")
                from app.models import StrategyStatus
                strategy.status = StrategyStatus.ACTIVE.value
                db.commit()
                db.refresh(strategy)
                logger.info(f"✅ Strategy auto-activated: strategy_id={strategy.id}")
            else:
                error_msg = f"Strategy must be active to run. Current status: {status_str} (strategy_id={strategy.id})"
                logger.warning(error_msg)
                raise HTTPException(
                    status_code=400,
                    detail=error_msg
                )
        
        # Get latest version
        latest_version = db.query(StrategyVersion).filter(
            StrategyVersion.strategy_id == request.strategy_id
        ).order_by(StrategyVersion.version.desc()).first()
        
        if not latest_version:
            raise HTTPException(
                status_code=404,
                detail=f"No version found for strategy {request.strategy_id}"
            )
        
        # Validate and normalize execution mode
        # CRITICAL: Normalize input to lowercase to match Enum values
        execution_mode_input = request.execution_mode.strip().lower() if request.execution_mode else ""
        if execution_mode_input not in ["template", "paper", "live"]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid execution_mode: {request.execution_mode}. Must be 'template', 'paper', or 'live'"
            )
        
        # CRITICAL: Use ExecutionMode(value) constructor - accepts lowercase string
        # ExecutionMode enum values are lowercase: "template", "paper", "live"
        # This matches DB ENUM values exactly
        try:
            execution_mode = ExecutionMode(execution_mode_input)  # ExecutionMode("paper") -> ExecutionMode.paper
            logger.info(f"Execution mode normalized: input='{request.execution_mode}' -> enum={execution_mode}, value={execution_mode.value}")
        except ValueError as e:
            logger.error(f"Invalid execution_mode enum value: input='{request.execution_mode}', normalized='{execution_mode_input}'")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid execution_mode: {request.execution_mode}. Must be 'template', 'paper', or 'live'"
            )
        
        # run_source matches execution_mode (use lowercase string for run_source)
        run_source = execution_mode_input
        
        # CRITICAL: Create execution row immediately
        # History tab depends ONLY on this insert
        execution = StrategyExecution(
            strategy_id=strategy.id,
            strategy_version=latest_version.version,
            strategy_name=strategy.name,
            strategy_code=strategy.strategy_code,
            execution_mode=execution_mode,
            run_source=run_source.value if hasattr(run_source, 'value') else str(run_source),
            status=ExecutionStatus.running,
            trades=0,
            pnl="0.0"
        )
        
        db.add(execution)
        db.flush()
        
        # Commit immediately
        db.commit()
        db.refresh(execution)
        
        logger.info(f"Strategy run created: execution_id={execution.id}, strategy_id={strategy.id}, execution_mode={execution_mode_str}")
        
        status_val = execution.status.value if hasattr(execution.status, 'value') else str(execution.status)
        execution_mode_val = execution.execution_mode.value if hasattr(execution.execution_mode, 'value') else str(execution.execution_mode)
        
        return StrategyRunResponse(
            success=True,
            execution_id=execution.id,
            strategy_id=strategy.id,
            strategy_code=strategy.strategy_code,
            execution_mode=execution_mode_val,
            status=status_val,
            message="Strategy run created successfully"
        )
        
    except HTTPException:
        raise
    except IntegrityError as e:
        db.rollback()
        error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
        logger.error(f"Database integrity error creating strategy run: {error_msg}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Database error: {error_msg.splitlines()[0]}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating strategy run: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

