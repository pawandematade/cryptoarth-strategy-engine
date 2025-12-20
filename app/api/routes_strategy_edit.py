"""
Strategy Edit API Routes
Handles editing saved strategies by creating new versions.

IMPORTANT: Editing a strategy NEVER overwrites existing versions.
Every edit creates a NEW version in strategy_versions table.
"""
from fastapi import APIRouter, HTTPException, Header, Depends, Path
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import logging
import requests

from app.database import get_db
from app.services.strategy_edit_service import edit_strategy

logger = logging.getLogger(__name__)

router = APIRouter()


class EditStrategyRequest(BaseModel):
    """Request model for editing a saved strategy"""
    strategy_payload: Dict[str, Any] = Field(..., description="Full strategy JSON payload")
    backtest_snapshot: Optional[Dict[str, Any]] = Field(None, description="Optional backtest snapshot JSON")
    description: Optional[str] = Field(None, description="Optional updated strategy description")


class EditStrategyResponse(BaseModel):
    """Response model for editing a strategy"""
    success: bool
    strategy_code: str
    new_version: int
    message: str


@router.post("/strategies/{strategy_code}/edit", response_model=EditStrategyResponse)
def edit_strategy_endpoint(
    strategy_code: str = Path(..., description="Strategy code (e.g., STRG-ABCD)"),
    request: EditStrategyRequest = ...,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db)
):
    """
    Edit a saved strategy by creating a new version.
    
    FLOW (STRICT ORDER):
    1. Extract Authorization token
    2. Call auth backend user API (via get_or_sync_user - FAILS FAST if unavailable)
    3. Sync user into local DB
    4. Fetch strategy by strategy_code
    5. Verify strategy ownership (user_id match)
    6. Get latest version number from strategy_versions
    7. Validate strategy_payload schema (same rules as save)
    8. Create new strategy_versions row with version = latest_version + 1
    9. Update strategies.description if provided
    10. Commit transaction
    11. Return strategy_code and new_version
    
    IMPORTANT:
    - Editing NEVER overwrites existing versions
    - Every edit creates a NEW version row
    - TEMP strategies are NOT allowed (only saved strategies can be edited)
    - Ownership must be verified
    - Use transaction for safety (rollback on error)
    - Old versions remain unchanged
    - No partial saves
    - No ghost versions
    
    Args:
        strategy_code: Strategy code (e.g., STRG-ABCD)
        request: EditStrategyRequest with strategy_payload, optional description and backtest_snapshot
        authorization: Authorization header (Bearer token)
        db: Database session
    
    Returns:
        EditStrategyResponse with strategy_code and new_version
    
    Raises:
        HTTPException: If validation fails, strategy not found, ownership mismatch, or edit fails
    """
    try:
        # Validate authorization header
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization header required")
        
        # Validate strategy_code format (basic validation)
        if not strategy_code or not isinstance(strategy_code, str):
            raise HTTPException(status_code=400, detail="Invalid strategy_code format")
        
        # TEMP strategies are NOT allowed for editing
        if strategy_code.startswith("TEMP-"):
            raise HTTPException(
                status_code=400,
                detail="TEMP strategies cannot be edited. Please save the strategy first."
            )
        
        # Edit strategy (includes user sync, ownership verification, validation, and DB update)
        result = edit_strategy(
            db=db,
            strategy_code=strategy_code,
            strategy_payload=request.strategy_payload,
            authorization=authorization,
            description=request.description,
            backtest_snapshot=request.backtest_snapshot
        )
        
        logger.info(
            f"Strategy edited successfully: strategy_code={result['strategy_code']}, "
            f"new_version={result['new_version']}"
        )
        
        return EditStrategyResponse(
            success=True,
            strategy_code=result["strategy_code"],
            new_version=result["new_version"],
            message=f"Strategy edited successfully. New version {result['new_version']} created."
        )
        
    except ValueError as e:
        # Validation errors, ownership mismatch, or strategy not found
        error_msg = str(e)
        status_code = 400
        
        # Check for specific error types to return appropriate status codes
        if "not found" in error_msg.lower():
            status_code = 404
        elif "ownership" in error_msg.lower() or "different user" in error_msg.lower():
            status_code = 403
        
        logger.warning(f"Validation/ownership error editing strategy: {e}")
        raise HTTPException(status_code=status_code, detail=error_msg)
    except requests.exceptions.RequestException as e:
        # Auth backend unavailable - FAIL FAST
        logger.error(f"Auth backend unavailable: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Auth backend unavailable. Cannot edit strategy without user verification. Error: {str(e)}"
        )
    except SQLAlchemyError as e:
        # Database errors
        logger.error(f"Database error editing strategy: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error occurred while editing strategy")
    except Exception as e:
        # Unexpected errors
        logger.error(f"Unexpected error editing strategy: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
