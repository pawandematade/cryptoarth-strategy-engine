"""
Strategy Save Service
Handles TEMP → SAVED strategy transition.

IMPORTANT: TEMP strategies (TEMP-xxx) are NOT stored in database.
Only explicitly saved strategies are persisted.
"""
import logging
import secrets
import string
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models import Strategy, StrategyVersion, StrategyStatus, User
from app.services.user_sync_service import get_or_sync_user

logger = logging.getLogger(__name__)


def generate_strategy_code() -> str:
    """
    Generate unique strategy code (e.g., STRG-ABCD).
    
    Returns:
        str: Unique strategy code
    """
    # Generate random 4-character code
    random_part = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
    return f"STRG-{random_part}"


def validate_temp_strategy_id(temp_strategy_id: str) -> bool:
    """
    Validate that strategy ID is a TEMP strategy ID.
    
    Args:
        temp_strategy_id: Strategy ID to validate
    
    Returns:
        bool: True if valid TEMP strategy ID
    """
    return isinstance(temp_strategy_id, str) and temp_strategy_id.startswith("TEMP-")


def validate_strategy_payload(strategy_payload: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate strategy payload schema.
    
    Args:
        strategy_payload: Strategy payload to validate
    
    Returns:
        tuple: (is_valid, error_message)
    """
    if not isinstance(strategy_payload, dict):
        return False, "strategy_payload must be a JSON object"
    
    # Basic structure validation
    # Add more specific validations based on your strategy schema requirements
    # For now, just check that it's not empty
    if not strategy_payload:
        return False, "strategy_payload cannot be empty"
    
    # You can add more validations here:
    # - Check for required fields
    # - Validate indicators
    # - Validate operators
    # - Validate timeframe
    # - Reject execution-only fields
    
    return True, None


def save_strategy(
    db: Session,
    temp_strategy_id: str,
    name: str,
    strategy_payload: Dict[str, Any],
    authorization: str,
    description: Optional[str] = None,
    backtest_snapshot: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Save a TEMP strategy to database.
    
    FLOW:
    1. Extract user ID from authorization header
    2. Sync user from auth backend (FAIL FAST if unavailable)
    3. Validate temp_strategy_id (must be TEMP-xxx)
    4. Validate strategy_payload
    5. Generate strategy_code
    6. Create strategy and first version in transaction
    7. Return strategy_id, strategy_code, version
    
    Args:
        db: Database session
        temp_strategy_id: TEMP strategy ID (e.g., TEMP-123456)
        name: Strategy name
        strategy_payload: Full strategy JSON payload
        authorization: Authorization header (Bearer token)
        description: Optional strategy description
        backtest_snapshot: Optional backtest snapshot JSON
    
    Returns:
        dict: {
            "strategy_id": int,
            "strategy_code": str,
            "version": int
        }
    
    Raises:
        ValueError: If validation fails
        requests.exceptions.RequestException: If auth backend unavailable
    """
    # 1 & 2. Extract user ID and sync user from auth backend (FAIL FAST if unavailable)
    # get_or_sync_user will call auth backend API and sync user to local DB
    # This will raise exception if auth backend is unavailable
    user = get_or_sync_user(db, external_user_id=None, authorization=authorization)
    if not user:
        raise ValueError("Failed to sync user from auth backend")
    
    # 3. Validate temp_strategy_id (must be TEMP-xxx)
    if not validate_temp_strategy_id(temp_strategy_id):
        raise ValueError(f"Invalid temp_strategy_id: must start with 'TEMP-', got '{temp_strategy_id}'")
    
    # 4. Validate strategy_payload
    is_valid, error_msg = validate_strategy_payload(strategy_payload)
    if not is_valid:
        raise ValueError(f"Invalid strategy_payload: {error_msg}")
    
    # 5. Generate strategy_code
    strategy_code = generate_strategy_code()
    
    # Ensure uniqueness (retry if collision, unlikely but possible)
    max_retries = 5
    for _ in range(max_retries):
        existing = db.query(Strategy).filter(Strategy.strategy_code == strategy_code).first()
        if not existing:
            break
        strategy_code = generate_strategy_code()
    else:
        raise ValueError("Failed to generate unique strategy_code after retries")
    
    try:
        # 6. Create strategy and first version in transaction
        strategy = Strategy(
            user_id=user.id,  # Use local user ID, not external_user_id
            strategy_code=strategy_code,
            name=name,
            description=description,
            status=StrategyStatus.DRAFT
        )
        db.add(strategy)
        db.flush()  # Get strategy.id without committing
        
        # Create first version
        strategy_version = StrategyVersion(
            strategy_id=strategy.id,
            version=1,
            strategy_payload=strategy_payload,
            backtest_snapshot=backtest_snapshot
        )
        db.add(strategy_version)
        
        # Commit transaction
        db.commit()
        db.refresh(strategy)
        
        logger.info(f"Strategy saved successfully: temp_strategy_id={temp_strategy_id}, strategy_id={strategy.id}, strategy_code={strategy_code}")
        
        # 7. Return strategy_id, strategy_code, version
        return {
            "strategy_id": strategy.id,
            "strategy_code": strategy_code,
            "version": 1
        }
        
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Database integrity error saving strategy: {e}")
        raise ValueError(f"Failed to save strategy: database constraint violation")
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error saving strategy: {e}", exc_info=True)
        raise ValueError(f"Failed to save strategy: {str(e)}")
