"""
Strategy Execution API Routes
Handles activation of strategy versions for execution.

IMPORTANT: Execution must ALWAYS bind to a specific version (strategy_code + version).
Only one ACTIVE execution per strategy_id is allowed.
"""
from fastapi import APIRouter, HTTPException, Header, Depends, Path
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import logging
import requests

from app.database import get_db
from app.services.strategy_execution_service import activate_strategy_execution

logger = logging.getLogger(__name__)

router = APIRouter()


class ActivateStrategyRequest(BaseModel):
    """Request model for activating a strategy version"""
    version: int = Field(..., gt=0, description="Version number to activate")


class ActivateStrategyResponse(BaseModel):
    """Response model for activating a strategy"""
    success: bool
    strategy_code: str
    active_version: int
    status: str
    message: str


@router.post("/strategies/{strategy_code}/activate", response_model=ActivateStrategyResponse)
def activate_strategy_endpoint(
    strategy_code: str = Path(..., description="Strategy code (e.g., STRG-ABCD)"),
    request: ActivateStrategyRequest = ...,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db)
):
    """
    Activate a specific version of a strategy for execution.
    
    FLOW (STRICT ORDER):
    1. Extract Authorization token
    2. Call auth backend user API (via get_or_sync_user - FAILS FAST if unavailable)
    3. Sync user into local DB
    4. Fetch strategy by strategy_code
    5. Verify strategy belongs to user
    6. Verify requested version exists
    7. Start DB transaction
    8. Deactivate existing active execution (if any)
    9. Insert or update strategy_executions row:
       - strategy_id
       - strategy_version
       - status = ACTIVE
       - activated_at = now (UTC)
    10. Commit transaction
    11. Return success response
    
    IMPORTANT:
    - TEMP strategies are NOT allowed (rejected with 400)
    - Execution must ALWAYS bind to a specific version
    - Only one ACTIVE execution per strategy_id
    - Old active version must be deactivated before new activation
    - Ownership must be verified
    - Use transaction for safety (rollback on error)
    - Fail fast if auth backend unavailable
    - Never leave system without a valid active state
    
    Args:
        strategy_code: Strategy code (e.g., STRG-ABCD)
        request: ActivateStrategyRequest with version number
        authorization: Authorization header (Bearer token)
        db: Database session
    
    Returns:
        ActivateStrategyResponse with strategy_code, active_version, and status
    
    Raises:
        HTTPException: If validation fails, strategy not found, ownership mismatch, version not found, or activation fails
    """
    try:
        # Validate authorization header
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization header required")
        
        # Validate strategy_code format (basic validation)
        if not strategy_code or not isinstance(strategy_code, str):
            raise HTTPException(status_code=400, detail="Invalid strategy_code format")
        
        # TEMP strategies are NOT allowed for execution
        if strategy_code.startswith("TEMP-"):
            raise HTTPException(
                status_code=400,
                detail="TEMP strategies cannot be activated for execution. Please save the strategy first."
            )
        
        # Validate version number
        if request.version <= 0:
            raise HTTPException(status_code=400, detail="Version must be a positive integer")
        
        # Activate strategy execution (includes user sync, ownership verification, validation, and DB update)
        result = activate_strategy_execution(
            db=db,
            strategy_code=strategy_code,
            version=request.version,
            authorization=authorization
        )
        
        logger.info(
            f"Strategy execution activated successfully: strategy_code={result['strategy_code']}, "
            f"active_version={result['active_version']}"
        )
        
        return ActivateStrategyResponse(
            success=True,
            strategy_code=result["strategy_code"],
            active_version=result["active_version"],
            status=result["status"],
            message=f"Strategy version {result['active_version']} activated successfully for execution."
        )
        
    except ValueError as e:
        # Validation errors, ownership mismatch, strategy not found, or version not found
        error_msg = str(e)
        status_code = 400
        
        # Check for specific error types to return appropriate status codes
        if "not found" in error_msg.lower():
            status_code = 404
        elif "ownership" in error_msg.lower() or "different user" in error_msg.lower():
            status_code = 403
        
        logger.warning(f"Validation/ownership error activating strategy execution: {e}")
        raise HTTPException(status_code=status_code, detail=error_msg)
    except requests.exceptions.RequestException as e:
        # Auth backend unavailable - FAIL FAST
        logger.error(f"Auth backend unavailable: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Auth backend unavailable. Cannot activate strategy execution without user verification. Error: {str(e)}"
        )
    except SQLAlchemyError as e:
        # Database errors
        logger.error(f"Database error activating strategy execution: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error occurred while activating strategy execution")
    except Exception as e:
        # Unexpected errors
        logger.error(f"Unexpected error activating strategy execution: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
