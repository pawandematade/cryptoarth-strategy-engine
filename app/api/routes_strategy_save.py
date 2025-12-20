"""
Strategy Save API Routes
Handles TEMP → SAVED strategy transition.

IMPORTANT: TEMP strategies (TEMP-xxx) are NOT stored in database.
Only explicitly saved strategies are persisted via this endpoint.
"""
from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import logging
import requests

from app.database import get_db
from app.services.strategy_save_service import save_strategy

logger = logging.getLogger(__name__)

router = APIRouter()


class SaveStrategyRequest(BaseModel):
    """Request model for saving a TEMP strategy"""
    temp_strategy_id: str = Field(..., description="TEMP strategy ID (must start with 'TEMP-')")
    name: str = Field(..., min_length=1, max_length=255, description="Strategy name")
    description: Optional[str] = Field(None, description="Optional strategy description")
    strategy_payload: Dict[str, Any] = Field(..., description="Full strategy JSON payload")
    backtest_snapshot: Optional[Dict[str, Any]] = Field(None, description="Optional backtest snapshot JSON")


class SaveStrategyResponse(BaseModel):
    """Response model for saving a strategy"""
    success: bool
    strategy_id: int
    strategy_code: str
    version: int
    message: str


@router.post("/strategies/save", response_model=SaveStrategyResponse)
def save_strategy_endpoint(
    request: SaveStrategyRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db)
):
    """
    Save a TEMP strategy to database.
    
    FLOW (STRICT ORDER):
    1. Extract Authorization token
    2. Call auth backend user API (via get_or_sync_user - FAILS FAST if unavailable)
    3. Sync user into local DB
    4. Validate temp_strategy_id (must start with "TEMP-")
    5. Validate strategy_payload schema
    6. Save strategy to DB in transaction
    7. Return strategy_id, strategy_code, version
    
    IMPORTANT:
    - TEMP strategies (TEMP-xxx) are NOT stored in database
    - Only explicitly saved strategies are persisted
    - Fail fast if auth backend unavailable
    - Use transaction for safety (rollback on error)
    - TEMP strategy remains intact if save fails
    
    Args:
        request: SaveStrategyRequest with temp_strategy_id, name, strategy_payload, etc.
        authorization: Authorization header (Bearer token)
        db: Database session
    
    Returns:
        SaveStrategyResponse with strategy_id, strategy_code, version
    
    Raises:
        HTTPException: If validation fails or save fails
    """
    try:
        # Validate authorization header
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization header required")
        
        # Save strategy (includes user sync, validation, and DB save)
        result = save_strategy(
            db=db,
            temp_strategy_id=request.temp_strategy_id,
            name=request.name,
            strategy_payload=request.strategy_payload,
            authorization=authorization,
            description=request.description,
            backtest_snapshot=request.backtest_snapshot
        )
        
        logger.info(f"Strategy saved successfully: strategy_id={result['strategy_id']}, strategy_code={result['strategy_code']}")
        
        return SaveStrategyResponse(
            success=True,
            strategy_id=result["strategy_id"],
            strategy_code=result["strategy_code"],
            version=result["version"],
            message="Strategy saved successfully"
        )
        
    except ValueError as e:
        # Validation errors
        logger.warning(f"Validation error saving strategy: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except requests.exceptions.RequestException as e:
        # Auth backend unavailable - FAIL FAST
        logger.error(f"Auth backend unavailable: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Auth backend unavailable. Cannot save strategy without user verification. Error: {str(e)}"
        )
    except SQLAlchemyError as e:
        # Database errors
        logger.error(f"Database error saving strategy: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error occurred while saving strategy")
    except Exception as e:
        # Unexpected errors
        logger.error(f"Unexpected error saving strategy: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
