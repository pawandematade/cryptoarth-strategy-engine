"""
Strategy Save API Routes
Handles TEMP â†’ SAVED strategy transition.

IMPORTANT: TEMP strategies (TEMP-xxx) are NOT stored in database.
Only explicitly saved strategies are persisted via this endpoint.
"""
from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
import logging
import requests

from common.db import get_db
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
    logger.info("Entered save_strategy API endpoint")
    logger.info(f"Request data: temp_strategy_id={request.temp_strategy_id}, name={request.name}")
    
    try:
        # STEP 1: CONFIRM ACTIVE DATABASE (CRITICAL)
        from common.db import DATABASE_URL
        # Extract DB info from DATABASE_URL for logging
        db_info = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else "configured"
        logger.info(f"Active DB: {db_info}")
        
        # Validate authorization header
        if not authorization:
            logger.warning("Authorization header missing")
            raise HTTPException(status_code=401, detail="Authorization header required")
        
        logger.info("Calling save_strategy()")
        logger.info(f"Request params: temp_strategy_id={request.temp_strategy_id}, name={request.name}")
        
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
        
        # STEP 6: RESPONSE MUST USE REAL DB ID
        # Verify strategy_id is from actual DB, not random/fake
        strategy_id = result["strategy_id"]
        if not isinstance(strategy_id, int) or strategy_id <= 0:
            logger.error(f"âŒ [ENDPOINT] Invalid strategy_id in response: {strategy_id}")
            raise HTTPException(status_code=500, detail="Invalid strategy_id returned from save operation")
        
        print(f"âœ… [ENDPOINT] Returning response with strategy_id={strategy_id}")
        logger.info(f"âœ… [ENDPOINT] Returning response with strategy_id={strategy_id}")
        print("ðŸ”¥ðŸ”¥ðŸ”¥ EXITING save_strategy API ENDPOINT (SUCCESS) ðŸ”¥ðŸ”¥ðŸ”¥")
        logger.info("ðŸ”¥ðŸ”¥ðŸ”¥ EXITING save_strategy API ENDPOINT (SUCCESS) ðŸ”¥ðŸ”¥ðŸ”¥")
        
        return SaveStrategyResponse(
            success=True,
            strategy_id=strategy_id,
            strategy_code=result["strategy_code"],
            version=result["version"],
            message="Strategy saved successfully"
        )
        
    except ValueError as e:
        # Validation errors (including NOT NULL constraint violations)
        error_msg = str(e)
        print(f"âŒ [ENDPOINT] ValueError: {error_msg}")
        logger.error(f"âŒ Validation error saving strategy: {error_msg}", exc_info=True)
        print("ðŸ”¥ðŸ”¥ðŸ”¥ EXITING save_strategy API ENDPOINT (ValueError) ðŸ”¥ðŸ”¥ðŸ”¥")
        logger.info("ðŸ”¥ðŸ”¥ðŸ”¥ EXITING save_strategy API ENDPOINT (ValueError) ðŸ”¥ðŸ”¥ðŸ”¥")
        
        # Check if it's a NOT NULL constraint error
        if 'must be explicitly set' in error_msg or 'NOT NULL' in error_msg:
            raise HTTPException(
                status_code=400,
                detail=f"Database constraint violation: {error_msg}. Please ensure all required fields are set."
            )
        else:
            raise HTTPException(status_code=400, detail=error_msg)
    except requests.exceptions.RequestException as e:
        # Auth backend unavailable - FAIL FAST
        print(f"âŒ [ENDPOINT] RequestException (Auth backend unavailable): {e}")
        logger.error(f"Auth backend unavailable: {e}")
        print("ðŸ”¥ðŸ”¥ðŸ”¥ EXITING save_strategy API ENDPOINT (RequestException) ðŸ”¥ðŸ”¥ðŸ”¥")
        logger.info("ðŸ”¥ðŸ”¥ðŸ”¥ EXITING save_strategy API ENDPOINT (RequestException) ðŸ”¥ðŸ”¥ðŸ”¥")
        raise HTTPException(
            status_code=503,
            detail=f"Auth backend unavailable. Cannot save strategy without user verification. Error: {str(e)}"
        )
    except IntegrityError as e:
        # Database integrity errors (NOT NULL, UNIQUE, FOREIGN KEY violations)
        error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
        print(f"âŒ [ENDPOINT] IntegrityError: {error_msg}")
        logger.error(f"âŒ Database integrity error saving strategy: {error_msg}", exc_info=True)
        import traceback
        traceback.print_exc()
        db.rollback()
        print("ðŸ”¥ðŸ”¥ðŸ”¥ EXITING save_strategy API ENDPOINT (IntegrityError) ðŸ”¥ðŸ”¥ðŸ”¥")
        logger.info("ðŸ”¥ðŸ”¥ðŸ”¥ EXITING save_strategy API ENDPOINT (IntegrityError) ðŸ”¥ðŸ”¥ðŸ”¥")
        
        # Check if it's a NOT NULL constraint violation
        if 'NOT NULL' in error_msg or 'cannot be null' in error_msg.lower():
            raise HTTPException(
                status_code=400,
                detail=f"Database constraint violation: Missing required field. Error: {error_msg}"
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Database constraint violation: {error_msg}"
            )
    except SQLAlchemyError as e:
        # Other database errors
        error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
        print(f"âŒ [ENDPOINT] SQLAlchemyError: {error_msg}")
        logger.error(f"âŒ Database error saving strategy: {error_msg}", exc_info=True)
        import traceback
        traceback.print_exc()
        db.rollback()
        print("ðŸ”¥ðŸ”¥ðŸ”¥ EXITING save_strategy API ENDPOINT (SQLAlchemyError) ðŸ”¥ðŸ”¥ðŸ”¥")
        logger.info("ðŸ”¥ðŸ”¥ðŸ”¥ EXITING save_strategy API ENDPOINT (SQLAlchemyError) ðŸ”¥ðŸ”¥ðŸ”¥")
        raise HTTPException(
            status_code=500,
            detail=f"Database error occurred while saving strategy: {error_msg}"
        )
    except Exception as e:
        # Unexpected errors
        print(f"âŒ [ENDPOINT] Unexpected error: {e}")
        logger.error(f"Unexpected error saving strategy: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        db.rollback()
        print("ðŸ”¥ðŸ”¥ðŸ”¥ EXITING save_strategy API ENDPOINT (Exception) ðŸ”¥ðŸ”¥ðŸ”¥")
        logger.info("ðŸ”¥ðŸ”¥ðŸ”¥ EXITING save_strategy API ENDPOINT (Exception) ðŸ”¥ðŸ”¥ðŸ”¥")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
